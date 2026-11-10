"""Integration tests use disposable sources; supplied resumes are never edited."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import greenlatex as app


@unittest.skipUnless(shutil.which("latexmk") and shutil.which("pdflatex"), "TeX Live required")
class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="green latex ")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.source = self.directory / "resume draft.tex"
        self.source.write_text(r"\documentclass{article}\begin{document}First version\end{document}")

    def test_build_preserves_existing_pdf_and_survives_error(self):
        original_pdf = self.source.with_suffix(".pdf")
        original_pdf.write_bytes(b"Existing user PDF must remain untouched")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.build(self.source), 0)
        published = app.output_dir(self.source) / "resume draft.preview.pdf"
        before = published.read_bytes()
        self.assertTrue(before.startswith(b"%PDF-"))
        self.source.write_text(r"\documentclass{article}\begin{document}\badcommand\end{document}")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(app.build(self.source), 0)
        self.assertEqual(before, published.read_bytes())
        self.assertEqual(original_pdf.read_bytes(), b"Existing user PDF must remain untouched")
        state = json.loads((app.output_dir(self.source) / "resume draft.status.json").read_text())
        self.assertFalse(state["ok"])
        self.assertIn("Undefined control sequence", state["log"])

    def test_live_preview_rebuilds_after_save_and_recovers(self):
        state = app.Preview(self.source)
        server = ThreadingHTTPServer(("127.0.0.1", 0), state.handler())
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        watching = threading.Thread(target=state.watch, daemon=True)
        serving.start()
        watching.start()
        base = f"http://127.0.0.1:{server.server_port}/{state.token}/"

        def wait_for(predicate):
            end = time.monotonic() + 25
            while time.monotonic() < end:
                with urlopen(base + "status", timeout=2) as response:
                    status = json.load(response)
                if predicate(status):
                    return status
                time.sleep(0.15)
            self.fail(f"Timed out waiting for preview update: {status}")

        try:
            first = wait_for(lambda s: s["ok"] is True and not s["building"])
            with urlopen(base) as response:
                self.assertIn(b"Compiled PDF preview", response.read())
            with urlopen(base + "document.pdf") as response:
                original = response.read()
                self.assertEqual(hashlib.sha256(original).hexdigest(), first["revision"])
            self.source.write_text(r"\documentclass{article}\begin{document}\badcommand\end{document}")
            wait_for(lambda s: s["ok"] is False and not s["building"])
            with urlopen(base + "document.pdf") as response:
                self.assertEqual(original, response.read())
            self.source.write_text(r"\documentclass{article}\begin{document}Updated after save\end{document}")
            wait_for(lambda s: s["ok"] is True and s["revision"] != first["revision"] and not s["building"])
            for route in ("/status", "/wrong-token/document.pdf", f"/{state.token}/../resume draft.tex"):
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"http://127.0.0.1:{server.server_port}" + route.replace(" ", "%20"))
                self.assertEqual(error.exception.code, 404)
        finally:
            state.stop.set()
            watching.join(timeout=25)
            server.shutdown()
            server.server_close()
            serving.join(timeout=2)
        self.assertFalse(watching.is_alive())

    def test_watch_tracks_external_recorded_dependencies(self):
        shared = self.directory / "shared.tex"
        shared.write_text("Original")
        document = self.directory / "document"
        document.mkdir()
        self.source = document / "main.tex"
        self.source.write_text(r"\documentclass{article}\begin{document}\input{../shared.tex}\end{document}")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.build(self.source), 0)
        before = app.fingerprint(self.source)
        shared.write_text("Updated dependency")
        self.assertNotEqual(before, app.fingerprint(self.source))

    def test_rejects_empty_source(self):
        self.source.write_text("")
        with self.assertRaisesRegex(ValueError, "empty"):
            app.source_path(str(self.source))

    def test_concurrent_save_and_preview_builds_share_outputs_safely(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with ThreadPoolExecutor(max_workers=2) as pool:
                codes = list(pool.map(app.build, [self.source, self.source]))
        self.assertEqual(codes, [0, 0])
        state = app.Preview(self.source).status()
        self.assertTrue(state["ok"])
        self.assertIsNotNone(state["revision"])

    def test_separate_processes_can_build_the_same_document(self):
        helper = Path(app.__file__).resolve()
        processes = [subprocess.Popen([sys.executable, str(helper), "build", str(self.source)],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                     for _ in range(2)]
        try:
            for process in processes:
                output, _ = process.communicate(timeout=25)
                self.assertEqual(process.returncode, 0, output)
            self.assertTrue(app.Preview(self.source).status()["ok"])
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
