"""Persistent credential, proof-boundary, offline-helper and local API checks.

Only temporary test authorities are issued. No fixture key is a user key.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

from aiohttp import ClientSession, web

from manager.admin import create_admin_app
from manager.authority import AuthorityError, AuthorityStore, GameAuthority
from tools.admin_key import CredentialError, HEADER, PREFIX, canonical, parse_credential, proof_for, render_credential


ROOT = Path(__file__).resolve().parents[1]


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jk-authority-test-")
        self.root = Path(self.temp.name)
        self.directory = self.root / "authority"
        self.store = AuthorityStore(self.directory)

    def tearDown(self):
        self.temp.cleanup()

    def issue(self, caps=None):
        return self.store.issue("Private QA fixture", caps or ["match.next"])

    def test_constructor_status_and_invalid_actions_do_not_create_identity(self):
        with patch("manager.authority.secrets.token_hex", side_effect=AssertionError("unexpected issuance")):
            self.assertIsNone(self.store.metadata()["server_id"])
            self.assertEqual(self.store.metadata()["credentials"], [])
            for action in (lambda: self.store.issue("", ["match.next"]),
                           lambda: self.store.revoke("0" * 16), lambda: self.store.rotate("0" * 16)):
                with self.assertRaises(AuthorityError):
                    action()
        self.assertFalse(self.directory.exists())

    def test_explicit_issuance_persists_private_identity_and_sanitized_metadata(self):
        first = self.issue(["player.kick", "match.next"])
        key = parse_credential(first["credential"])
        metadata = self.store.metadata()
        self.assertEqual(metadata, AuthorityStore(self.directory).metadata())
        self.assertEqual(metadata["server_id"], key["server_id"])
        self.assertEqual(metadata["credentials"][0]["id"], key["key_id"])
        self.assertNotIn(key["secret"], json.dumps(metadata))
        self.assertNotIn("secret", json.dumps(metadata))
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        second = parse_credential(self.issue()["credential"])
        self.assertEqual(key["server_id"], second["server_id"])
        self.assertNotEqual(key["key_id"], second["key_id"])
        self.assertNotEqual(key["secret"], second["secret"])

    def test_revocation_is_idempotent_and_survives_store_recreation(self):
        issued = self.issue()
        key_id = issued["metadata"]["id"]
        first = self.store.revoke(key_id)
        self.assertEqual(first["status"], "revoked")
        self.assertIsNotNone(first["revoked_at"])
        self.assertEqual(first, self.store.revoke(key_id))
        self.assertIsNone(AuthorityStore(self.directory)._active_record(key_id))

    def test_rotation_atomically_revokes_old_key_and_retains_issuer_and_caps(self):
        old = self.issue(["player.kick"])
        new = self.store.rotate(old["metadata"]["id"])
        self.assertEqual(new["metadata"]["server_id"], old["metadata"]["server_id"])
        self.assertEqual(new["metadata"]["capabilities"], ["player.kick"])
        self.assertEqual(new["metadata"]["rotated_from"], old["metadata"]["id"])
        self.assertNotEqual(new["metadata"]["id"], old["metadata"]["id"])
        self.assertIsNone(self.store._active_record(old["metadata"]["id"]))
        with self.assertRaises(AuthorityError):
            self.store.rotate(old["metadata"]["id"])

    def test_failed_rotation_rolls_back_insert_and_keeps_current_key_active(self):
        old = self.issue()
        before = self.store.metadata()
        with patch("manager.authority.render_credential", side_effect=RuntimeError("fixture delivery preparation failed")):
            with self.assertRaises(RuntimeError):
                self.store.rotate(old["metadata"]["id"])
        self.assertEqual(self.store.metadata(), before)
        self.assertIsNotNone(self.store._active_record(old["metadata"]["id"]))

    def test_insecure_permissions_are_rejected_without_silent_repair(self):
        self.issue()
        self.store.path.chmod(0o644)
        with self.assertRaises(AuthorityError):
            self.store.metadata()
        with self.assertRaises(AuthorityError):
            self.issue()
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o644)
        self.store.path.chmod(0o600)
        self.directory.chmod(0o755)
        with self.assertRaises(AuthorityError):
            self.store.metadata()

    @unittest.skipUnless(os.name == "posix", "POSIX link and ownership validation")
    def test_symlink_directory_database_journal_and_hardlinks_are_rejected(self):
        other = self.root / "actual"
        other.mkdir(mode=0o700)
        self.directory.symlink_to(other, target_is_directory=True)
        with self.assertRaises(AuthorityError):
            self.issue()
        self.directory.unlink()
        self.issue()
        target = self.root / "copied.sqlite3"
        self.store.path.rename(target)
        self.store.path.symlink_to(target)
        with self.assertRaises(AuthorityError):
            self.store.metadata()
        self.store.path.unlink()
        os.link(target, self.store.path)
        with self.assertRaises(AuthorityError):
            self.store.metadata()
        self.store.path.unlink()
        target.rename(self.store.path)
        journal = self.store.path.with_name("keys.sqlite3-journal")
        journal.symlink_to(self.root / "missing")
        with self.assertRaises(AuthorityError):
            self.store.metadata()

    def test_corrupt_store_and_malformed_record_fail_closed(self):
        issued = self.issue()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute("UPDATE credentials SET capabilities=?", ('["shell.exec"]',))
        with self.assertRaises(AuthorityError):
            self.store.metadata()
        with self.assertRaises(AuthorityError):
            self.issue()
        self.assertIsNotNone(issued)
        self.store.path.write_bytes(b"not a SQLite database")
        before = self.store.path.read_bytes()
        with self.assertRaises(AuthorityError):
            self.issue()
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_issue_rejects_unrecognized_empty_duplicate_or_injected_values(self):
        for label, caps in (("name\nsecret", ["match.next"]), ("operator", []),
                            ("operator", ["shell.exec"]), ("operator", "match.next"),
                            ("operator", ["match.next", "match.next"]), ("\u2603", ["match.next"])):
            with self.subTest(label=label, caps=caps), self.assertRaises(AuthorityError):
                self.store.issue(label, caps)
        self.assertFalse(self.directory.exists())


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jk-proof-test-")
        self.store = AuthorityStore(Path(self.temp.name) / "authority")
        self.issued = self.store.issue("Private QA fixture", ["match.next"])
        self.key = parse_credential(self.issued["credential"])
        self.now = 10.0
        self.policy = GameAuthority(self.store, clock=lambda: self.now)

    def tearDown(self):
        self.temp.cleanup()

    def answer(self, challenge, key=None):
        return proof_for(key or self.key, challenge).split()[2:]

    def login(self, peer=42, generation=1, key=None):
        challenge = self.policy.begin(peer, generation)
        self.assertTrue(challenge.startswith("JKADMIN1:"))
        reply = self.policy.prove(peer, generation, *self.answer(challenge, key))
        self.assertIn("authenticated", reply)
        return challenge

    def test_valid_proof_authorizes_only_current_peer_generation_and_capabilities(self):
        self.login()
        self.assertTrue(self.policy.authorized(42, 1))
        self.assertTrue(self.policy.authorized(42, 1, "match.next"))
        for peer, generation, capability in ((43, 1, None), (42, 2, None), (42, 1, "player.kick"), (42, 1, "shell.exec")):
            self.assertFalse(self.policy.authorized(peer, generation, capability))
        self.assertIsNotNone(self.store.metadata()["credentials"][0]["last_used_at"])

    def test_nonce_is_bound_to_trusted_peer_and_generation(self):
        challenge = self.policy.begin(42, 1)
        answer = self.answer(challenge)
        self.assertNotIn("authenticated", self.policy.prove(43, 1, *answer))
        self.assertNotIn("authenticated", self.policy.prove(42, 2, *answer))
        self.assertFalse(self.policy.authorized(43, 1))
        self.assertIn("authenticated", self.policy.prove(42, 1, *answer))

    def test_bad_mac_consumes_nonce_and_replay_never_authenticates(self):
        challenge = self.policy.begin(42, 1)
        key_id, mac = self.answer(challenge)
        bad = ("0" if mac[0] != "0" else "1") + mac[1:]
        self.assertNotIn("authenticated", self.policy.prove(42, 1, key_id, bad))
        self.assertNotIn("authenticated", self.policy.prove(42, 1, key_id, mac))
        self.assertFalse(self.policy.authorized(42, 1))
        new = self.policy.begin(42, 1)
        answer = self.answer(new)
        self.assertIn("authenticated", self.policy.prove(42, 1, *answer))
        self.policy.logout(42, 1)
        self.assertNotIn("authenticated", self.policy.prove(42, 1, *answer))
        self.assertFalse(self.policy.authorized(42, 1))

    def test_wrong_key_or_malformed_mac_never_grants_authority(self):
        for key_id, mac in (("0" * 16, "0" * 64), (self.key["key_id"], "f" * 63),
                            (self.key["key_id"], "F" * 64), ("invalid", "0" * 64)):
            self.policy.begin(42, 1)
            self.assertNotIn("authenticated", self.policy.prove(42, 1, key_id, mac))
            self.assertFalse(self.policy.authorized(42, 1))

    def test_challenge_and_grant_expire_at_the_exact_boundaries(self):
        challenge = self.policy.begin(42, 1)
        answer = self.answer(challenge)
        self.now += 120
        self.assertNotIn("authenticated", self.policy.prove(42, 1, *answer))
        self.login()
        self.now += 899.999
        self.assertTrue(self.policy.authorized(42, 1))
        self.now += .001
        self.assertFalse(self.policy.authorized(42, 1))

    def test_reset_new_session_and_logout_clear_proofs_and_grants(self):
        challenge = self.policy.begin(42, 1)
        answer = self.answer(challenge)
        self.policy.reset()
        self.assertNotIn("authenticated", self.policy.prove(42, 1, *answer))
        other = GameAuthority(self.store, clock=lambda: self.now)
        self.assertNotIn("authenticated", other.prove(42, 1, *answer))
        self.login()
        self.policy.logout(42, 1)
        self.assertFalse(self.policy.authorized(42, 1))
        self.login()
        self.policy.reset()
        self.assertFalse(self.policy.authorized(42, 1))

    def test_revocation_and_rotation_are_checked_on_every_authorization(self):
        self.login()
        AuthorityStore(self.store.directory).revoke(self.key["key_id"])
        self.assertFalse(self.policy.authorized(42, 1))
        fresh = self.store.issue("Second private QA fixture", ["player.kick"])
        key = parse_credential(fresh["credential"])
        self.login(43, 9, key)
        self.assertTrue(self.policy.authorized(43, 9, "player.kick"))
        replacement = self.store.rotate(key["key_id"])
        self.assertFalse(self.policy.authorized(43, 9))
        self.login(43, 9, parse_credential(replacement["credential"]))
        self.assertTrue(self.policy.authorized(43, 9, "player.kick"))
        self.assertFalse(self.policy.authorized(43, 9, "match.next"))

    def test_unavailable_store_denies_and_discards_existing_grant(self):
        self.login()
        self.store.path.chmod(0o644)
        self.assertFalse(self.policy.authorized(42, 1))
        self.assertIn("unavailable", self.policy.begin(43, 1))
        self.store.path.chmod(0o600)
        self.assertFalse(self.policy.authorized(42, 1))

    def test_rate_and_state_are_bounded_without_allocating_for_invalid_peers(self):
        for _ in range(4):
            self.assertTrue(self.policy.begin(42, 1).startswith("JKADMIN1:"))
        self.assertIn("rate limited", self.policy.begin(42, 1))
        self.now += 61
        self.assertTrue(self.policy.begin(42, 1).startswith("JKADMIN1:"))
        for peer in range(100, 1200):
            self.policy.begin(peer, 1)
            self.policy.prove(peer, 1, "bad", "bad")
        self.assertLessEqual(len(self.policy._rates), self.policy.MAX_RATE_PEERS)
        self.assertLessEqual(self.policy.status()["pending_challenges"], self.policy.MAX_PENDING)
        for peer, generation in ((0, 1), (1, 1), (42, 0), (True, 1), (42, True), (-1, 1), (42, 1 << 32)):
            self.assertNotIn("JKADMIN1:", self.policy.begin(peer, generation))
            self.assertFalse(self.policy.authorized(peer, generation))

    def test_policy_status_never_exposes_keys_nonces_or_proofs(self):
        challenge = self.login()
        status = json.dumps(self.policy.status())
        for value in (self.key["secret"], self.key["key_id"], challenge, self.key["server_id"]):
            self.assertNotIn(value, status)


class OfflineHelperTests(unittest.TestCase):
    def setUp(self):
        self.key = {"format": "JKADMIN-KEY", "version": 1, "server_id": "a" * 32,
                    "key_id": "b" * 16, "secret": "01" * 32, "label": "Fixed non-user test key",
                    "capabilities": ["match.next"]}
        self.text = render_credential(self.key)
        self.challenge = "JKADMIN1:" + "a" * 32 + ":" + "c" * 32

    def test_helper_uses_exact_transcript_and_rejects_other_server(self):
        exact = b"JKADMIN1\n" + b"a" * 32 + b"\n" + b"c" * 32 + b"\n" + b"b" * 16
        mac = hmac.new(bytes.fromhex("01" * 32), exact, hashlib.sha256).hexdigest()
        result = proof_for(parse_credential(self.text), self.challenge)
        self.assertEqual(result, "admin prove " + "b" * 16 + " " + mac)
        self.assertLessEqual(len(result), 127)
        self.assertNotEqual(mac, hmac.new(bytes.fromhex("01" * 32), exact + b"\n", hashlib.sha256).hexdigest())
        with self.assertRaises(CredentialError):
            proof_for(self.key, "JKADMIN1:" + "d" * 32 + ":" + "c" * 32)

    def test_only_exact_inert_container_and_canonical_metadata_are_accepted(self):
        self.assertEqual(parse_credential(self.text.replace("\n", "\r\n")), self.key)
        altered = [self.text + "startup:\nReturn;\n", self.text.replace("code\nend", "code\nstartup:\nReturn;\nend"),
                   self.text.replace('"version":1', '"version":1,"version":1'),
                   self.text.replace('"secret":', '"extra":0,"secret":'),
                   self.text.replace('"version":1', '"version":true'), self.text.replace("\n", "\v")]
        for text in altered:
            with self.subTest(change=altered.index(text)), self.assertRaises(CredentialError):
                parse_credential(text)

    def test_standalone_cli_works_without_repository_imports_and_redacts_errors(self):
        with tempfile.TemporaryDirectory(prefix="jk-offline-helper-") as directory:
            root = Path(directory)
            helper = root / "admin_key.py"
            shutil.copyfile(ROOT / "tools/admin_key.py", helper)
            key = root / "private-fixture.cog"
            key.write_text(self.text)
            result = subprocess.run([sys.executable, "-I", str(helper), "--key", str(key), "--challenge", self.challenge],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), proof_for(self.key, self.challenge))
            bad = subprocess.run([sys.executable, "-I", str(helper), "--key", str(key), "--challenge", "wrong"],
                                 capture_output=True, text=True, timeout=5)
            self.assertNotEqual(bad.returncode, 0)
            self.assertNotIn(self.key["secret"], bad.stdout + bad.stderr)
            self.assertNotIn(str(key), bad.stdout + bad.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node required to exercise the browser helper's actual Web Crypto")
    def test_browser_helper_actual_webcrypto_matches_cli_and_rejects_malformed_key(self):
        source = """
