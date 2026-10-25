"""Stock-map metadata checks use authored synthetic maps, never retail assets."""
from __future__ import annotations
import unittest
from bots.map_audit import audit_map, parse_jkl, pickup_catalog

FIXTURE = """
SECTION: HEADER
SECTION: GEORESOURCE
World vertices 8
World surfaces 6
SECTION: SECTORS
World sectors 2
SECTION: TEMPLATES
World templates 5
_powerup none type=item model3d=ecel.3do
custom_energy _powerup respawn=30
_actor none type=actor
walkplayer _actor type=player
SECTION: THINGS
World things 6
0: walkplayer player 0 0 0.12 0 0 0 0
1: custom_energy cell 1 0 0.05 0 0 0 1
end
"""
CATALOG_SOURCE = '{"energycell","ecel.3do",{BOT_ITEM_AMMO,11,0,500}},'


class MapAuditTests(unittest.TestCase):
    def test_inherited_stock_model_classifies_renamed_placed_item(self):
        report = audit_map("synthetic.jkl", FIXTURE.encode(), pickup_catalog(CATALOG_SOURCE), ctf=False)
        self.assertEqual(report["status"], "structure_and_pickup_catalog_pass")
        self.assertEqual(report["item_categories"], {"ammo": 1})
        self.assertEqual(report["player_starts"], 1)
        self.assertEqual(report["authored_things"], 2)
        self.assertEqual(report["world"]["things"], 6)

    def test_missing_or_unclassified_content_is_not_a_pass(self):
        report = audit_map("synthetic.jkl", FIXTURE.replace("ecel.3do", "different.3do").encode(),
                           pickup_catalog(CATALOG_SOURCE), ctf=False)
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["unclassified_templates"], {"custom_energy": 1})
        parsed = parse_jkl(FIXTURE.replace("0 0 0 1\n", "0 0 0 20\n"))
        self.assertTrue(any("invalid sector" in e for e in parsed["errors"]))

    def test_ctf_requires_real_flag_and_corridor_bindings(self):
        missing = audit_map("synthetic.jkl", FIXTURE.encode(), pickup_catalog(CATALOG_SOURCE), ctf=True)
        self.assertEqual(missing["status"], "needs_review")
        self.assertIsNone(missing["ctf_bindings"])
        self.assertIn("CTF requires exactly one stock CTF_MAIN instance", missing["errors"])
        bad = FIXTURE + "\nSECTION: COGS\n0: ctf_main.cog 0 1 2 3 0 0 1\nend\n"
        report = audit_map("synthetic.jkl", bad.encode(), pickup_catalog(CATALOG_SOURCE), ctf=True)
        self.assertTrue(any("absent flag or base" in e for e in report["errors"]))

    def test_catalog_requires_real_classifier_table(self):
        with self.assertRaises(ValueError):
            pickup_catalog("no classifier here")


if __name__ == "__main__":
    unittest.main()
