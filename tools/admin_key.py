#!/usr/bin/env python3
"""Generate a JK chat-admin proof offline; never load or execute the key COG."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys


HEADER = "# JK Cross Server offline admin credential. Keep outside game content."
PREFIX = "# JKADMIN-KEY-V1 "
CAPABILITIES = ("match.next", "player.kick")
FIELDS = {"format", "version", "server_id", "key_id", "secret", "label", "capabilities"}
MAX_CREDENTIAL_BYTES = 16384
HEX16 = re.compile(r"[0-9a-f]{16}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CHALLENGE = re.compile(r"JKADMIN1:([0-9a-f]{32}):([0-9a-f]{32})\Z")


class CredentialError(ValueError):
    """An input is not a valid credential or challenge; messages contain no key."""


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def validate_credential(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise CredentialError("The credential metadata schema is invalid.")
    if value["format"] != "JKADMIN-KEY" or type(value["version"]) is not int or value["version"] != 1:
        raise CredentialError("This credential version is unsupported.")
    for name, pattern in (("server_id", HEX32), ("key_id", HEX16), ("secret", HEX64)):
        if not isinstance(value[name], str) or not pattern.fullmatch(value[name]):
            raise CredentialError("The credential identifiers or secret have an invalid format.")
    label = value["label"]
    if (not isinstance(label, str) or not 1 <= len(label) <= 80 or label != label.strip()
            or any(not 32 <= ord(c) <= 126 for c in label)):
        raise CredentialError("The credential label must use 1–80 printable ASCII characters.")
    caps = value["capabilities"]
    if (not isinstance(caps, list) or not 1 <= len(caps) <= len(CAPABILITIES)
            or any(not isinstance(c, str) or c not in CAPABILITIES for c in caps)
            or caps != sorted(set(caps))):
        raise CredentialError("The credential capability list is invalid.")
    return value


def render_credential(value: dict) -> str:
    validate_credential(value)
    return HEADER + "\n" + PREFIX + canonical(value) + "\nsymbols\nend\ncode\nend\n"


def parse_credential(text: str) -> dict:
    if not isinstance(text, str) or len(text) > MAX_CREDENTIAL_BYTES or not text.isascii():
        raise CredentialError("Choose an unmodified JK admin key file.")
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    if (len(lines) != 6 or lines[0] != HEADER or not lines[1].startswith(PREFIX)
            or lines[2:] != ["symbols", "end", "code", "end"]):
        raise CredentialError("The key file must be the inert issued credential container.")
    encoded = lines[1][len(PREFIX):]
    try:
        value = json.loads(encoded)
    except (ValueError, TypeError):
        raise CredentialError("The credential metadata is not valid JSON.") from None
    validate_credential(value)
    # Exact canonical metadata also rejects duplicate JSON keys and appended code.
    if encoded != canonical(value):
        raise CredentialError("The credential metadata has been changed or duplicated.")
    return value


def proof_for(credential: dict, challenge: str) -> str:
    value = validate_credential(credential)
    match = CHALLENGE.fullmatch(challenge) if isinstance(challenge, str) else None
    if not match:
        raise CredentialError("Paste the complete JKADMIN1 challenge exactly.")
    server_id, nonce = match.groups()
    if not hmac.compare_digest(server_id, value["server_id"]):
        raise CredentialError("This challenge belongs to a different server.")
    message = f"JKADMIN1\n{server_id}\n{nonce}\n{value['key_id']}".encode("ascii")
    mac = hmac.new(bytes.fromhex(value["secret"]), message, hashlib.sha256).hexdigest()
    return f"admin prove {value['key_id']} {mac}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", required=True, type=Path, help="Issued jk-admin-key-*.cog, outside game content")
    parser.add_argument("--challenge", required=True, help="Exact private server challenge beginning JKADMIN1:")
    args = parser.parse_args(argv)
    try:
        if not args.key.is_file() or args.key.stat().st_size > MAX_CREDENTIAL_BYTES:
            raise CredentialError("Choose an issued admin key file smaller than 16 KiB.")
        value = parse_credential(args.key.read_text(encoding="ascii"))
        print(proof_for(value, args.challenge))
        return 0
    except (OSError, UnicodeError, CredentialError):
        # File paths, key material and supplied input never appear in diagnostics.
        print("Unable to create a proof: verify the issued key file and exact challenge for that server.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
