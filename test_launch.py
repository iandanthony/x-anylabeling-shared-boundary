"""Portable configuration-path behavior without starting the GUI."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launch


class LaunchPathsTest(unittest.TestCase):
    def test_cli_directory_has_priority(self):
        for argument_list in (["launch.py", "--work-dir", "chosen"], ["launch.py", "--work-dir=chosen"]):
            with self.subTest(arguments=argument_list), patch.object(sys, "argv", argument_list.copy()):
                launch.prepare_work_directory()
                self.assertEqual(sys.argv, argument_list)

    def test_environment_directory_and_arguments(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            work = Path(directory) / "用户设置"
            with patch.dict(os.environ, {"XANYLABELING_SHARED_WORK_DIR": str(work)}), patch.object(sys, "argv", ["launch.py", "--no-auto-update-check"]):
                launch.prepare_work_directory()
                self.assertEqual(sys.argv[1:3], ["--work-dir", str(work)])
                self.assertEqual(sys.argv[-1], "--no-auto-update-check")
                self.assertTrue(work.is_dir())

    def test_default_directory_is_outside_checkout(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch.dict(os.environ, {"XANYLABELING_SHARED_WORK_DIR": ""}), patch.object(Path, "home", return_value=Path(directory)), patch.object(sys, "argv", ["launch.py"]):
                launch.prepare_work_directory()
                work = Path(directory) / "X-AnyLabeling-SharedBoundary"
                self.assertEqual(sys.argv[2], str(work))
                self.assertTrue(work.is_dir())


if __name__ == "__main__":
    unittest.main()
