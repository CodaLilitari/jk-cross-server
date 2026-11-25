"""Use one private companion credential to observe or control its bot."""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from . import tactics
from .companion import MODES


def load_private(path):
    if os.name == "nt":
        attrs = os.lstat(path).st_file_attributes
        if attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Select a regular local credential or lease.")
        # Windows does not interpret mode 0600. Verify allow entries against
        # the current Windows SID; use an environment value for the literal
        # path so no user-controlled text can become PowerShell code.
        script = ("$ErrorActionPreference='Stop'; "
                  "$a=Get-Acl -LiteralPath $env:JK_COMPANION_CHECK_PATH; "
                  "$id=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
                  "$r=$a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]); "
                  "if (@($r | Where-Object { $_.AccessControlType -eq 'Allow' -and "
                  "$_.IdentityReference.Value -ne $id }).Count -ne 0) { exit 1 }; exit 0")
        checked = subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],
                                 env={**os.environ, "JK_COMPANION_CHECK_PATH":str(Path(path).resolve())},
                                 capture_output=True)
        if checked.returncode:
            raise ValueError("Windows credential or lease permissions must be restricted to your account.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "r", encoding="utf-8") as f:
        info = os.fstat(f.fileno())
        unsafe_posix = os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077)
        if not stat.S_ISREG(info.st_mode) or unsafe_posix or info.st_size > 4096:
            raise ValueError(f"Expected a private, owned, regular credential or lease file: {path}")
        return json.load(f)


def call(cred, route, body=None):
    url = urlsplit(cred["url"])
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or
            url.netloc != f"127.0.0.1:{url.port}" or url.path or url.query or url.fragment
            or not re.fullmatch(r"[a-z0-9_-]{1,32}", cred["bot_id"])):
        raise ValueError("Credential must identify a loopback companion.")
    conn = http.client.HTTPConnection("127.0.0.1", url.port, timeout=3)
    try:
        conn.request("GET" if body is None else "POST", "/v1/bots/"+cred["bot_id"]+"/"+route,
                     None if body is None else json.dumps(body),
                     {"Authorization": "Bearer "+cred["token"], "Content-Type": "application/json"})
        response = conn.getresponse()
        raw = response.read(128*1024+1)
        if len(raw) > 128*1024:
            raise ValueError("Oversized companion response.")
        result = json.loads(raw)
        if response.status >= 400:
            raise ValueError(f"HTTP {response.status}: {result.get('error', 'request failed')}")
        return result
    finally:
        conn.close()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--credentials", required=True, type=Path, help="Private BOT.json from the current run.")
    p.add_argument("--lease-file", type=Path, help="Local lease ticket (default beside the credential).")
    sub = p.add_subparsers(dest="op", required=True)
    for op in ("capabilities", "observe", "renew"):
        sub.add_parser(op)
    sub.add_parser("tactics-info", help="Tactic table, presets and the adjustments applied so far.")
    sub.add_parser("attach").add_argument("controller")
    sub.add_parser("events").add_argument("--after", default=0, type=int)
    sub.add_parser("command").add_argument("request_id")
    for name in ("strategy", "say", "release", "tactics"):
        action = sub.add_parser(name)
        action.add_argument("--request-id", help="Reuse the same ID and payload to inspect a retry.")
        action.add_argument("--wait", default=1., type=float, help="Seconds to poll for the native ACK (0..10).")
        if name == "strategy":
            action.add_argument("mode", choices=MODES)
            action.add_argument("--ttl-seconds", type=float)
            action.add_argument("--risk", type=float)
            action.add_argument("--range", type=float)
            for field in ("weapon", "resource", "focus-net-id", "focus-guid"):
                action.add_argument("--"+field, type=int)
        elif name == "say":
            action.add_argument("text")
        elif name == "tactics":
            action.add_argument("--preset", choices=sorted(tactics.PRESETS),
                                help="Reset to the defaults, then apply this preset.")
            action.add_argument("--set", action="append", metavar="NAME=VALUE",
                                help="Set one tactic; repeatable. Merged over the preset or the current table.")
            action.add_argument("--reset", action="store_true",
                                help="Reset to the defaults before applying --set values.")
    return p


def execute(args):
    cred = load_private(args.credentials)
    ticket = args.lease_file or args.credentials.with_suffix(".lease.json")
    op = args.op
    if op in ("capabilities", "observe", "events", "command", "tactics-info"):
        if op == "command":
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.request_id):
                raise ValueError("Invalid request identifier.")
            route = "commands/" + args.request_id
        elif op == "events":
            route = "events?after=" + str(args.after)
        else:
            route = "observation" if op == "observe" else "tactics" if op == "tactics-info" else op
        return call(cred, route)
    if op == "attach":
        # An expired ticket can be replaced. The hub itself serializes attach
        # requests, so no second caller can replace an active controller.
        if ticket.exists():
            stored = load_private(ticket)
            if type(stored) is not dict or set(stored) != {"run_id","world_epoch","life_epoch","lease_id"}:
                raise ValueError("Existing lease file is not a companion ticket.")
        fd, temp = tempfile.mkstemp(prefix=".lease-", dir=ticket.parent)
        try:
            with os.fdopen(fd, "w") as f:
                state = call(cred, "observation")
                fence = {k:state[k] for k in ("run_id","world_epoch","life_epoch")}
                if fence["run_id"] != cred["run_id"]:
                    raise ValueError("The running hub differs from the credential's run.")
                result = call(cred, op, dict(fence, controller=args.controller))
                json.dump(dict(fence, lease_id=result["lease_id"]), f)
            os.replace(temp, ticket)
        finally:
            Path(temp).unlink(missing_ok=True)
        return dict(fence, lease_file=str(ticket), expires_in=result["expires_in"])
    lease = load_private(ticket)
    if lease["run_id"] != cred["run_id"]:
        raise ValueError("Lease belongs to a previous run.")
    if op == "renew":
        result = call(cred, op, lease)
        return {k:v for k,v in result.items() if k != "lease_id"}
    if not 0 <= args.wait <= 10:
        raise ValueError("--wait must be in 0..10 seconds.")
    body = dict(lease, request_id=args.request_id or secrets.token_hex(12))
    if op == "say":
        body["text"] = args.text
    if op == "tactics":
        values = tactics.parse_assignments(args.set)
        tactics.resolve(args.preset, values, args.reset)
        if args.preset:
            body["preset"] = args.preset
        if values:
            body["values"] = values
        if args.reset:
            body["reset"] = True
    if op == "strategy":
        for key in ("mode","risk","range","weapon","resource","focus_net_id","focus_guid","ttl_seconds"):
            value = getattr(args, key)
            if value is not None:
                body[key] = value
    result = call(cred, op, body)
    if op == "release":
        ticket.unlink(missing_ok=True)
    deadline = time.monotonic() + args.wait
    while result["status"] == "pending" and time.monotonic() < deadline:
        time.sleep(.05)
        result = call(cred, "commands/"+body["request_id"])
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException) as exc:
        print(f"Companion: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
