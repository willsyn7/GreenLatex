"""HTTP integration tests do not require a TeX installation."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import greenlatex as app


class PreviewHttpTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="green http ")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = self.root / "resume.tex"
        self.source.write_text("test")
        self.state = app.Preview(self.source)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.state.handler())
        worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        def cleanup():
            self.server.shutdown()
            self.server.server_close()
            worker.join(timeout=2)
        self.addCleanup(cleanup)
        self.base = f"http://127.0.0.1:{self.server.server_port}/{self.state.token}/"

    def test_initial_status_and_unavailable_pdf(self):
        with urlopen(self.base + "status") as response:
            self.assertEqual(response.headers["Content-Type"], "application/json")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            status = json.load(response)
        self.assertIsNone(status["revision"])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "document.pdf")
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_corrupt_status_is_a_json_error_state_instead_of_disconnect(self):
        self.state.directory.mkdir()
        (self.state.directory / "resume.status.json").write_text("{broken")
        with urlopen(self.base + "status") as response:
            state = json.load(response)
        self.assertFalse(state["ok"])
        self.assertIn("rebuild", state["message"])

    def test_pdf_query_string_and_headers(self):
        self.state.directory.mkdir()
        (self.state.directory / "resume.preview.pdf").write_bytes(b"%PDF-test")
        with urlopen(self.base + "document.pdf?v=revision") as response:
            self.assertEqual(response.headers["Content-Type"], "application/pdf")
            self.assertEqual(response.headers["Content-Length"], "9")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.read(), b"%PDF-test")

    def test_unknown_paths_and_encoded_traversals_are_not_served(self):
        for route in ("../resume.tex", "%2e%2e/resume.tex", "resume.tex", "status/extra", "../../README.md"):
            with self.subTest(route=route), self.assertRaises(HTTPError) as error:
                urlopen(self.base + route)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()

    def test_post_cannot_trigger_builds(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base + "status", data=b"{}", method="POST"))
        self.assertEqual(error.exception.code, 501)
        error.exception.close()


if __name__ == "__main__":
    unittest.main()
