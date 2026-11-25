"""A small coach: try tactic presets on a live bot and keep what scores.

The bot plays on its own. Through the companion API the coach reads its
score, holds one preset for a fixed spell, grades that spell by kills minus
deaths per minute, and picks the next preset by the UCB1 rule, which keeps
returning to what has worked while still testing the alternatives. A preset
is never changed before its spell has run and produced at least one kill or
death, so the bot cannot be flipped between plans faster than a plan can
show a result. The engine enforces its own shorter commitment window as well.

Results persist in a memory file under a label of your choosing (a map, an
opponent, a rule set), so a later session resumes from what earlier ones
learned. This is a starting point for a smarter coach, and has not yet been
through a live match.

    python -m bots.coach --credentials RUN/companion/BOT.json \\
        --memory runtime/coach.json --label oasis-ff-guns
"""
from __future__ import annotations

import argparse
import http.client
import json
import math
from pathlib import Path
import secrets
import sys
import time

from . import tactics
from .companion_cli import call, load_private


class Bandit:
    """UCB1 over a fixed set of arms, with an explicit, serialisable record."""
    def __init__(self, arms, exploration=1.0, record=None):
        self.arms = list(arms)
        if not self.arms or len(set(self.arms)) != len(self.arms):
            raise ValueError("Give at least one arm, each once.")
        self.exploration = exploration
        self.plays = {arm: 0 for arm in self.arms}
        self.total = {arm: 0.0 for arm in self.arms}
        for arm, row in (record or {}).items():
            if arm in self.plays and type(row) is dict:
                plays, total = row.get("plays"), row.get("total")
                if type(plays) is int and plays >= 0 and type(total) in (int, float) and math.isfinite(total):
                    self.plays[arm], self.total[arm] = plays, float(total)

    def choose(self) -> str:
        for arm in self.arms:
            if not self.plays[arm]:
                return arm
        rounds = sum(self.plays.values())
        def bound(arm):
            return (self.total[arm] / self.plays[arm]
                    + self.exploration * math.sqrt(2 * math.log(rounds) / self.plays[arm]))
        return max(self.arms, key=bound)

    def record(self, arm: str, reward: float) -> None:
        self.plays[arm] += 1
        self.total[arm] += reward

    def export(self) -> dict:
        return {arm: {"plays": self.plays[arm], "total": self.total[arm]} for arm in self.arms}


class Coach:
    """Decides when a spell ends and which preset the next one uses."""
    def __init__(self, bandit: Bandit, dwell_seconds=90.0, patience=3.0):
        if dwell_seconds < tactics.COMMIT_SECONDS:
            raise ValueError(f"A spell must last at least {tactics.COMMIT_SECONDS} seconds.")
        self.bandit, self.dwell, self.patience = bandit, dwell_seconds, patience
        self.current = None
        self.since = self.kills = self.deaths = 0

    def begin(self, preset: str, state: dict, now: float) -> None:
        """Call once the engine has acknowledged the preset as applied."""
        self.current, self.since = preset, now
        self.kills, self.deaths = state["kills"], state["deaths"]

    def step(self, state: dict, now: float) -> str | None:
        """Return the preset to apply now, or None to keep playing."""
        if self.current is None:
            return self.bandit.choose()
        elapsed = now - self.since
        kills, deaths = state["kills"] - self.kills, state["deaths"] - self.deaths
        if kills < 0 or deaths < 0:  # a new match reset the score
            self.kills, self.deaths, self.since = state["kills"], state["deaths"], now
            return None
        # Grade only a spell with evidence. A spell in which nothing happened
        # ends after patience x dwell and counts as a draw.
        if elapsed < self.dwell or (not kills and not deaths and elapsed < self.dwell * self.patience):
            return None
        reward = max(-4.0, min(4.0, (kills - deaths) * 60.0 / elapsed))
        self.bandit.record(self.current, reward)
        chosen = self.bandit.choose()
        if chosen == self.current:
            self.begin(chosen, state, now)  # same plan, new spell: nothing to send
            return None
        return chosen


def load_memory(path: Path | None, label: str) -> dict:
    if path is None or not path.is_file():
        return {}
    stored = json.loads(path.read_text(encoding="utf-8"))
    return stored.get(label, {}) if type(stored) is dict else {}


def save_memory(path: Path | None, label: str, record: dict) -> None:
    if path is None:
        return
    stored = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if type(stored) is not dict:
        stored = {}
    stored[label] = record
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def session(cred, coach: Coach, *, memory=None, label="default", seconds=0.0, poll=5.0,
            clock=time.monotonic, sleep=time.sleep, request=call, log=print) -> None:
    """Coach until interrupted or `seconds` pass, then release the bot.

    The hub drops a controller's lease whenever the bot dies or the map
    changes, so the lease is taken again whenever the fence has moved.
    """
    started, lease, pending = clock(), None, None
    try:
        while not seconds or clock() - started < seconds:
            try:
                observed = request(cred, "observation")
                fence = {key: observed[key] for key in ("run_id", "world_epoch", "life_epoch")}
                if lease is None or any(lease[key] != fence[key] for key in fence):
                    lease = pending = None
                    if observed["native_active"]:
                        ticket = request(cred, "attach", dict(fence, controller="coach"))
                        lease = dict(fence, lease_id=ticket["lease_id"])
                else:
                    request(cred, "renew", lease)
                now = clock()
                if lease and pending:
                    result = request(cred, "commands/" + pending[1])
                    if result["status"] == "applied":
                        coach.begin(pending[0], observed["state"], now)
                        log(f"coach: playing {pending[0]}")
                    if result["status"] != "pending":
                        pending = None  # refused or lost: decide again on the next pass
                elif lease:
                    before = dict(coach.bandit.plays)
                    preset = coach.step(observed["state"], now)
                    if coach.bandit.plays != before:
                        save_memory(memory, label, coach.bandit.export())
                    if preset:
                        key = secrets.token_hex(12)
                        request(cred, "tactics", dict(lease, request_id=key, preset=preset))
                        pending = (preset, key)
            except ValueError as error:
                # The hub refused: the fence moved mid-pass, or another
                # controller holds the bot. Start the next pass clean.
                log(f"coach: {error}")
                lease = pending = None
            sleep(poll)
    finally:
        if lease:
            try:
                request(cred, "release", dict(lease, request_id=secrets.token_hex(12)))
            except (OSError, ValueError, KeyError, http.client.HTTPException):
                pass  # the lease lapses on its own within 30 seconds


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--credentials", required=True, type=Path, help="Private BOT.json from the current run.")
    parser.add_argument("--presets", default="default,arsenal,hunter,standoff,dry",
                        help="Comma-separated presets to choose among.")
    parser.add_argument("--dwell-seconds", type=float, default=90.0, help="Shortest spell on one preset.")
    parser.add_argument("--memory", type=Path, help="JSON file that keeps results between sessions.")
    parser.add_argument("--label", default="default", help="Which record in the memory file to use.")
    parser.add_argument("--seconds", type=float, default=0.0, help="Stop after this long; 0 runs until interrupted.")
    args = parser.parse_args(argv)
    try:
        arms = [name for name in args.presets.split(",") if name]
        unknown = [name for name in arms if name not in tactics.PRESETS]
        if unknown:
            raise ValueError("Unknown presets: " + ", ".join(unknown))
        coach = Coach(Bandit(arms, record=load_memory(args.memory, args.label)), args.dwell_seconds)
        session(load_private(args.credentials), coach, memory=args.memory, label=args.label, seconds=args.seconds)
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException) as error:
        print(f"Coach: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
