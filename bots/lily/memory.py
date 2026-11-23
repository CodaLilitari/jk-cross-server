"""Durable outcome evidence keyed by geometry, independently of native node IDs."""
import json
import math
import sqlite3

from .bank_task import bank_verdict


def packed(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)


def geometry(environment, position, direction):
    cells = [math.floor(v * 2) for v in position]
    heading = round(math.atan2(direction[1], direction[0]) * 4 / math.pi) % 8
    vertical = 0 if abs(direction[2]) <= .3 * math.hypot(*direction) else (1 if direction[2] > 0 else -1)
    return [environment, cells, heading, vertical]


def route_key(environment, offer, origin):
    position = offer["position"]
    delta = [b - a for a, b in zip(origin, position)]
    return packed(["route", *geometry(environment, position, delta), offer["sector"], offer["class"], offer["item_bin"]])


def skill_key(environment, skill, sense, direction):
    return packed(["motor", *geometry(environment, sense["position"], direction), skill,
                   sense["medium"], bool(sense["supported"])])


def episode_id(record):
    return "/".join(str(record[k]) for k in ("run_id", "world_epoch", "life_epoch", "action_seq"))


class ExperienceStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=1)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS attempts (
                episode TEXT PRIMARY KEY, environment_key TEXT NOT NULL,
                identity TEXT NOT NULL, outcome TEXT, success INTEGER, duration REAL
            );
            CREATE INDEX IF NOT EXISTS conditions ON attempts(environment_key, success);
            CREATE TABLE IF NOT EXISTS submissions (
                run TEXT NOT NULL, request TEXT NOT NULL, intent TEXT NOT NULL,
                disposition TEXT NOT NULL, episode TEXT UNIQUE, admitted INTEGER DEFAULT 0 NOT NULL,
                PRIMARY KEY (run, request)
            );
            CREATE INDEX IF NOT EXISTS pending_submissions ON submissions(run, disposition);
            CREATE TABLE IF NOT EXISTS bank_tasks (
                task_id TEXT PRIMARY KEY, run TEXT NOT NULL, identity TEXT NOT NULL, outcome TEXT
            );
            CREATE INDEX IF NOT EXISTS open_banks ON bank_tasks(run) WHERE outcome IS NULL;
            CREATE TABLE IF NOT EXISTS bank_children (
                episode TEXT PRIMARY KEY REFERENCES attempts(episode),
                task_id TEXT NOT NULL REFERENCES bank_tasks(task_id)
            );
            CREATE TABLE IF NOT EXISTS transitions (
                episode TEXT NOT NULL, phase TEXT NOT NULL, evidence TEXT NOT NULL,
                PRIMARY KEY (episode, phase)
            );
        """)

    def prepare(self, intent):
        """Commit the exact credential-free intent before the transport can see it."""
        with self.db:
            self.db.execute("INSERT INTO submissions(run,request,intent,disposition) VALUES(?,?,?,'prepared')",
                            (intent["run_id"], intent["request_id"], packed(intent)))

    def request_floor(self, run_id):
        # Request serials are unsigned decimal and may exceed sqlite's int64 range.
        row = self.db.execute("SELECT request FROM submissions WHERE run=? "
                              "ORDER BY length(request) DESC, request DESC LIMIT 1", (run_id,)).fetchone()
        return int(row[0][5:]) if row else 0

    def unresolved(self, run_id):
        rows = self.db.execute("SELECT intent FROM submissions WHERE run=? "
                               "AND disposition IN ('prepared','unconfirmed') ORDER BY rowid", (run_id,))
        return [json.loads(raw) for (raw,) in rows]

    def pending_admissions(self, run_id):
        """Already-bound open children whose positive native receipt may have arrived late."""
        rows = self.db.execute(
            "SELECT a.identity FROM submissions s JOIN attempts a ON a.episode=s.episode "
            "WHERE s.run=? AND s.disposition='linked' AND s.admitted=0 AND a.outcome IS NULL "
            "ORDER BY s.rowid", (run_id,))
        return [json.loads(raw) for (raw,) in rows]

    def disposition(self, intent, status):
        with self.db:
            self.db.execute("UPDATE submissions SET disposition=? WHERE run=? AND request=? AND episode IS NULL",
                            (status, intent["run_id"], intent["request_id"]))

    def bind(self, intent, seq):
        """Atomically bind the pre-dispatch identity and its native episode."""
        attempt = {k: v for k, v in intent.items() if k not in ("command", "ttl_seconds")}
        attempt["action_seq"] = seq
        episode = episode_id(attempt)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO attempts(episode,environment_key,identity) VALUES(?,?,?)",
                            (episode, attempt["key"], packed(attempt)))
            self.db.execute("UPDATE submissions SET episode=?,disposition='linked' WHERE run=? AND request=?",
                            (episode, intent["run_id"], intent["request_id"]))
        return attempt, episode

    def admitted(self, episode, task_id=None):
        with self.db:
            updated = self.db.execute("UPDATE submissions SET admitted=1 WHERE episode=?", (episode,))
            if task_id and updated.rowcount:
                self.db.execute("INSERT OR IGNORE INTO bank_children(episode,task_id) "
                                "SELECT ?,task_id FROM bank_tasks WHERE task_id=?", (episode, task_id))

    def bank(self, task_id):
        row = self.db.execute("SELECT identity,outcome FROM bank_tasks WHERE task_id=?", (task_id,)).fetchone()
        return (json.loads(row[0]), json.loads(row[1]) if row[1] else None) if row else None

    def begin_bank(self, record):
        with self.db:
            inserted = self.db.execute("INSERT OR IGNORE INTO bank_tasks(task_id,run,identity) VALUES(?,?,?)",
                                       (record["task_id"], record["run_id"], packed(record)))
        return inserted.rowcount == 1

    def finish_bank(self, task_id, outcome):
        with self.db:
            updated = self.db.execute("UPDATE bank_tasks SET outcome=? WHERE task_id=? AND outcome IS NULL",
                                      (packed(outcome), task_id))
        return updated.rowcount == 1

    def recover_banks(self, run):
        """Censor abandoned commitments only after obtaining exclusive control of this run."""
        outcome = dict(bank_verdict(terminal="restarted", controller="candidate", wet_takeover=False,
                                    baseline_assisted=False, ownership_complete=False), evidence="live_sampled",
                       reason="exclusive_owner_recovery")
        with self.db:
            # UPDATE ... RETURNING would exclude older SQLite versions used by the server.
            self.db.execute("BEGIN IMMEDIATE")
            rows = self.db.execute("SELECT identity FROM bank_tasks WHERE run=? AND outcome IS NULL", (run,)).fetchall()
            self.db.execute("UPDATE bank_tasks SET outcome=? WHERE run=? AND outcome IS NULL", (packed(outcome), run))
        return [(json.loads(raw), outcome) for (raw,) in rows]

    def begin(self, attempt):
        episode = episode_id(attempt)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO attempts(episode,environment_key,identity) VALUES(?,?,?)",
                            (episode, attempt["key"], packed(attempt)))
        return episode

    def transition(self, episode, progress):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO transitions VALUES(?,?,?)",
                            (episode, progress["phase"], packed(progress)))

    def finish(self, episode, outcome):
        success = outcome["physical_success"]
        if success is not None and type(success) is not bool:
            raise ValueError("Expected a physical verdict or null.")
        with self.db:
            updated = self.db.execute(
                "UPDATE attempts SET outcome=?,success=?,duration=? WHERE episode=? AND outcome IS NULL",
                (packed(outcome), success, outcome["duration_seconds"], episode))
        return updated.rowcount == 1

    def recover(self, run_id):
        """Only the new, exclusive controller calls this after acquiring a lease."""
        lost = {"status": "owner_lost", "physical_success": None, "duration_seconds": None,
                "applied_ms": None, "damage": None, "item_gain": {}}
        with self.db:
            rows = self.db.execute("SELECT episode FROM attempts WHERE instr(episode,?)=1 AND outcome IS NULL",
                                   (run_id + "/",)).fetchall()
            self.db.executemany("UPDATE attempts SET outcome=? WHERE episode=? AND outcome IS NULL",
                                [(packed(lost), eid) for (eid,) in rows])
        return [eid for (eid,) in rows]

    def estimate(self, key):
        attempts, trials, wins, duration = self.db.execute(
            "SELECT count(*),count(success),coalesce(sum(success),0),avg(CASE WHEN success IS NOT NULL THEN duration END) FROM attempts "
            "WHERE environment_key=? AND NOT EXISTS (SELECT 1 FROM submissions s "
            "WHERE s.episode=attempts.episode AND s.admitted=0)", (key,)).fetchone()
        return {"attempts": attempts, "trials": trials, "wins": wins, "probability": (wins + 1) / (trials + 2),
                "mean_seconds": duration}

    def close(self):
        self.db.close()
