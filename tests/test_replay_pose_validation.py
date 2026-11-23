import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.bot_development.analysis import validate_replay_poses as poses


class ReplayPoseValidationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "src/World").mkdir(parents=True)
        (self.root / "src/Engine").mkdir()
        (self.root / "src/World/sithSurface.h").write_text(
            "SITH_SURFACE_HAS_COLLISION = 0x4,\nSITHSURF_ADJOIN_ALLOW_MOVEMENT = 0x2,\n")
        (self.root / "src/types_enums.h").write_text("SITH_SECTOR_UNDERWATER = 0x2,\n")
        (self.root / "src/Engine/sithIntersect.c").write_text("fixture\n")
        self.map_path = self.root / "owned.jkl"
        self.map_path.write_text("fixture\n")
        self.cases_path = self.root / "cases.tsv"

    def evaluate(self, x, y, *, adjoin_flags=2, sector_flags=2):
        # A collision plane at x=0 and a movement adjoin at y=0. The fixture
        # deliberately uses the engine's actual flag values (4 and 2).
        numeric = (f"1\n0 0 0\n1\n{adjoin_flags} 0\n2\n"
                   "4 -1 1 0 1 0 0\n0 0 1 0 0 1 0\n1\n"
                   f"{sector_flags} -1 -1 -1 1 1 1 0 0 0 0 0 0 0 0 0 0 0 2\n")
        with self.cases_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("case", "start_sector", "x", "y", "z", "yaw_offsets"), delimiter="\t")
            writer.writeheader()
            writer.writerow(dict(case="pose", start_sector=0, x=x, y=y, z=0, yaw_offsets="0,90"))
        with patch.object(poses, "write_geometry", side_effect=lambda _input, output: output.write_text(numeric)):
            return poses.validate(self.root, self.map_path, self.cases_path)

    def test_center_inside_does_not_establish_body_clearance(self):
        row = self.evaluate(.03, .2)["cases"][0]
        self.assertTrue(row["center_inside"])
        self.assertFalse(row["sphere_inside"])

    def test_movement_adjoin_constrains_the_sphere(self):
        self.assertFalse(self.evaluate(.2, .03)["all_spheres_inside"])
        # A non-movement adjoin is not an engine sector containment plane.
        self.assertTrue(self.evaluate(.2, .03, adjoin_flags=1)["all_spheres_inside"])

    def test_rounding_allowance_and_inside_sphere(self):
        self.assertFalse(self.evaluate(.065001, .2)["all_spheres_inside"])
        result = self.evaluate(.10, .20)
        self.assertTrue(result["all_spheres_inside"])
        self.assertEqual((result["pose_groups"], result["yaw_trials"]), (1, 2))

    def test_dry_start_is_not_accepted_as_water(self):
        with self.assertRaisesRegex(ValueError, "underwater"):
            self.evaluate(.2, .2, sector_flags=0)

    def test_large_coordinate_cancellation_cannot_overstate_clearance(self):
        normal = [poses.binary32(2 ** -.5), -poses.binary32(2 ** -.5), 0]
        distance, allowance = poses.plane_clearance([100000.09375, 100000, 0], [0, 0, 0], normal)
        self.assertGreater(distance, .06501)
        # The native float products/sum round to .0625, outside the required
        # .065 body clearance even though a fixed 1e-5 Python margin passes.
        self.assertLess(distance - allowance, .065)


if __name__ == "__main__":
    unittest.main()
