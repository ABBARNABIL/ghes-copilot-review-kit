import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "install.py"
SPEC = importlib.util.spec_from_file_location("install", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.target = Path(self.temporary.name) / "client checkout"
        self.target.mkdir()

    def test_copies_only_deployable_files_byte_for_byte(self):
        result = MODULE.install(self.target)
        self.assertEqual(len(result), 2)
        for status, relative in result:
            self.assertEqual(status, "copied")
            self.assertEqual(
                (self.target / relative).read_bytes(),
                (MODULE.TEMPLATE_ROOT / relative).read_bytes(),
            )
        files = {
            str(path.relative_to(self.target).as_posix())
            for path in self.target.rglob("*") if path.is_file()
        }
        self.assertEqual(files, set(MODULE.TEMPLATE_FILES))
        self.assertFalse((self.target / "README.md").exists())

    def test_dry_run_does_not_create_directories_or_files(self):
        result = MODULE.install(self.target, dry_run=True)
        self.assertTrue(all(status == "would-copy" for status, _ in result))
        self.assertEqual(list(self.target.iterdir()), [])

    def test_identical_files_are_unchanged(self):
        MODULE.install(self.target)
        path = self.target / MODULE.TEMPLATE_FILES[0]
        before = path.stat().st_mtime_ns
        result = MODULE.install(self.target)
        self.assertTrue(all(status == "unchanged" for status, _ in result))
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_conflict_preflight_does_not_partially_install(self):
        conflicting = self.target / MODULE.TEMPLATE_FILES[-1]
        conflicting.parent.mkdir(parents=True)
        conflicting.write_text("customer content\n", encoding="utf-8")
        for dry_run in [True, False]:
            with self.subTest(dry_run=dry_run), self.assertRaisesRegex(
                MODULE.InstallError, "different"
            ):
                MODULE.install(self.target, dry_run=dry_run)
            self.assertFalse(
                (self.target / MODULE.TEMPLATE_FILES[0]).exists()
            )
            self.assertEqual(
                conflicting.read_text(encoding="utf-8"), "customer content\n"
            )

    def test_preserves_unrelated_customer_files(self):
        customer = self.target / "README.md"
        customer.write_text("client documentation\n", encoding="utf-8")
        MODULE.install(self.target)
        self.assertEqual(
            customer.read_text(encoding="utf-8"), "client documentation\n"
        )

    def test_rejects_a_parent_that_is_a_file(self):
        (self.target / ".github").write_text("do not replace", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.InstallError, "directory"):
            MODULE.install(self.target)
        self.assertEqual(
            (self.target / ".github").read_text(encoding="utf-8"),
            "do not replace",
        )

    def test_rejects_missing_target(self):
        with self.assertRaisesRegex(MODULE.InstallError, "existing directory"):
            MODULE.install(self.target / "missing")

    def test_rejects_distribution_repository_as_target(self):
        with self.assertRaisesRegex(MODULE.InstallError, "distribution"):
            MODULE.install(ROOT)

    def test_rejects_directory_at_a_destination_file(self):
        (self.target / MODULE.TEMPLATE_FILES[0]).mkdir(parents=True)
        with self.assertRaises(MODULE.InstallError):
            MODULE.install(self.target)

    def test_rejects_linked_parent_without_writing_through_it(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        try:
            (self.target / ".github").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlink creation is unavailable: {error}")
        with self.assertRaisesRegex(MODULE.InstallError, "link"):
            MODULE.install(self.target)
        self.assertEqual(list(outside.iterdir()), [])

    def test_rejects_linked_destination_even_if_content_matches(self):
        destination = self.target / MODULE.TEMPLATE_FILES[0]
        destination.parent.mkdir(parents=True)
        try:
            destination.symlink_to(
                MODULE.TEMPLATE_ROOT / MODULE.TEMPLATE_FILES[0]
            )
        except OSError as error:
            self.skipTest(f"Symlink creation is unavailable: {error}")
        with self.assertRaisesRegex(MODULE.InstallError, "link"):
            MODULE.install(self.target)
        self.assertFalse((self.target / MODULE.TEMPLATE_FILES[1]).exists())

    def test_cli_handles_paths_with_spaces_and_reports_collisions(self):
        command = [
            sys.executable, str(SCRIPT), "--target", str(self.target), "--dry-run"
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WOULD-COPY", result.stdout)
        self.assertEqual(list(self.target.iterdir()), [])
        result = subprocess.run(command[:-1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.target / MODULE.TEMPLATE_FILES[1]).write_text(
            "customer edit\n", encoding="utf-8"
        )
        result = subprocess.run(command[:-1], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different", result.stderr)


if __name__ == "__main__":
    unittest.main()
