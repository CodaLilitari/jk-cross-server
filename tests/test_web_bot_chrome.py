import unittest

from web_bots.launch_chrome import SEATS, check_view


class ChromeQualificationTests(unittest.TestCase):
    def setUp(self):
        self.status = {
            "custom_model": True, "joined_count": 4,
            "seats": {seat: {"joined": True, "self": {"slot": i, "net_id": 7+i}}
                      for i, seat in enumerate(SEATS)},
        }
        self.lily = self.status["seats"]["lily"]
        self.lily.update(view={"flags": 7, "model": "dlil.3do"},
                         graphics={"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA GeForce, D3D11)",
                                   "width": 1280, "height": 720})

    def test_live_unique_slots_host_model_and_hardware(self):
        self.assertIsNone(check_view(self.status))
        self.status["custom_model"] = False
        self.lily["view"]["model"] = "ky.3do"
        self.assertIsNone(check_view(self.status))

    def test_fresh_count_cannot_substitute_for_seat_and_network_identity(self):
        jan = self.status["seats"]["jan"]
        jan["joined"] = False
        self.assertIsNotNone(check_view(self.status))
        jan["joined"] = True
        jan["self"]["net_id"] = 7
        self.assertIsNotNone(check_view(self.status))
        jan["self"]["net_id"] = 9
        jan["self"]["slot"] = 0
        self.assertIsNotNone(check_view(self.status))
        jan["self"]["slot"] = 2
        self.lily["self"]["slot"] = False
        self.assertIsNotNone(check_view(self.status))

    def test_third_person_privately_loaded_model_and_drawable(self):
        self.lily["view"]["model"] = "ky.3do"
        self.assertIsNotNone(check_view(self.status))
        self.lily["view"]["model"] = "dlil.3do"
        for flags in (1, 3, 5, 15):
            with self.subTest(flags=flags):
                self.lily["view"]["flags"] = flags
                self.assertIsNotNone(check_view(self.status))
        self.lily["view"]["flags"] = 7
        self.lily["graphics"]["width"] = 0
        self.assertIsNotNone(check_view(self.status))

    def test_capture_drawable_is_widescreen_after_sdl_size_probe(self):
        for width, height, ok in [(1085, 1085, False), (1100, 618, True), (960, 540, True)]:
            with self.subTest(size=(width, height)):
                self.lily["graphics"].update(width=width, height=height)
                self.assertEqual(check_view(self.status) is None, ok)

    def test_software_and_masked_renderers_fail_despite_hardware_vendor(self):
        for name in ("ANGLE (Intel, SwiftShader Device)", "llvmpipe (LLVM)", "ANGLE (Microsoft Basic Render Driver)",
                     "Direct3D11 WARP", "Apple Software Rasterizer", "WebKit WebGL"):
            with self.subTest(renderer=name):
                self.lily["graphics"]["renderer"] = name
                self.assertIsNotNone(check_view(self.status))
