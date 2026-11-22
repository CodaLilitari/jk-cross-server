import errno
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bots.map_audit import STOCK_MAPS, parse_jkl

LEVEL = b"""SECTION: SECTORS
World sectors 3
end
SECTION: TEMPLATES
World templates 3
base none type=actor
spawn base type=player thingflags=0x20
child spawn
end
SECTION: THINGS
World things 12
8: child north 1.25 3 -4 -10 91.5 0 2
1: child decoy 0 0 0 0 0 0 1 type=actor
5: base south 4 5 6 30 60 -90 0 type=player
end
"""


def write_gob(path, entries):
    payload = bytearray()
    directory = bytearray()
    for name, data in entries:
        directory.extend(struct.pack("<II128s", 12 + len(payload), len(data), name.encode()))
        payload.extend(data)
    path.write_bytes(struct.pack("<4sII", b"GOB ", 20, 12 + len(payload)) + payload
                     + struct.pack("<I", len(entries)) + directory)


class SpawnAtlasTests(unittest.TestCase):
    def test_parser_keeps_order_and_pose(self):
        things = parse_jkl(LEVEL.decode())["things"]
        self.assertEqual(things[8]["orientation"], (-10, 91.5, 0))
        self.assertEqual(things[5]["authored_order"], 2)

    def test_inherited_and_overridden_types(self):
        from bots.spawn_atlas import build_map_atlas
        report = build_map_atlas("arena.jkl", LEVEL)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["sha256"], hashlib.sha256(LEVEL).hexdigest())
        starts = report["starts"]
        self.assertEqual([(s["thing_index"], s["authored_order"]) for s in starts], [(8, 0), (5, 2)])
        self.assertEqual(starts[0]["properties"]["thingflags"], "0x20")
        self.assertEqual(starts[1]["properties"]["type"], "player")
        for start in starts:
            self.assertEqual(start["source_kind"], "authored_player_thing")
            self.assertEqual(start["engine_eligibility"], "not_checked")

    def test_duplicate_templates_fail_and_retain_first_definition(self):
        from bots.spawn_atlas import build_map_atlas
        for duplicate in (b"child", b"ChIlD"):
            with self.subTest(duplicate=duplicate):
                level = LEVEL.replace(b"World templates 3", b"World templates 4")
                level = level.replace(b"child spawn\n", b"child spawn\n" + duplicate + b" base\n")
                report = build_map_atlas("arena.jkl", level)
                self.assertEqual(report["status"], "incomplete")
                self.assertTrue(any("Duplicate template child" in e for e in report["errors"]))
                self.assertEqual([s["thing_index"] for s in report["starts"]], [8, 5])

    def test_pose_requires_complete_decimal_and_finite_engine_float(self):
        from bots.spawn_atlas import build_map_atlas
        fields = b"1.25 3 -4 -10 91.5 0".split()
        for component in range(len(fields)):
            for token in (b"1_000", b"1.5x", b"0x1p1", b"1e", b"nan", b"-inf", b"1e100", b"-1e999"):
                with self.subTest(component=component, token=token):
                    changed = fields.copy()
                    changed[component] = token
                    level = LEVEL.replace(b" ".join(fields), b" ".join(changed))
                    report = build_map_atlas("arena.jkl", level)
                    self.assertEqual(report["status"], "incomplete")
                    self.assertIn(token.decode(), " ".join(report["errors"]))
                    self.assertEqual([s["thing_index"] for s in report["starts"]], [5])

    def test_sector_requires_complete_signed_decimal_integer(self):
        from bots.spawn_atlas import build_map_atlas
        for token in (b"0_2", b"2.0", b"2e0", b"0x2", b"2x"):
            with self.subTest(token=token):
                level = LEVEL.replace(b"91.5 0 2\n", b"91.5 0 " + token + b"\n")
                report = build_map_atlas("arena.jkl", level)
                self.assertEqual(report["status"], "incomplete")
                self.assertIn("invalid sector integer", " ".join(report["errors"]))
                self.assertEqual([s["thing_index"] for s in report["starts"]], [5])

    def test_decimal_pose_preserves_authored_precision(self):
        from bots.spawn_atlas import build_map_atlas
        level = LEVEL.replace(b"1.25 3 -4 -10 91.5 0 2", b"+1.00000001 3. -.4e1 -1E+1 +.915e2 -0. +02")
        report = build_map_atlas("arena.jkl", level)
        self.assertEqual(report["status"], "pass", report["errors"])
        start = report["starts"][0]
        self.assertEqual(start["position"], (1.00000001, 3, -4))
        self.assertEqual(start["orientation"], (-10, 91.5, 0))
        self.assertEqual(start["sector"], 2)

    def test_empty_placed_property_fails_validation(self):
        from bots.spawn_atlas import build_map_atlas
        for override in (b"type=", b"type= thingflags=0x20"):
            with self.subTest(override=override):
                report = build_map_atlas("arena.jkl", LEVEL.replace(b"type=actor\n5:", override + b"\n5:"))
                self.assertEqual(report["status"], "incomplete")
                self.assertTrue(any("type" in e and "empty" in e for e in report["errors"]))
                self.assertNotIn(1, [s["thing_index"] for s in report["starts"]])
        valid = LEVEL.replace(b"type=player\nend", b"type=player thingflags=0x20 orient=(0/90/0)\nend")
        report = build_map_atlas("arena.jkl", valid)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["starts"][-1]["properties"]["orient"], "(0/90/0)")

    def test_property_fields_must_be_complete_assignments(self):
        from bots.spawn_atlas import build_map_atlas
        for field in (b"=actor", b"type =actor", b"type==actor", b"type=actor=bad",
                      b"orient=(0/90/0)junk", b"orient=(0 / 90 / 0", b"unassigned"):
            for original in (b"type=actor\n5:", b"type=player thingflags=0x20"):
                with self.subTest(field=field, original=original):
                    replacement = field + (b"\n5:" if original.endswith(b"5:") else b"")
                    report = build_map_atlas("arena.jkl", LEVEL.replace(original, replacement))
                    self.assertEqual(report["status"], "incomplete")
                    self.assertTrue(report["errors"])
        fields = b"type=player  orient=(0 /  90 / 0)\tthingflags=0x20"
        report = build_map_atlas("arena.jkl", LEVEL.replace(b"type=player thingflags=0x20", fields))
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["starts"][0]["properties"]["orient"], "(0 /  90 / 0)")
        self.assertEqual(report["starts"][0]["properties"]["thingflags"], "0x20")

    def test_invalid_records(self):
        from bots.spawn_atlas import build_map_atlas
        for before, after in [(b"5:", b"8:"), (b"5:", b"5"), (b"5:", b"-1:"),
                              (b"1.25", b"nan"), (b"91.5", b"-inf"), (b"0 2\n", b"0 3\n"),
                              (b"0 2\n", b"0\n"), (b"8:", b"12:")]:
            with self.subTest(after=after):
                report = build_map_atlas("arena.jkl", LEVEL.replace(before, after))
                self.assertTrue(report["errors"])
                self.assertNotEqual(report["status"], "pass")

    def test_archives_and_ambiguity(self):
        from bots.spawn_atlas import build_atlas
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "Episode"
            episode.mkdir()
            for name, maps in STOCK_MAPS.items():
                write_gob(episode / (name.upper() + ".GOB"), [("jkl\\" + m, LEVEL) for m in sorted(maps)])
            report = build_atlas(root)
            self.assertEqual(report["status"], "pass", report)
            self.assertEqual(sum(len(e["maps"]) for e in report["episodes"]), 9)
            path = episode / "JK1MP.GOB"
            self.assertEqual(report["episodes"][0]["archive_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            write_gob(path, [("a/m2.jkl", LEVEL), ("b/M2.JKL", LEVEL)])
            report = build_atlas(root)
            self.assertIn("ambiguous", str(report).lower())
            self.assertNotEqual(report["status"], "pass")
            write_gob(path, [("a/m2.jkl", LEVEL)])
            self.assertIn("m4.jkl", build_atlas(root)["episodes"][0]["missing_maps"])

    def test_cli_preserves_archives_when_output_aliases_an_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode = root / "Episode"
            episode.mkdir()
            for name, maps in STOCK_MAPS.items():
                path = episode / (name.upper() + ".GOB")
                write_gob(path, [(m, LEVEL) for m in sorted(maps)])
            for archive in episode.iterdir():
                original = archive.read_bytes()
                symlink = root / (archive.stem + "-sym.json")
                hardlink = root / (archive.stem + "-hard.json")
                os.link(archive, hardlink)
                outputs = [archive, hardlink]
                try:
                    symlink.symlink_to(archive)
                except NotImplementedError:
                    pass
                except OSError as exc:
                    unsupported = exc.errno in (errno.ENOSYS, errno.ENOTSUP, errno.EPERM)
                    if not unsupported and getattr(exc, "winerror", None) != 1314:
                        raise
                else:
                    outputs.append(symlink)
                for output in outputs:
                    with self.subTest(output=output):
                        result = subprocess.run([sys.executable, "-m", "bots.spawn_atlas",
                                                 "--game-data", tmp, "--output", str(output)],
                                                capture_output=True)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(archive.read_bytes(), original)

    def test_missing_archives_cli_writes_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Episode").mkdir()
            output = root / "atlas.json"
            result = subprocess.run([sys.executable, "-m", "bots.spawn_atlas", "--game-data",
                                     tmp, "--output", str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(all(e["errors"] for e in json.loads(output.read_text())["episodes"]))
