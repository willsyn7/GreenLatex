#!/usr/bin/env python3
"""Green LaTeX v0.1: serialized builds and a local, live browser PDF preview."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parent.parent


def source_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() not in (".tex", ".latex") or not path.is_file():
        raise ValueError(f"Choose an existing .tex file: {path}")
    if not path.read_text(encoding="utf-8", errors="replace").strip():
        raise ValueError(f"This source file is empty: {path}")
    return path


def output_dir(source: Path) -> Path:
    return source.parent / ".greenlatex"


@contextmanager
def build_lock(path: Path):
    """OS-owned lock releases automatically on exit, including crashes."""
    with path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            lock.write(b"0")
            lock.flush()
            while True:
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def atomic_write(path: Path, data: bytes):
    # Separate temporary files allow status and build writers to run concurrently.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def build(source: Path) -> int:
    if not shutil.which("latexmk"):
        raise RuntimeError("latexmk is missing. Install TeX Live (Linux/WSL), MacTeX, or MiKTeX.")
    directory = output_dir(source)
    directory.mkdir(exist_ok=True)
    with build_lock(directory / f"{source.stem}.lock"):
        # Keep all generated files away from the supplied PDFs and source files.
        # TexLab parses TeX's standard "! ... / l.N" error format; the
        # -file-line-error variant suppresses those diagnostics in TexLab 5.x.
        command = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
                   "-synctex=1", "-outdir=.greenlatex", source.name]
        started = time.time()
        print(f"Building {source}", flush=True)
        process = subprocess.Popen(command, cwd=source.parent, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors="replace")
        lines = []
        try:
            for line in process.stdout:
                print(line, end="", flush=True)
                lines.append(line)
            code = process.wait()
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
        finally:
            process.stdout.close()
        transcript = "".join(lines)
        pdf = directory / f"{source.stem}.pdf"
        if code == 0 and (not pdf.exists() or not pdf.read_bytes().startswith(b"%PDF-")):
            code = 1
            transcript += "\nBuild did not produce a valid PDF.\n"
        atomic_write(directory / f"{source.stem}.build.log", transcript.encode())
        if code == 0:
            # A failed future compilation must never replace the last good preview.
            atomic_write(directory / f"{source.stem}.preview.pdf", pdf.read_bytes())
        state = {"ok": code == 0, "finished": time.time(), "duration": time.time() - started,
                 "message": "Build succeeded" if code == 0 else "Build failed — showing last successful PDF",
                 "log": transcript[-24000:]}
        atomic_write(directory / f"{source.stem}.status.json", json.dumps(state).encode())
        # TexLab 5.x can miss watching a build directory that did not exist at
        # startup. Its source-directory watch sees this metadata event and reloads
        # the artifacts inside, clearing stale errors after the next good build.
        os.utime(directory, None)
        return code


def fingerprint(source: Path) -> str:
    """Watch document inputs, excluding generated files. No third-party watcher."""
    digest = hashlib.sha256()
    paths = {source}
    # Include subdocuments, styles and graphics below this document's directory.
    extensions = {".tex", ".latex", ".sty", ".cls", ".bib", ".png", ".jpg", ".jpeg", ".svg", ".pdf"}
    for directory, subdirs, files in os.walk(source.parent):
        subdirs[:] = [d for d in subdirs if not d.startswith(".") and d not in ("target", "node_modules")]
        for name in files:
            path = Path(directory) / name
            if path.suffix.lower() in extensions:
                paths.add(path)
    # Recorder includes dependencies outside this directory (e.g. ../shared.tex).
    recorder = output_dir(source) / f"{source.stem}.fls"
    if recorder.exists():
        for line in recorder.read_text(errors="replace").splitlines():
            if line.startswith("INPUT "):
                path = Path(line[6:])
                if not path.is_absolute():
                    path = source.parent / path
                path = path.resolve()
                if ".greenlatex" not in path.parts and path.suffix.lower() in extensions:
                    paths.add(path)
    for path in sorted(paths):
        try:
            stat = path.stat()
            digest.update(f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode())
        except FileNotFoundError:
            digest.update(f"{path}:missing".encode())
    return digest.hexdigest()


def browser_open(url: str):
    if sys.platform.startswith("linux") and "microsoft" in os.uname().release.lower():
        powershell = shutil.which("powershell.exe")
        if powershell:
            subprocess.Popen([powershell, "-NoProfile", "-NonInteractive", "-Command",
                              f"Start-Process '{url}'"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    if not webbrowser.open(url):
        print("Open the preview URL above in your browser.", flush=True)


class Preview:
    def __init__(self, source: Path):
        self.source = source
        self.directory = output_dir(source)
        self.token = secrets.token_urlsafe(24)
        self.building = False
        self.stop = threading.Event()
        self.worker: threading.Thread | None = None

    def status(self) -> dict:
        path = self.directory / f"{self.source.stem}.status.json"
        try:
            state = json.loads(path.read_text())
            if not isinstance(state, dict):
                raise ValueError("Build status must be an object")
        except FileNotFoundError:
            state = {"ok": None, "message": "Waiting for first build", "log": ""}
        except (ValueError, OSError) as error:
            state = {"ok": False, "message": "Cannot read build status — save to rebuild", "log": str(error)}
        pdf = self.directory / f"{self.source.stem}.preview.pdf"
        state["revision"] = hashlib.sha256(pdf.read_bytes()).hexdigest() if pdf.exists() else None
        state["building"] = self.building
        state["source"] = self.source.name
        return state

    def watch(self):
        last = None
        while not self.stop.is_set():
            current = fingerprint(self.source)
            if current != last:
                # Debounce saves and atomic file replacement.
                if self.stop.wait(0.3):
                    break
                before = fingerprint(self.source)
                self.building = True
                try:
                    build(self.source)
                except Exception as error:
                    state = {"ok": False, "message": str(error), "log": str(error)}
                    self.directory.mkdir(exist_ok=True)
                    atomic_write(self.directory / f"{self.source.stem}.status.json", json.dumps(state).encode())
                finally:
                    self.building = False
                # Rebuild if an input changed during compilation. Recorder inputs
                # discovered by the first build get one extra reconciliation pass.
                last = before
            self.stop.wait(0.5)

    def handler(self):
        preview = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                route = urlsplit(self.path).path
                prefix = "/" + preview.token
                # Serve only explicitly named resources, never arbitrary files.
                if route == prefix + "/":
                    data = (ROOT / "web/preview.html").read_bytes()
                    mime = "text/html; charset=utf-8"
                elif route == prefix + "/status":
                    data = json.dumps(preview.status()).encode()
                    mime = "application/json"
                elif route == prefix + "/document.pdf":
                    path = preview.directory / f"{preview.source.stem}.preview.pdf"
                    if not path.exists():
                        self.send_error(404, "No successful build yet")
                        return
                    data = path.read_bytes()
                    mime = "application/pdf"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        return Handler


def preview(source: Path, port: int, open_browser: bool):
    state = Preview(source)
    with ThreadingHTTPServer(("127.0.0.1", port), state.handler()) as server:
        url = f"http://127.0.0.1:{server.server_port}/{state.token}/"
        print(f"Live PDF preview: {url}\nSave the .tex file to rebuild. Ctrl+C stops preview and watching.", flush=True)
        state.worker = threading.Thread(target=state.watch, daemon=True)
        state.worker.start()
        try:
            if open_browser:
                try:
                    browser_open(url)
                except (OSError, webbrowser.Error) as error:
                    print(f"Could not open a browser ({error}). Open the preview URL above manually.", flush=True)
            server.serve_forever(poll_interval=0.2)
        finally:
            state.stop.set()
            # Finish any in-flight build so no orphaned latexmk is left behind.
            state.worker.join()


def doctor() -> int:
    missing = []
    for name in ("latexmk", "pdflatex"):
        path = shutil.which(name)
        print(f"{name}: {path or 'MISSING'}")
        if not path:
            missing.append(name)
    print(f"Python: {sys.version.split()[0]}")
    print(f"texlab: {shutil.which('texlab') or 'not on PATH; the Zed extension downloads it'}")
    print("Preview: browser with built-in PDF support (Chrome, Edge, Firefox, Safari)")
    return bool(missing)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check local prerequisites")
    for name in ("build", "preview"):
        command = sub.add_parser(name)
        command.add_argument("source", help="Path to the main .tex document")
        if name == "preview":
            command.add_argument("--port", type=port_number, default=0, help="Local port, 0–65535 (default: choose a free port)")
            command.add_argument("--no-open", action="store_true", help="Print the URL without opening a browser")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return int(doctor())
        source = source_path(args.source)
        if args.command == "build":
            return build(source)
        preview(source, args.port, not args.no_open)
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Green LaTeX: {error}", file=sys.stderr)
        return 1


def port_number(value: str) -> int:
    number = int(value)
    if not 0 <= number <= 65535:
        raise argparse.ArgumentTypeError("port must be between 0 and 65535")
    return number


if __name__ == "__main__":
    sys.exit(main())
