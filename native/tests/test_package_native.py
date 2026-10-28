"""Preserve the actual native link when preparing portable relinking inputs."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


def packager():
    spec = spec_from_file_location("package_native", Path(__file__).parents[1] / "package_native.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RelinkFlagsTests(unittest.TestCase):
    def test_cmake_origin_and_other_flags_survive_without_shell_expansion(self):
        with tempfile.TemporaryDirectory(prefix="jk-package-test-") as directory:
            build = Path(directory)
            (build / "main.c").write_text("int main(void) { return 0; }\n")
            subprocess.run(["cc", "-c", "main.c", "-o", "main.o"], cwd=build, check=True)
            # This is CMake's real link.txt spelling, including its escaped dollar.
            link = 'cc main.o -o openjkdf2 -Wl,--as-needed -Wl,-rpath,"\\$ORIGIN"'
            command, paths = packager().make_relink_plan(link, build)
            self.assertIn("-Wl,-rpath,$ORIGIN", command)
            self.assertIn("-Wl,--as-needed", command)
            self.assertEqual(paths["main.o"], build / "main.o")
            subprocess.run(["c++", "main.o", "-o", "openjkdf2", "-Wl,--as-needed", "-Wl,-rpath,$ORIGIN"], cwd=build, check=True)
            subprocess.run(command, cwd=build, check=True)
            self.assertEqual((build / "openjkdf2").read_bytes(), (build / "openjkdf2-relinked").read_bytes())
            dynamic = subprocess.check_output(["readelf", "-d", str(build / "openjkdf2-relinked")], text=True)
            self.assertIn("[$ORIGIN]", dynamic)
            self.assertEqual(packager().make_post_link_plan(build / "openjkdf2"), [])
            # The pinned Release CMake build strips its output after linking.
            subprocess.run(["strip", str(build / "openjkdf2")], check=True)
            for post_link in packager().make_post_link_plan(build / "openjkdf2"):
                subprocess.run(post_link, cwd=build, check=True)
            self.assertEqual((build / "openjkdf2").read_bytes(), (build / "openjkdf2-relinked").read_bytes())

    def test_absolute_static_input_is_included_and_library_search_flag_retained(self):
        with tempfile.TemporaryDirectory(prefix="jk-package-test-") as directory:
            build = Path(directory)
            archive = build / "libexample.a"
            archive.write_bytes(b"static-library-fixture")
            command, paths = packager().make_relink_plan(
                "c++ -L/some/search/path " + shlex.quote(str(archive)) + " -o openjkdf2", build)
            self.assertIn("-L/some/search/path", command)
            self.assertIn("system-static/libexample.a", command)
            self.assertEqual(paths["system-static/libexample.a"], archive)


if __name__ == "__main__":
    unittest.main()
