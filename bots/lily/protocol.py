"""Payload codec for the bounded JKCP Lily extension. See docs/LILY_PROTOCOL.md."""
import math
from struct import Struct, error as StructError

OFFERS, PROGRESS, SENSE = 5, 6, 7
COMMIT, MOTOR = 19, 20
COMMIT_HEADER = Struct("<dIIII")
MOTOR_HEADER = Struct("<dIIB")
STEP = Struct("<HbbbbBBB")
OFFERS_HEADER = Struct("<IIB")
CHOICE = Struct("<IiBB3fff")
ACTION = Struct("<IIIBBBBIi")
SENSE_HEADER = Struct("<IIIIiBBBBI3f3f3f3ffff4fBBBB")
PEER = Struct("<IIIi3f3f")
AXES = ("forward", "strafe", "turn", "pitch")
OWNERS = ("baseline", "route", "motor")
PHASES = ("idle", "queued", "started", "running", "completed", "interrupted", "failed", "expired")
REASONS = ("none", "released", "life", "world", "deadline", "invalid_route", "survival", "disconnected", "replaced")
OUTCOMES = ("none", "arrived", "playback")
CLASSES = ("patrol", "item")


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"expected integer in [{low}, {high}]")
    return value


def _number(value, low, high):
    if type(value) not in (float, int) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(f"expected finite number in [{low}, {high}]")
    return value


def _keys(obj, required, optional=()):
    if type(obj) is not dict or not set(required) <= obj.keys() <= set(required) | set(optional):
        raise ValueError(f"expected keys {required} and optional keys {optional}")


def encode_command(kind, body, deadline):
    """Return command payload bytes. Strict JSON-compatible inputs only."""
    _number(deadline, 0, 1e308)
    if not deadline:
        raise ValueError("expected a positive deadline")
    if type(kind) is not int or kind not in (COMMIT, MOTOR):
        raise ValueError("unknown command")
    common = ("sample_id", "revision")
    _keys(body, common + (("offer_id", "node") if kind == COMMIT else ("steps",)))
    sample, revision = (_integer(body[key], 1, 0xffffffff) for key in common)
    if kind == COMMIT:
        return COMMIT_HEADER.pack(deadline, sample, revision, _integer(body["offer_id"], 1, 0xffffffff),
                                  _integer(body["node"], 0, 8191))
    steps = body["steps"]
    if type(steps) is not list or not 1 <= len(steps) <= 5:
        raise ValueError("expected one through five steps")
    payload = bytearray(MOTOR_HEADER.pack(deadline, sample, revision, len(steps)))
    total = 0
    for step in steps:
        _keys(step, ("duration_ms",), AXES + ("buttons", "weapon", "force"))
        duration = _integer(step["duration_ms"], 1, 600)
        total += duration
        axes = [round(100 * _number(step.get(k, 0), -1, 1)) for k in AXES]
        force = _integer(step.get("force", 0), 0, 34)
        if 0 < force < 21 or total > 600:
            raise ValueError("invalid Force bin or sequence duration")
        payload.extend(STEP.pack(duration, *axes, _integer(step.get("buttons", 0), 0, 31),
                                 _integer(step.get("weapon", 0), 0, 10), force))
    return bytes(payload)


def _records(payload, header, record, count):
    if count > 8 or len(payload) != header.size + count * record.size:
        raise ValueError("invalid record count or payload size")
    return record.iter_unpack(payload[header.size:])


def _finite(values):
    if not all(map(math.isfinite, values)):
        raise ValueError("nonfinite observation")


def _action_node(owner, node):
    return (owner == 1 and 0 <= node < 8192) or (owner == 2 and node == -1)


def _valid_progress(owner, phase, reason, outcome, node):
    if not _action_node(owner, node):
        return False
    if phase == 4:
        return reason == 0 and outcome == owner  # route arrived, or motor played
    if outcome != 0:
        return False
    if phase in (1, 2, 3):
        return reason == 0
    if phase == 5:
        return reason in (1, 2, 3, 7, 8) or (owner == 1 and reason in (5, 6))
    if phase == 6:
        return owner == 1 and reason == 5
    return phase == 7 and reason == 4


def decode_event(kind, payload):
    """Decode a single payload. Unrecognized or malformed data returns None."""
    if type(kind) is not int or not isinstance(payload, (bytes, bytearray, memoryview)) or len(payload) > 492:
        return None
    try:
        if kind == OFFERS:
            sample, offer, count = OFFERS_HEADER.unpack_from(payload)
            if not sample or not offer:
                return None
            choices = []
            for node, sector, cls, item_bin, x, y, z, cost, utility in _records(payload, OFFERS_HEADER, CHOICE, count):
                _finite((x, y, z, cost, utility))
                if node >= 8192 or sector < 0 or cost < 0:
                    return None
                choices.append(dict(node=node, sector=sector, **{"class": CLASSES[cls]},
                                    item_bin=item_bin, position=[x, y, z], cost=cost, utility=utility))
            return dict(sample_id=sample, offer_id=offer, choices=choices)
        if kind == PROGRESS:
            seq, revision, sample, owner, phase, reason, outcome, ms, node = ACTION.unpack(payload)
            if not seq or not revision or not sample or not _valid_progress(owner, phase, reason, outcome, node):
                return None
            return dict(action_seq=seq, revision=revision, sample_id=sample, owner=OWNERS[owner],
                        phase=PHASES[phase], reason=REASONS[reason], outcome=OUTCOMES[outcome],
                        applied_ms=ms, node=node)
        if kind == SENSE:
            fields = SENSE_HEADER.unpack_from(payload)
            sample, seq, revision, reference, node, owner, phase, safe, supported, medium = fields[:10]
            if not sample or safe > 1 or supported > 1 or medium > 1 or not -1 <= node < 8192:
                return None
            if owner == 0:
                if seq or revision or reference or phase or node != -1:
                    return None
            elif not (_action_node(owner, node) and seq and revision and reference and phase in (1, 3) and not safe):
                return None
            _finite(fields[10:29])
            if fields[23] < 0 or fields[24] <= 0 or any(abs(axis) > 1 for axis in fields[25:29]):
                return None
            buttons, weapon, force, count = fields[29:]
            if buttons > 31 or weapon > 10 or force not in (0, *range(21, 35)):
                return None
            peers = []
            for slot, net_id, guid, sector, *values in _records(payload, SENSE_HEADER, PEER, count):
                _finite(values)
                if not net_id or sector < 0:
                    return None
                peers.append(dict(slot=slot, net_id=net_id, guid=guid, sector=sector,
                                  position=values[:3], velocity=values[3:]))
            return dict(sample_id=sample, action_seq=seq, revision=revision, owner_sample_id=reference,
                        node=node, owner=OWNERS[owner], phase=PHASES[phase], safe_handover=bool(safe),
                        supported=bool(supported), medium=("air", "water")[medium], position=list(fields[10:13]),
                        velocity=list(fields[13:16]), facing=list(fields[16:19]), up=list(fields[19:22]),
                        head_pitch=fields[22], breath_used_ms=fields[23], tick_ms=fields[24],
                        axes=list(fields[25:29]), buttons=buttons, weapon=weapon, force=force, peers=peers)
    except (StructError, IndexError, ValueError, TypeError, BufferError):
        return None
    return None
