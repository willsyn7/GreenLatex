"""Helper unit tests run without TeX, TexLab, Zed, or network access."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import greenlatex as app


class HelperUnitTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="green unit ")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = self.root / "resume.tex"
        self.source.write_text(r"\documentclass{article}\begin{document}Test\end{document}")

    def test_valid_source_is_resolved(self):
        self.assertEqual(app.source_path(str(self.root / "sub" / ".." / "resume.tex")), self.source)

    def test_source_rejects_missing_files_directories_and_non_tex(self):
        wrong = self.root / "resume.txt"
        wrong.write_text("not a TeX source")
        for candidate in (self.root, self.root / "missing.tex", wrong):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                app.source_path(str(candidate))

    def test_source_rejects_whitespace_only_files(self):
        self.source.write_text(" \n\t")
        with self.assertRaisesRegex(ValueError, "empty"):
            app.source_path(str(self.source))

    def test_fingerprint_ignores_compiler_outputs(self):
        before = app.fingerprint(self.source)
        directory = app.output_dir(self.source)
        directory.mkdir()
        (directory / "resume.pdf").write_bytes(b"%PDF-generated")
        (directory / "resume.status.json").write_text("{}")
        self.assertEqual(before, app.fingerprint(self.source))

    def test_fingerprint_detects_input_addition_and_deletion(self):
        before = app.fingerprint(self.source)
        included = self.root / "sections.tex"
        included.write_text("section")
        self.assertNotEqual(before, app.fingerprint(self.source))
        included.unlink()
        self.assertEqual(before, app.fingerprint(self.source))

    def test_build_reports_missing_latexmk_without_starting_process(self):
        with patch.object(app.shutil, "which", return_value=None), patch.object(app.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "latexmk is missing"):
                app.build(self.source)
            spawn.assert_not_called()

    def test_successful_exit_without_pdf_is_reported_in_both_logs(self):
        process = Mock(stdout=io.StringIO("Compiler exited without producing output.\n"))
        process.wait.return_value = 0
        with patch.object(app.shutil, "which", return_value="latexmk"), \
             patch.object(app.subprocess, "Popen", return_value=process), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(app.build(self.source), 0)
        directory = app.output_dir(self.source)
        state = json.loads((directory / "resume.status.json").read_text())
        self.assertFalse(state["ok"])
        self.assertIn("valid PDF", state["log"])
        self.assertIn("valid PDF", (directory / "resume.build.log").read_text())
        self.assertFalse((directory / "resume.preview.pdf").exists())

    def test_invalid_pdf_does_not_replace_last_successful_preview(self):
        directory = app.output_dir(self.source)
        directory.mkdir()
        published = directory / "resume.preview.pdf"
        published.write_bytes(b"%PDF-last-good")
        (directory / "resume.pdf").write_bytes(b"not actually a PDF")
        process = Mock(stdout=io.StringIO(""))
        process.wait.return_value = 0
        with patch.object(app.shutil, "which", return_value="latexmk"), \
             patch.object(app.subprocess, "Popen", return_value=process), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(app.build(self.source), 0)
        self.assertEqual(published.read_bytes(), b"%PDF-last-good")

    def test_atomic_write_failure_preserves_original_and_cleans_temporary_file(self):
        target = self.root / "status.json"
        target.write_bytes(b"original")
        with patch.object(Path, "replace", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                app.atomic_write(target, b"replacement")
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(set(self.root.iterdir()), {self.source, target})

    def test_status_before_first_build(self):
        status = app.Preview(self.source).status()
        self.assertIsNone(status["ok"])
        self.assertIsNone(status["revision"])
        self.assertFalse(status["building"])
        self.assertEqual(status["source"], "resume.tex")

    def test_corrupt_status_keeps_last_good_pdf_available(self):
        directory = app.output_dir(self.source)
        directory.mkdir()
        (directory / "resume.status.json").write_text("{broken")
        (directory / "resume.preview.pdf").write_bytes(b"%PDF-last-good")
        status = app.Preview(self.source).status()
        self.assertFalse(status["ok"])
        self.assertIsNotNone(status["revision"])

    def test_browser_launch_failure_still_serves_and_cleans_up(self):
        state = app.Preview(self.source)
        with patch.object(app, "Preview", return_value=state), \
             patch.object(app, "ThreadingHTTPServer") as server_type, \
             patch.object(app.threading, "Thread") as thread_type, \
             patch.object(app, "browser_open", side_effect=OSError("no browser")), \
             contextlib.redirect_stdout(io.StringIO()):
            server = server_type.return_value.__enter__.return_value
            server.server_port = 8765
            server.serve_forever.side_effect = KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):
                app.preview(self.source, 0, True)
            server.serve_forever.assert_called_once()
            thread_type.return_value.join.assert_called_once()
        self.assertTrue(state.stop.is_set())

    def test_doctor_fails_when_compiler_is_missing(self):
        with patch.object(app.shutil, "which", return_value=None), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.doctor(), 1)

    def test_cli_returns_failure_for_invalid_source(self):
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(app.main(["build", str(self.root / "missing.tex")]), 1)
        self.assertIn("existing .tex file", errors.getvalue())

    def test_cli_rejects_invalid_port_before_starting_server(self):
        for port in ("-1", "65536", "not-a-number"):
            with self.subTest(port=port), patch.object(app, "preview") as start:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    app.main(["preview", str(self.source), "--port", port])
                self.assertEqual(error.exception.code, 2)
                start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
