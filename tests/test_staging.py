"""Staging must not copy resumes or overwrite unrelated Windows directories."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stage_extension as staging


class ExtensionStagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        (self.source / "src").mkdir(parents=True)
        (self.source / "src/lib.rs").write_text("extension code")
        (self.source / "Cargo.toml").write_text("manifest")
        (self.source / "extension.toml").write_text('id = "green-latex"')
        self.destination = self.root / "Windows extension"

    def test_only_extension_files_are_copied_and_updates_are_supported(self):
        for name in ("BE", "target", ".aws"):
            (self.source / name).mkdir()
            (self.source / name / "private.txt").write_text("do not copy")
        (self.source / "extension.wasm").write_bytes(b"wasm artifact")
        staging.stage(self.source, self.destination)
        self.assertEqual((self.destination / "extension.wasm").read_bytes(), b"wasm artifact")
        for name in ("BE", "target", ".aws"):
            self.assertFalse((self.destination / name).exists())
        (self.source / "src/lib.rs").write_text("updated code")
        staging.stage(self.source, self.destination)
        self.assertEqual((self.destination / "src/lib.rs").read_text(), "updated code")

    def test_unrelated_files_are_not_overwritten(self):
        self.destination.mkdir()
        existing = self.destination / "keep.txt"
        existing.write_text("original")
        with self.assertRaisesRegex(ValueError, "unrelated"):
            staging.stage(self.source, self.destination)
        self.assertEqual(existing.read_text(), "original")

    def test_source_and_nested_destination_are_rejected(self):
        for destination in (self.source, self.source / "src/staging"):
            with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, "outside"):
                staging.stage(self.source, destination)


if __name__ == "__main__":
    unittest.main()
