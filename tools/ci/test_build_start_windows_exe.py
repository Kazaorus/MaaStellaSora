import tempfile
import unittest
from pathlib import Path

from tools.build_start_windows_exe import (
    APP_NAME,
    build_command,
    copy_resource_tree,
)


class BuildStartWindowsExeTests(unittest.TestCase):
    def test_build_command_uses_onedir_and_collects_maa(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "start_windows.py").write_text("# test", encoding="utf-8")
            command = build_command(
                root,
                root / "dist",
                root / "build" / APP_NAME,
                ["python", "-m", "PyInstaller"],
            )

            self.assertIn("--onedir", command)
            self.assertEqual(command[command.index("--name") + 1], APP_NAME)
            self.assertEqual(
                command[command.index("--collect-all") + 1],
                "maa",
            )
            self.assertEqual(command[-1], str(root / "start_windows.py"))

    def test_copy_resource_tree_places_resources_beside_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource_root = root / "resource"
            (resource_root / "base").mkdir(parents=True)
            (resource_root / "base" / "model" / "ocr").mkdir(parents=True)
            (resource_root / "windows").mkdir()
            (resource_root / "base" / "pipeline.json").write_text(
                "{}", encoding="utf-8"
            )
            output_dir = root / "dist" / APP_NAME

            copy_resource_tree(resource_root, output_dir)

            self.assertEqual(
                (output_dir / "resource" / "base" / "pipeline.json").read_text(
                    encoding="utf-8"
                ),
                "{}",
            )
            self.assertTrue((output_dir / "resource" / "windows").is_dir())


if __name__ == "__main__":
    unittest.main()
