"""Optional real TexLab smoke test: set TEXLAB_BINARY to an installed server."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest


@unittest.skipUnless(os.environ.get("TEXLAB_BINARY"), "Set TEXLAB_BINARY to run the language-server test")
class TexlabIntegration(unittest.TestCase):
    def test_completions_save_build_and_compiler_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="green texlab ") as folder:
            root = Path(folder)
            source = root / "main.tex"
            text = "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n"
            source.write_text(text)
            project = Path(__file__).resolve().parents[1]
            # The extension expects its helper at the worktree root.
            # Use the actual Rust defaults rather than maintaining a copied config.
            import shutil
            shutil.copytree(project / "scripts", root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
            config_binary = os.environ.get("GREEN_LATEX_CONFIG_BIN", str(project / "target/debug/examples/texlab_config"))
            self.assertTrue(Path(config_binary).is_file(), "Build the texlab_config example or run scripts/test.py first")
            config = json.loads(subprocess.check_output([config_binary, str(root), sys.executable], text=True))["texlab"]
            process = subprocess.Popen([os.environ["TEXLAB_BINARY"]], cwd=root,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL)
            messages = queue.Queue()
            diagnostics = {}

            def read_messages():
                while True:
                    headers = {}
                    while True:
                        line = process.stdout.readline()
                        if not line:
                            return
                        if line == b"\r\n":
                            break
                        key, value = line.decode().split(":", 1)
                        headers[key.lower()] = value.strip()
                    messages.put(json.loads(process.stdout.read(int(headers["content-length"]))))

            reader = threading.Thread(target=read_messages, daemon=True)
            reader.start()

            def send(message):
                data = json.dumps({"jsonrpc": "2.0", **message}).encode()
                process.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
                process.stdin.flush()

            def until(predicate, timeout=20, ready=None):
                deadline = time.monotonic() + timeout
                observed = []
                while time.monotonic() < deadline:
                    if ready is not None and ready():
                        return
                    try:
                        message = messages.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    observed.append(message)
                    if message.get("method") == "textDocument/publishDiagnostics":
                        diagnostics[message["params"]["uri"]] = message["params"]["diagnostics"]
                    if message.get("method") == "workspace/configuration":
                        values = [config if item.get("section") == "texlab" else {"texlab": config}
                                  for item in message["params"]["items"]]
                        send({"id": message["id"], "result": values})
                    elif message.get("method") and "id" in message:
                        send({"id": message["id"], "result": None})
                    if predicate(message):
                        return message
                self.fail(f"TexLab timed out. Recent messages: {observed[-4:]}")

            try:
                send({"id": 1, "method": "initialize", "params": {
                    "processId": os.getpid(), "rootUri": root.as_uri(),
                    "capabilities": {"workspace": {"configuration": True}},
                    "workspaceFolders": [{"uri": root.as_uri(), "name": "test"}]}})
                initialized = until(lambda m: m.get("id") == 1 and "result" in m)
                self.assertIn("completionProvider", initialized["result"]["capabilities"])
                send({"method": "initialized", "params": {}})
                send({"method": "textDocument/didOpen", "params": {"textDocument": {
                    "uri": source.as_uri(), "languageId": "latex", "version": 1, "text": text}}})
                # Ask for command completions after typing a backslash.
                edit = text.replace("Hello", "\\sec")
                send({"method": "textDocument/didChange", "params": {
                    "textDocument": {"uri": source.as_uri(), "version": 2},
                    "contentChanges": [{"text": edit}]}})
                send({"id": 2, "method": "textDocument/completion", "params": {
                    "textDocument": {"uri": source.as_uri()}, "position": {"line": 2, "character": 4}}})
                completions = until(lambda m: m.get("id") == 2 and "result" in m)["result"]
                items = completions.get("items", []) if isinstance(completions, dict) else completions
                self.assertTrue(any("section" in item["label"] for item in items))
                # Saving invalid source must trigger our helper and report its compiler error.
                invalid = text.replace("Hello", "\\badcommand")
                source.write_text(invalid)
                send({"method": "textDocument/didChange", "params": {
                    "textDocument": {"uri": source.as_uri(), "version": 3},
                    "contentChanges": [{"text": invalid}]}})
                send({"method": "textDocument/didSave", "params": {"textDocument": {"uri": source.as_uri()}}})
                error_message = until(lambda m: m.get("method") == "textDocument/publishDiagnostics"
                      and any("Undefined control sequence" in d["message"]
                              for d in m.get("params", {}).get("diagnostics", [])))
                compiler_error = next(d for d in error_message["params"]["diagnostics"]
                                      if "Undefined control sequence" in d["message"])
                self.assertEqual(compiler_error["severity"], 1)
                self.assertEqual(compiler_error["range"]["start"]["line"], 2)
                status = json.loads((root / ".greenlatex/main.status.json").read_text())
                self.assertFalse(status["ok"])
                # Save a fix and verify the error disappears after a successful build.
                source.write_text(text)
                send({"method": "textDocument/didChange", "params": {
                    "textDocument": {"uri": source.as_uri(), "version": 4},
                    "contentChanges": [{"text": text}]}})
                send({"method": "textDocument/didSave", "params": {"textDocument": {"uri": source.as_uri()}}})

                def recovered():
                    state = json.loads((root / ".greenlatex/main.status.json").read_text())
                    current = diagnostics.get(source.as_uri())
                    return state["ok"] and current is not None and not any(d.get("severity") == 1 for d in current)

                # File publication and diagnostics are independent asynchronous
                # signals; they do not have to arrive in the same LSP message.
                until(lambda _message: False, ready=recovered)
                self.assertTrue((root / ".greenlatex/main.preview.pdf").read_bytes().startswith(b"%PDF-"))
            finally:
                process.terminate()
                process.wait(timeout=5)
                reader.join(timeout=2)
                process.stdin.close()
                process.stdout.close()


if __name__ == "__main__":
    unittest.main()
