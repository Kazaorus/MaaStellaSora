import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.ci import install


class InstallChoresTests(unittest.TestCase):
    def test_copies_windows_launcher_script_to_mfa_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "install"
            output.mkdir()
            for name in (
                "README.md",
                "LICENSE",
                "CONTACT",
                "requirements.txt",
                "start_windows.py",
            ):
                (root / name).write_text(name, encoding="utf-8")

            with patch.object(install, "working_dir", root), patch.object(
                install, "install_path", output
            ):
                install.install_chores()

            self.assertEqual(
                (output / "start_windows.py").read_text(encoding="utf-8"),
                "start_windows.py",
            )


if __name__ == "__main__":
    unittest.main()
