"""CTF catalog/preflight regression using authored archive fixtures."""
from pathlib import Path
import struct
import tempfile
import unittest

from manager import config, content


def archive(path, episode_type, maps):
    members = [("episode.jk", f'"Fixture"\nTYPE {episode_type}\n'.encode())]
    members += [("jkl/" + name, b"# authored catalog fixture\n") for name in maps]
    payload, entries = bytearray(), []
    for name, data in members:
        entries.append(struct.pack("<II128s", 12 + len(payload), len(data), name.encode()))
        payload.extend(data)
    path.write_bytes(b"GOB " + struct.pack("<II", 20, 12 + len(payload)) + payload +
                     struct.pack("<I", len(entries)) + b"".join(entries))


class CtfCatalogTests(unittest.TestCase):
    def test_stock_special_episode_is_listed_and_passes_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "episode").mkdir()
            (root / "resource").mkdir()
            for name in ("jk_.cd", "res2.gob", "res1hi.gob"):
                (root / "resource" / name).write_bytes(b"")
            archive(root / "episode/jk1ctf.gob", 8, ["c1.jkl", "c2.jkl", "c3.jkl"])
            archive(root / "episode/jk1mp.gob", 2, ["m2.jkl"])
            archive(root / "episode/single.gob", 1, ["single.jkl"])
            found = content.catalog(root)
            self.assertFalse(found["errors"])
            self.assertEqual({row["episode"] for row in found["episodes"]}, {"jk1ctf", "jk1mp"})
            ctf = next(row for row in found["episodes"] if row["episode"] == "jk1ctf")
            self.assertEqual(ctf["type"], 8)
            self.assertEqual(ctf["maps"], ["c1.jkl", "c2.jkl", "c3.jkl"])
            checked = config.validate({"game_data": str(root), "episode": "JK1CTF",
                                       "map": "c2.jkl", "teams": True})
            self.assertEqual(content.preflight(checked)["episode"], "jk1ctf.gob")


if __name__ == "__main__":
    unittest.main()