const helper=require(process.argv[1]),crypto=require('crypto').webcrypto;
let input='';process.stdin.on('data',chunk=>input+=chunk);process.stdin.on('end',async()=>{
 const v=JSON.parse(input),key=helper.parseCredential(v.text);
 const proof=await helper.proofFor(key,v.challenge,crypto);
 let rejected=0;
 for(const text of [v.text+'code\\n',v.text.replace('"version":1','"version":1,"version":1')]){
  try{helper.parseCredential(text);}catch(_){rejected++;}
 }
 let wrongServer=false;try{await helper.proofFor(key,'JKADMIN1:'+('d'.repeat(32))+':'+('c'.repeat(32)),crypto);}catch(_){wrongServer=true;}
 process.stdout.write(JSON.stringify({proof,rejected,wrongServer}));
});
"""
        result = subprocess.run(["node", "-e", source, str(ROOT / "tools/admin-helper.js")],
                                input=json.dumps({"text": self.text, "challenge": self.challenge}),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["proof"], proof_for(self.key, self.challenge))
        self.assertEqual(output["rejected"], 2)
        self.assertTrue(output["wrongServer"])


class AuthorityApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jk-authority-api-")
        self.store = AuthorityStore(Path(self.temp.name) / "authority")
        self.policy = GameAuthority(self.store)
        self.manager = types.SimpleNamespace(authority_store=self.store,
                                             chat_admin=types.SimpleNamespace(authority=self.policy))
        self.token = "private-test-panel-token-only"
        self.runner = web.AppRunner(create_admin_app(self.manager, port=None, token=self.token), access_log=None)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        self.base = "http://127.0.0.1:" + str(self.site._server.sockets[0].getsockname()[1])
        self.client = ClientSession(headers={"Authorization": "Bearer " + self.token})

    async def asyncTearDown(self):
        await self.client.close()
        await self.runner.cleanup()
        self.temp.cleanup()

    async def issue(self):
        response = await self.client.post(self.base + "/api/admin-keys", json={"label": "Private API fixture", "capabilities": ["match.next"]})
        self.assertEqual(response.status, 200, await response.text() if response.status != 200 else "")
        text = await response.text()
        return response, parse_credential(text)

    async def test_api_guard_and_metadata_are_side_effect_free(self):
        async with ClientSession() as anonymous:
            for method in ("get", "post"):
                response = await getattr(anonymous, method)(self.base + "/api/admin-keys")
                self.assertEqual(response.status, 401)
        response = await self.client.post(self.base + "/api/admin-keys", headers={"Origin": "https://unrelated.invalid"},
                                          json={"label": "No issuance", "capabilities": ["match.next"]})
        self.assertEqual(response.status, 403)
        response = await self.client.get(self.base + "/api/admin-keys")
        self.assertIsNone((await response.json())["server_id"])
        self.assertFalse(self.store.directory.exists())

    async def test_one_time_attachment_and_sanitized_list_never_reexport_secret(self):
        response, key = await self.issue()
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
        self.assertIn("jk-admin-key-" + key["key_id"] + ".cog", response.headers["Content-Disposition"])
        response = await self.client.get(self.base + "/api/admin-keys")
        body = await response.text()
        self.assertNotIn(key["secret"], body)
        self.assertNotIn('"secret"', body)
        self.assertEqual(json.loads(body)["credentials"][0]["id"], key["key_id"])
        response = await self.client.get(self.base + "/api/admin-keys/" + key["key_id"])
        self.assertEqual(response.status, 404)

    async def test_supplied_secrets_or_unrecognized_fields_are_rejected_without_issuance(self):
        for body in ({"label": "No", "capabilities": ["match.next"], "secret": "never-echo-this"},
                     {"label": "No", "capabilities": []}, {"label": "No", "capabilities": ["console"]}):
            response = await self.client.post(self.base + "/api/admin-keys", json=body)
            self.assertEqual(response.status, 400)
            self.assertNotIn("never-echo-this", await response.text())
        self.assertFalse(self.store.directory.exists())

    async def test_revoke_invalidates_live_policy_and_rotation_is_serialized(self):
        _, key = await self.issue()
        answer = proof_for(key, self.policy.begin(42, 1)).split()[2:]
        self.policy.prove(42, 1, *answer)
        self.assertTrue(self.policy.authorized(42, 1))
        response = await self.client.post(self.base + "/api/admin-keys/" + key["key_id"] + "/revoke")
        self.assertEqual(response.status, 200)
        self.assertFalse(self.policy.authorized(42, 1))
        _, key = await self.issue()
        url = self.base + "/api/admin-keys/" + key["key_id"] + "/rotate"
        results = await asyncio.gather(self.client.post(url), self.client.post(url))
        self.assertEqual(sorted(r.status for r in results), [200, 400])
        for response in results:
            await response.read()
        rows = self.store.metadata()["credentials"]
        self.assertEqual(sum(row["status"] == "active" for row in rows), 1)

    async def test_offline_helpers_are_public_downloads_with_no_key_material(self):
        async with ClientSession() as anonymous:
            response = await anonymous.get(self.base + "/admin-helper.zip")
            self.assertEqual(response.status, 200)
            self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
            with zipfile.ZipFile(io.BytesIO(await response.read())) as bundle:
                self.assertEqual(set(bundle.namelist()), {"admin-helper.html", "admin-helper.js", "admin-helper.css"})
                self.assertIn(b"connect-src 'none'", bundle.read("admin-helper.html"))
                self.assertNotIn(b"<script>", bundle.read("admin-helper.html"))
            response = await anonymous.get(self.base + "/admin-helper.py")
            self.assertEqual(response.status, 200)
            self.assertIn(b"import hmac", await response.read())
        self.assertFalse(self.store.directory.exists())


if __name__ == "__main__":
    unittest.main()
