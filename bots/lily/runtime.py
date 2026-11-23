"""Fence one companion controller, stage exact policy bytes, and retain observed outcomes."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import stat
import subprocess
import sys
import threading
import time

from . import protocol
from .bank_task import BankTask, bank_id, bank_parameters, bank_verdict, finite_number
from .memory import route_key, skill_key
from .motor_model import remaining_goal
from .worker import MAX_DECISION, MAX_SOURCE, encode, read

IDENT = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
FENCE = ("run_id", "world_epoch", "life_epoch")
STATE_FIELDS = ("health", "shields", "mana", "weapon", "ammo", "kills", "deaths", "position", "game_time")
TERMINAL = {"completed", "interrupted", "failed", "expired"}
MOTOR_SKILLS = ("forward-probe", "sidestep")


def regular_bytes(path, bound):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Expected a regular file")
    with path.open("rb") as f:
        data = f.read(bound + 1)
    if len(data) > bound:
        raise ValueError("Local file exceeds limit")
    return data


class WorkerFault(ValueError):
    """A safe diagnostic code that may appear in a private trace."""


class Worker:
    """One reader/writer thread and one outstanding operation, including startup."""
    def __init__(self, source, startup_timeout):
        self.source = source
        self.digest = hashlib.sha256(source).hexdigest()
        self.revision = int(self.digest[:8], 16) or 1
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-u", str(Path(__file__).with_name("worker.py").resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.requests = queue.Queue(maxsize=1)
        self.responses = queue.Queue(maxsize=1)
        self.closed = threading.Event()
        self.phase = "startup"
        self.state_version = None
        self.ticket = None
        self.deadline = time.monotonic() + startup_timeout
        stage = {"source": base64.b64encode(source).decode("ascii"), "digest": self.digest}
        self.requests.put_nowait(encode(stage))
        self.thread = threading.Thread(target=self._exchange, daemon=True, name="lily-policy-pipe")
        self.thread.start()

    def _exchange(self):
        try:
            with self.process.stdin as sink, self.process.stdout as source:
                while not self.closed.is_set():
                    packet = self.requests.get()
                    if packet is None:
                        break
                    sink.write(packet)
                    sink.flush()
                    reply = read(source, MAX_DECISION)
                    self.responses.put_nowait((time.monotonic(), reply))
        except (OSError, ValueError, RecursionError, queue.Full):
            try:
                self.responses.put_nowait((time.monotonic(), {"error": "pipe"}))
            except queue.Full:
                pass
        finally:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()

    def decide(self, observation, context, ticket, timeout):
        self.phase = "decision"
        self.ticket = ticket
        self.deadline = time.monotonic() + timeout
        self.requests.put_nowait(encode({"observation": observation, "context": context}))

    def poll(self):
        try:
            arrived, reply = self.responses.get_nowait()
        except queue.Empty:
            if self.phase in ("startup", "decision") and time.monotonic() >= self.deadline:
                raise WorkerFault(self.phase + "_timeout")
            if self.process.poll() is not None:
                raise WorkerFault("worker_exit")
            return None
        if arrived > self.deadline:
            raise WorkerFault(self.phase + "_timeout")
        if "error" in reply:
            raise WorkerFault(self.phase + "_error")
        if self.phase == "startup":
            if reply.get("ready") is not True:
                raise WorkerFault("invalid_handshake")
            self.state_version = reply.get("state_version")
            self.phase = "idle"
            return None
        if self.phase != "decision" or "decision" not in reply:
            raise WorkerFault("invalid_reply")
        self.phase = "idle"
        return reply["decision"], self.ticket

    def close(self):
        self.closed.set()
        if self.process.poll() is None:
            self.process.kill()
        try:
            self.requests.put_nowait(None)
        except queue.Full:
            pass


def normalized_goal(value):
    if type(value) is not dict or set(value) != {"direction", "distance"}:
        raise ValueError("invalid_goal")
    vector = value["direction"]
    if type(vector) is not list or len(vector) != 3 or not all(type(v) in (int, float) for v in vector):
        raise ValueError("invalid_direction")
    length = math.hypot(*vector)
    distance = value["distance"]
    if not math.isfinite(length) or length < .001 or type(distance) not in (int, float) or not .001 <= distance <= 100:
        raise ValueError("invalid_distance")
    return {"direction": [v / length for v in vector], "distance": distance}


def decision(result, obs, worker):
    if type(result) is not dict:
        raise ValueError("invalid_decision")
    action = result.get("action")
    fields = {"action", "state"}
    if action in ("wait", "baseline"):
        pass
    elif action == "route":
        fields.update(("skill", "node"))
    elif action == "motor":
        fields.update(("skill", "steps", "goal", "task_id"))
        if "task_id" in result and (type(result["task_id"]) is not str or
                                    not re.fullmatch(r"[0-9a-f]{64}", result["task_id"])):
            raise ValueError("invalid_task_identity")
    else:
        raise ValueError("unknown_action")
    if set(result) - fields or type(result.get("state", {})) is not dict:
        raise ValueError("unknown_output_fields")
    encode(result.get("state", {}), 8192)
    if action in ("wait", "baseline"):
        return result, {}
    skill = result.get("skill", "navigate" if action == "route" else None)
    if type(skill) is not str or not IDENT.fullmatch(skill):
        raise ValueError("invalid_skill")
    command = dict(revision=worker.revision, sample_id=obs["lily"]["sense"]["sample_id"])
    if action == "route":
        offers = obs["lily"].get("offers")
        if not offers or not any(c["node"] == result.get("node") for c in offers["choices"]):
            raise ValueError("unknown_offer")
        command.update(offer_id=offers["offer_id"], node=result["node"])
        kind = protocol.COMMIT
    else:
        if "goal" in result:
            result = dict(result, goal=normalized_goal(result["goal"]))
        command["steps"] = result.get("steps")
        kind = protocol.MOTOR
    protocol.encode_command(kind, command, 1.)
    return dict(result, skill=skill), command


def get_directive(path, fence):
    if path is None:
        return None
    try:
        directive = json.loads(regular_bytes(path, 8192))
        encode(directive, 8192)
        if type(directive) is not dict or set(directive) != {
            *FENCE, "id", "provenance", "expires_at", "goal", "parameters"
        } or any(directive[k] != fence[k] for k in FENCE):
            return None
        if any(type(directive[k]) is not str or not IDENT.fullmatch(directive[k])
               for k in ("id", "goal", "provenance")):
            return None
        if any(type(directive[k]) is not int for k in ("world_epoch", "life_epoch")):
            return None
        if type(directive["expires_at"]) not in (int, float) or directive["expires_at"] <= time.time():
            return None
        if type(directive["parameters"]) is not dict:
            return None
        return directive
    except (OSError, ValueError, RecursionError, TypeError):
        return None


class Supervisor:
    def __init__(self, policy, memory, environment, transport, *, trace=None, directive_file=None,
                 startup_timeout=2., decision_timeout=.18, stage_interval=.3):
        if not isinstance(environment, str) or not environment.strip() or len(environment) > 128:
            raise ValueError("An explicit environment identity is required")
        self.path = Path(policy)
        self.memory = memory
        self.environment = environment
        self.call = transport
        self.trace = trace or (lambda row: None)
        self.directive_file = Path(directive_file) if directive_file else None
        self.startup_timeout = startup_timeout
        self.decision_timeout = decision_timeout
        self.stage_interval = stage_interval
        self.active = self.candidate = None
        self.retired = []
        self.candidate_ready = False
        self.candidate_scope = None
        self.previous_source = self.seen = None
        self.next_stage = self.renew_at = 0.
        self.lease = self.fence = self.undertaking = None
        self.state = {}
        self.directive = self.bank = None
        self.counter = time.time_ns()
        self.last_sample = self.last_decision = self.last_phase = None
        self.block_until = 0.
        self.block_sample = None
        self.generation = 0
        self.fresh = False

    def emit(self, event, **fields):
        self.trace({"schema": 1, "event": event, "monotonic_seconds": time.monotonic(),
                    **(self.fence or dict.fromkeys(FENCE)), **fields})

    def retire(self, worker):
        if worker:
            worker.close()
            self.retired.append(worker)
        self.retired = [w for w in self.retired if w.thread.is_alive()]

    def stage(self, source):
        self.retire(self.candidate)
        self.candidate = None
        self.candidate = Worker(source, self.startup_timeout)
        self.candidate_ready = False
        self.emit("stage", policy_hash=self.candidate.digest)

    def watch(self, now):
        if now < self.next_stage:
            return
        self.next_stage = now + self.stage_interval
        try:
            source = regular_bytes(self.path, MAX_SOURCE)
        except (OSError, ValueError):
            if self.seen != "unreadable":
                self.emit("rejected", policy_hash=None, reason="unreadable_source")
                self.seen = "unreadable"
                self.retire(self.candidate)
                self.candidate = None
            return
        digest = hashlib.sha256(source).hexdigest()
        if digest == self.seen:
            return
        self.seen = digest
        if self.active and self.active.digest == digest:
            self.retire(self.candidate)
            self.candidate = None
        else:
            try:
                self.stage(source)
            except OSError:
                self.candidate = None
                self.emit("rejected", policy_hash=digest, reason="worker_spawn_failed")

    def finish_bank(self, terminal, reason):
        task = self.bank
        if task is None or task.outcome is not None:
            return
        outcome = dict(bank_verdict(terminal=terminal, controller="candidate", wet_takeover=task.wet_takeover,
                                    baseline_assisted=False, ownership_complete=False),
                       evidence="live_sampled", reason=reason, observed_wet_takeover=task.wet_takeover)
        if outcome["physical_success"] is not None:
            raise ValueError("Live observations cannot establish an exact bank verdict")
        task_id = task.record["task_id"]
        if self.memory.finish_bank(task_id, outcome):
            self.emit("bank_outcome", task_id=task_id, policy_hash=task.record["policy_hash"], **outcome)
        else:
            # Another exclusive owner may already have censored this task during an outage.
            _, outcome = self.memory.bank(task_id)
        task.outcome = outcome
        self.generation += 1
        if self.undertaking and self.undertaking.get("task_id") == task_id:
            self.terminate_attempt("bank_" + terminal)

    def release(self, bank_terminal="control_lost", reason="release"):
        try:
            self.finish_bank(bank_terminal, reason)
        finally:
            # A failed local journal write must never suppress native fallback.
            lease, self.lease = self.lease, None
            if lease:
                self.block_sample = self.last_sample
                self.generation += 1
                try:
                    self.call("release", dict(lease, request_id="release-" + os.urandom(10).hex()))
                except (OSError, ValueError):
                    pass

    def close(self):
        try:
            try:
                self.terminate_attempt("supervisor_exit")
            finally:
                self.release(reason="supervisor_exit")
        finally:
            self.retire(self.active)
            self.retire(self.candidate)
            self.active = self.candidate = None
            for w in self.retired:
                w.thread.join(1.)

    def terminate_attempt(self, status, *, physical=None, obs=None, progress=None):
        u = self.undertaking
        if not u:
            return
        damage = None
        gain = {}
        if obs:
            old = u["start_state"]
            new = obs["state"]
            if all(k in old and k in new for k in ("health", "shields")):
                damage = max(0., old["health"] + old["shields"] - new["health"] - new["shields"])
            for k in ("health", "shields", "mana"):
                if k in old and k in new and new[k] > old[k]:
                    gain[k] = new[k] - old[k]
            for k, v in new.get("ammo", {}).items():
                if k in old.get("ammo", {}) and v > old["ammo"][k]:
                    gain["ammo_" + k] = v - old["ammo"][k]
        outcome = dict(status=status, physical_success=physical,
                     duration_seconds=max(0., time.monotonic() - u["started"]),
                     applied_ms=progress.get("applied_ms") if progress else None,
                     damage=damage, item_gain=gain)
        if self.memory.finish(u["episode_id"], outcome):
            self.emit("outcome", episode_id=u["episode_id"], action_seq=u["action_seq"],
                      policy_hash=u["policy_hash"], skill=u["skill"], **outcome)
        self.block_sample = self.last_sample
        self.undertaking = None
        self.last_decision = None
        self.last_phase = None

    def fail(self, worker, reason):
        if worker is self.candidate:
            self.emit("rejected", policy_hash=worker.digest, reason=reason)
            self.retire(worker)
            self.candidate = None
            self.candidate_ready = False
        else:
            self.emit("fallback", policy_hash=worker.digest, reason=reason)
            self.terminate_attempt(reason)
            self.release(reason=reason)
            self.retire(worker)
            self.active = None
            self.state = {}
        if self.active is None and self.candidate is None and self.previous_source is not None:
            source, self.previous_source = self.previous_source, None
            try:
                self.stage(source)
            except OSError:
                self.emit("fallback", policy_hash=None, reason="rollback_spawn_failed")

    def context(self, obs, worker):
        sense = obs["lily"]["sense"]
        routes = {}
        for choice in (obs["lily"].get("offers") or {}).get("choices", []):
            key = route_key(self.environment, choice, sense["position"])
            routes[str(choice["node"])] = self.memory.estimate(key)
        x, y, _ = sense["facing"]
        skills = {name: self.memory.estimate(skill_key(self.environment, name, sense, direction))
                for name, direction in zip(MOTOR_SKILLS, ([x, y, 0.], [y, -x, 0.]))}
        compatible = worker is self.active or (self.active and worker.state_version is not None
                                                and self.active.state_version == worker.state_version)
        current = self.undertaking
        return dict(abi_version=1, state_version=worker.state_version, state=self.state if compatible else {},
                    directive=self.directive, routes=routes, skills=skills,
                    bank_task=self.bank.context() if self.bank else None,
                    undertaking={k: current[k] for k in ("episode_id", "action_seq", "skill", "goal")} if current else None)

    def marker(self):
        return (self.generation, tuple(self.fence.values()), self.directive["id"] if self.directive else None,
                self.undertaking["episode_id"] if self.undertaking else None)

    def enqueue(self, worker, obs, sampled_at):
        ticket = (obs, self.marker(), sampled_at)
        context = self.context(obs, worker)
        if worker is self.candidate:
            # Exercise planning for the next undertaking while the current
            # action and its worker continue undisturbed.
            context["undertaking"] = None
        worker.decide(obs, context, ticket, self.decision_timeout)

    def refresh_directive(self):
        current = self.directive
        new = get_directive(self.directive_file, self.fence)
        if current and new and current["expires_at"] > time.time() and current["id"] == new["id"]:
            self.directive = dict(current, expires_at=new["expires_at"])
        else:
            if current or new:
                self.generation += 1
            if self.bank is not None:
                if self.bank.outcome is None:
                    self.release("directive_ended", "order_replaced_or_expired")
                self.bank = None
            self.directive = new

    def valid_plan(self, marker, sampled_at):
        self.refresh_directive()
        return self.marker() == marker and time.monotonic() - sampled_at <= .9

    @staticmethod
    def check_receipt(intent, response):
        expected = {k: intent[k] for k in (*FENCE, "request_id")}
        expected["kind"] = "commit" if intent["kind"] == "route" else "motor"
        if "action_seq" in intent:
            expected["action_seq"] = intent["action_seq"]
        if (not isinstance(response, dict) or any(response.get(k) != v for k, v in expected.items())
                or type(response.get("action_seq")) is not int or not 1 <= response["action_seq"] <= 0xffffffff
                or response.get("status") not in ("applied", "pending", "rejected", "expired", "stale",
                                                  "rate_limited", "unconfirmed", "cancelled")):
            raise ValueError("Mismatched action receipt")
        return response

    def receipt(self, intent):
        response = self.call("commands/" + intent["request_id"])
        return self.check_receipt(intent, response)

    def recover_submissions(self):
        # A new, exclusive lease can inspect receipts left by its predecessor.
        # A recovered episode has no continuous observation window across the outage.
        pending = self.memory.pending_admissions(self.fence["run_id"])
        for intent in self.memory.unresolved(self.fence["run_id"]):
            try:
                receipt = self.receipt(intent)
            except OSError:
                self.memory.disposition(intent, "unconfirmed")
                self.emit("submission_censored", request_id=intent["request_id"], reason="receipt_unavailable")
                continue
            except ValueError:
                self.memory.disposition(intent, "censored_unresolved")
                self.emit("submission_censored", request_id=intent["request_id"], reason="unknown_receipt")
                continue
            _, eid = self.memory.bind(intent, receipt["action_seq"])
            if receipt["status"] == "applied":
                self.memory.admitted(eid, intent.get("task_id"))
            self.emit("submission_reconciled", request_id=intent["request_id"], episode_id=eid,
                      status=receipt["status"])
        for attempt in pending:
            # The episode already exists. A changed sequence must never create
            # a replacement child or silently move this durable association.
            eid = "/".join(str(attempt[k]) for k in (*FENCE, "action_seq"))
            try:
                receipt = self.receipt(attempt)
            except (OSError, ValueError):
                self.emit("submission_censored", request_id=attempt["request_id"],
                          reason="late_admission_unconfirmed")
                continue
            if receipt["status"] == "applied":
                self.memory.admitted(eid, attempt.get("task_id"))
            self.emit("submission_reconciled", request_id=attempt["request_id"], episode_id=eid,
                      status=receipt["status"])
        for abandoned in self.memory.recover(self.fence["run_id"]):
            self.emit("recovered_attempt", episode_id=abandoned, status="owner_lost", physical_success=None)

        for record, outcome in self.memory.recover_banks(self.fence["run_id"]):
            self.emit("bank_outcome", task_id=record["task_id"], policy_hash=record["policy_hash"],
                      **{k: record[k] for k in FENCE}, **outcome)

    def attach(self):
        if not self.lease:
            attached = self.call("attach", dict(self.fence, controller="lily-runtime"))
            self.lease = dict(self.fence, lease_id=attached["lease_id"])
            self.counter = max(self.counter, int(attached.get("lily_request_floor", "0")),
                               self.memory.request_floor(self.fence["run_id"]))
            self.renew_at = time.monotonic() + attached["expires_in"] * .5
            self.recover_submissions()

    @staticmethod
    def bank_clock(obs):
        age = obs.get("age_seconds")
        value = obs["state"].get("game_time")
        return value if finite_number(age) and 0 <= age <= .75 and finite_number(value) else None

    def open_bank(self, obs, sampled_at):
        order = self.directive
        if self.bank or not order or order["goal"] != "escape-bank":
            return
        task_id = bank_id(self.environment, self.fence, order["id"])
        stored = self.memory.bank(task_id)
        if not stored or stored[1] is None:
            marker = self.marker()
            self.attach()  # Reconcile the previous exclusive owner's tasks first.
            if not self.valid_plan(marker, sampled_at):
                self.release()
                return
            stored = self.memory.bank(task_id)
        if stored:
            if stored[1] is None:
                raise ValueError("unreconciled_bank")
            self.bank = BankTask(stored[0], None)
            self.bank.outcome = stored[1]
            if self.lease:
                self.release()
            return
        sense = obs["lily"]["sense"]
        record = dict(self.fence, environment=self.environment, task_id=task_id, directive_id=order["id"],
                      policy_hash=self.active.digest, start_sample=sense["sample_id"], start_position=list(sense["position"]),
                      start_game_time=self.bank_clock(obs))
        try:
            record.update(bank_parameters(order["parameters"], sense["position"]))
            reason = None if sense["medium"] == "water" else "requires_wet_start"
        except ValueError:
            reason = "invalid_parameters"
        if not self.memory.begin_bank(record):
            raise ValueError("duplicate_bank_assignment")
        self.generation += 1
        self.bank = BankTask(record, record["start_game_time"])
        self.emit("bank_start", **record)
        if reason:
            self.release("unavailable", reason)

    def send(self, obs, result, command, marker, sampled_at):
        if time.monotonic() < self.block_until:
            return "not_sent"
        task_id = result.get("task_id")
        bank_goal = None
        if self.directive and self.directive["goal"] == "escape-bank":
            if not self.bank or self.bank.outcome is not None:
                return "not_sent"
            if task_id != self.bank.record["task_id"] or result["action"] != "motor":
                self.release("unavailable", "policy_did_not_accept_bank_task")
                return "not_sent"
            sense = obs["lily"]["sense"]
            target = self.bank.record["position"]
            supplied = result.get("goal")
            if supplied:
                endpoint = [v + d * supplied["distance"] for v, d in
                            zip(sense["position"], supplied["direction"])]
                if math.dist(endpoint, target) > 1e-6:
                    self.release("unavailable", "bank_goal_mismatch")
                    return "not_sent"
            bank_goal = remaining_goal(sense["position"], target) or dict(
                position=list(target), direction=list(sense["facing"]), distance=0.)
        elif task_id is not None:
            return "not_sent"
        self.attach()
        if not self.valid_plan(marker, sampled_at):
            return "not_sent"
        self.counter = max(time.time_ns(), self.counter + 1)
        op = "commit" if result["action"] == "route" else "motor"
        request_id = "lily." + str(self.counter)
        ttl = 12. if op == "commit" else 1.
        sense = obs["lily"]["sense"]
        goal = result.get("goal")
        if op == "commit":
            choice = next(c for c in obs["lily"]["offers"]["choices"] if c["node"] == command["node"])
            key = route_key(self.environment, choice, sense["position"])
            delta = [b - a for a, b in zip(sense["position"], choice["position"])]
            length = math.hypot(*delta)
            goal = {"position": choice["position"], "direction": [d / length if length else 0. for d in delta],
                  "distance": length, "sector": choice["sector"], "item_bin": choice["item_bin"]}
        else:
            direction = goal["direction"] if goal else sense["facing"]
            if bank_goal is not None:
                goal = bank_goal
                direction = goal["direction"]
            elif goal:
                goal = dict(goal, position=[v+d*goal["distance"] for v,d in zip(sense["position"],direction)])
            key = skill_key(self.environment, result["skill"], sense, direction)
        intent = dict(self.fence, request_id=request_id, policy_hash=self.active.digest,
                      sample_id=command["sample_id"], skill=result["skill"], kind=result["action"],
                      key=key, goal=goal, revision=self.active.revision, command=command, ttl_seconds=ttl)
        if task_id is not None:
            intent["task_id"] = task_id
        self.memory.prepare(intent)
        self.emit("submission", request_id=request_id, policy_hash=self.active.digest, kind=result["action"])
        # Both lease acquisition and the durable journal transaction may block.
        # Check the current order instance and actual sample age at the point of dispatch.
        if not self.valid_plan(marker, sampled_at):
            self.memory.disposition(intent, "not_sent")
            return "not_sent"
        started = time.monotonic()
        try:
            response = self.check_receipt(intent, self.call(op, dict(
                self.lease, request_id=request_id, ttl_seconds=ttl, **command)))
        except (ValueError, OSError):
            try:
                response = self.receipt(intent)
            except (ValueError, OSError):
                self.memory.disposition(intent, "unconfirmed")
                self.emit("submission_censored", request_id=request_id, reason="unconfirmed_dispatch")
                self.release(reason="unconfirmed_dispatch")
                raise
        attempt, eid = self.memory.bind(intent, response["action_seq"])
        self.undertaking = dict(attempt, episode_id=eid, started=started, deadline=started + ttl + 1.,
                                start_state=obs["state"], ack=None, ack_at=started, motor_origin=None,
                                max_projection=None, admitted=False, next_state=result.get("state"))
        self.emit("attempt", **{k: v for k, v in attempt.items() if k not in FENCE}, episode_id=eid)
        self.ack(response["status"])
        return response["status"]

    def accept_action(self):
        u = self.undertaking
        if not u["admitted"]:
            self.memory.admitted(u["episode_id"], u.get("task_id"))
            if u["next_state"] is not None:
                self.state = u["next_state"]
            u["admitted"] = True

    def ack(self, status, *, close_on_reject=True):
        u = self.undertaking
        if u and u["ack"] != status:
            u["ack"] = status
            self.emit("ack", episode_id=u["episode_id"], action_seq=u["action_seq"], status=status,
                      policy_hash=u["policy_hash"])
            if status == "applied":
                self.accept_action()
            elif close_on_reject and status not in ("pending", "unconfirmed") and not u["admitted"]:
                self.terminate_attempt("transport_" + status)

    def record(self, obs, now):
        sense = obs["lily"]["sense"]
        u = self.undertaking
        attributed = bool(u and (sense["action_seq"], sense["revision"], sense["owner_sample_id"]) ==
                        (u["action_seq"], u["revision"], u["sample_id"]) and sense["owner"] == u["kind"]
                        and sense["phase"] in ("started", "running"))
        if attributed:
            self.accept_action()
            if (self.bank and self.bank.outcome is None and u.get("task_id") == self.bank.record["task_id"]
                    and sense["owner"] == "motor" and sense["phase"] == "running" and sense["medium"] == "water"):
                self.bank.wet_takeover = True
        if self.last_sample != sense["sample_id"]:
            self.last_sample = sense["sample_id"]
            self.emit("observation", sense=sense, state={k: v for k, v in obs["state"].items() if k in STATE_FIELDS},
                      policy_hash=u["policy_hash"] if attributed else None,
                      episode_id=u["episode_id"] if attributed else None,
                      task_id=u.get("task_id") if attributed else None,
                      skill=u["skill"] if attributed else None,
                      goal=remaining_goal(sense["position"], u["goal"]["position"]) if attributed and u["goal"] else None)
            if attributed and u["kind"] == "motor" and u["goal"]:
                if u["motor_origin"] is None:
                    u["motor_origin"] = list(sense["position"])
                projection = sum((v - o) * d for v, o, d in zip(
                    sense["position"], u["motor_origin"], u["goal"]["direction"]))
                u["max_projection"] = max(projection, u["max_projection"] or 0.)
        if not u:
            return
        def matches(event):
            return event and (event["action_seq"], event["revision"], event["sample_id"], event["owner"]) == (
                u["action_seq"], u["revision"], u["sample_id"], u["kind"])

        p = next((e for e in reversed(obs["lily"].get("terminals") or []) if matches(e)),
                 obs["lily"].get("progress"))
        if matches(p):
            self.accept_action()
            if p["phase"] != self.last_phase:
                self.memory.transition(u["episode_id"], p)
                self.emit("progress", episode_id=u["episode_id"], progress=p, policy_hash=u["policy_hash"])
                self.last_phase = p["phase"]
            if p["phase"] in TERMINAL:
                if u["ack"] == "pending":
                    try:
                        self.ack(self.receipt(u)["status"], close_on_reject=False)
                    except (OSError, ValueError):
                        pass
                verdict = None
                status = p["phase"] + "_" + p["reason"]
                if p["phase"] == "completed" and p["outcome"] == "arrived" and u["kind"] == "route":
                    status, verdict = "arrived", True
                elif p["phase"] == "completed" and p["outcome"] == "playback" and u["kind"] == "motor":
                    status = "playback"
                    # Sampled in-flight progress can establish a lower bound.
                    # Missing a positive displacement between samples cannot prove failure.
                    if (u["goal"] and u["goal"]["distance"] > 0 and u["max_projection"] is not None
                            and u["max_projection"] >= u["goal"]["distance"]):
                        status, verdict = "motor_goal_reached", True
                elif p["phase"] == "failed" and p["reason"] == "invalid_route" and u["kind"] == "route":
                    verdict = False
                self.terminate_attempt(status, physical=verdict, obs=obs, progress=p)
                return
        if u["ack"] == "pending" and now >= u["ack_at"]:
            u["ack_at"] = now + .15
            try:
                self.ack(self.receipt(u)["status"])
            except (OSError, ValueError):
                pass
        if self.undertaking and now >= u["deadline"]:
            self.terminate_attempt("lost_terminal")
            self.release(reason="lost_terminal")

    def safe(self, obs):
        sense = obs["lily"]["sense"]
        return not self.undertaking and sense["safe_handover"] and sense["sample_id"] != self.block_sample

    def step(self, observation, *, observed_at=None):
        now = time.monotonic()
        received = now if observed_at is None else observed_at
        fence = {k: observation[k] for k in FENCE}
        if fence != self.fence:
            self.finish_bank("fence_changed", "run_world_or_life_changed")
            self.bank = None
            self.terminate_attempt("fence_changed")
            self.lease = None
            self.generation += 1
            self.block_sample = None
            self.fence = fence
            self.last_sample = self.last_decision = None
            self.directive = None
            self.state = {}
        self.watch(now)
        lily = observation.get("lily") or {}
        ages = lily.get("age_seconds") or {}
        age = ages.get("sense")
        fresh = bool(observation.get("native_active") and lily.get("sense") and
                   type(age) in (int, float) and 0 <= age and age + now - received <= .75)
        if not fresh and self.fresh:
            self.generation += 1
            self.terminate_attempt("stale_telemetry")
            self.release(reason="stale_telemetry")
            self.last_decision = None
            self.emit("fallback", reason="stale_telemetry", policy_hash=self.active.digest if self.active else None)
        self.fresh = fresh
        self.refresh_directive()
        if self.candidate_ready and self.candidate_scope != self.marker()[:3]:
            self.candidate_ready = False
        obs = None
        safe = False
        if fresh:
            obs = dict(fence, state=observation.get("state") or {}, native_active=True,
                     age_seconds=observation.get("age_seconds"),
                     lily={k: lily.get(k) for k in ("sense", "offers", "progress", "age_seconds", "terminals")})
            if ages.get("offers") is None or ages["offers"] > 2:
                obs["lily"]["offers"] = None
            self.record(obs, now)
            if self.bank and self.bank.outcome is None:
                terminal = self.bank.observe(obs["lily"]["sense"], self.bank_clock(obs))
                if terminal:
                    self.release(terminal, "sampled_game_state")
            safe = self.safe(obs)
            if self.lease and now >= self.renew_at:
                try:
                    response = self.call("renew", self.lease)
                    self.renew_at = now + .5 * response["expires_in"]
                except (OSError, ValueError):
                    self.terminate_attempt("lease_lost")
                    self.release(reason="lease_lost")
                    return
        for worker in (self.candidate, self.active):
            if not worker:
                continue
            try:
                reply = worker.poll()
                if reply:
                    result, (source, marker, when) = reply
                    result, cmd = decision(result, source, worker)
                    if worker is self.candidate:
                        self.candidate_scope = marker[:3]
                        self.candidate_ready = obs is not None and self.candidate_scope == self.marker()[:3]
                        if self.candidate_ready:
                            self.emit("candidate_ready", policy_hash=worker.digest)
                    elif obs and safe and self.valid_plan(marker, when):
                        if result["action"] == "baseline":
                            self.release("directive_ended", "policy_released")
                        elif result["action"] != "wait":
                            if result["action"] == "route" and (not obs["lily"]["offers"] or
                                    cmd["offer_id"] != obs["lily"]["offers"]["offer_id"]):
                                continue
                            try:
                                self.send(source, result, cmd, marker, when)
                            except (OSError, ValueError):
                                self.emit("admission_error", policy_hash=worker.digest)
                                self.block_until = time.monotonic() + .5
                            continue  # Action state is installed on positive native evidence.
                        if "state" in result:
                            self.state = result["state"]
                if (obs and worker is self.candidate and not self.candidate_ready and worker.phase == "idle"):
                    self.enqueue(worker, obs, received - age)
            except WorkerFault as exc:
                self.fail(worker, str(exc))
            except (ValueError, KeyError, TypeError, OverflowError, RecursionError):
                self.fail(worker, "invalid_policy_output")
        if not obs or time.monotonic() - (received - age) > .75:
            return
        self.refresh_directive()
        if self.candidate_ready and self.candidate_scope != self.marker()[:3]:
            self.candidate_ready = False
        safe = self.safe(obs)
        if safe and self.candidate and self.candidate_ready and (not self.bank or self.bank.outcome is not None):
            old = self.active
            self.active, self.candidate = self.candidate, None
            if not old or old.state_version is None or old.state_version != self.active.state_version:
                self.state = {}
            if old:
                self.previous_source = old.source
                self.retire(old)
            self.candidate_ready = False
            self.last_decision = None
            self.emit("activated", policy_hash=self.active.digest, previous_hash=old.digest if old else None)
        marker = (obs["lily"]["sense"]["sample_id"], self.generation)
        if safe and self.active and self.active.phase == "idle" and marker != self.last_decision and now >= self.block_until:
            try:
                self.open_bank(obs, received - age)
            except (OSError, ValueError):
                self.emit("admission_error", policy_hash=self.active.digest)
                self.block_until = time.monotonic() + .5
                return
            self.last_decision = (obs["lily"]["sense"]["sample_id"], self.generation)
            self.enqueue(self.active, obs, received - age)
