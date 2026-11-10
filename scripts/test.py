#!/usr/bin/env python3
"""Run Rust, Python, preview UI and WebAssembly checks from any directory."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-texlab", action="store_true", help="Fail instead of skipping the real TexLab check")
    args = parser.parse_args()
    env = dict(os.environ)
    needed = ["cargo", "node", "latexmk", "pdflatex"]
    missing = [tool for tool in needed if not shutil.which(tool)]
    if missing:
        print("Missing test prerequisites: " + ", ".join(missing), file=sys.stderr)
        if "cargo" in missing:
            print("Install Rust/Cargo through rustup: https://rustup.rs\n"
                  "If already installed, add its bin directory to PATH (usually: source ~/.cargo/env).\n"
                  "Then run: rustup target add wasm32-wasip2", file=sys.stderr)
        return 1
    texlab = env.get("TEXLAB_BINARY") or shutil.which("texlab")
    if texlab:
        resolved = shutil.which(texlab)
        if not resolved:
            print(f"TexLab executable not found: {texlab}", file=sys.stderr)
            return 1
        env["TEXLAB_BINARY"] = str(Path(resolved).resolve())
    elif args.require_texlab:
        print("Install texlab on PATH or set TEXLAB_BINARY for the required integration check.", file=sys.stderr)
        return 1
    else:
        print("TexLab not found: its protocol test will be explicitly skipped.", flush=True)
    target = Path(env.get("CARGO_TARGET_DIR", ROOT / "target"))
    target = (ROOT / target).resolve() if not target.is_absolute() else target.resolve()
    env["CARGO_TARGET_DIR"] = str(target)
    env["GREEN_LATEX_CONFIG_BIN"] = str(target / "debug/examples" / ("texlab_config.exe" if os.name == "nt" else "texlab_config"))
    commands = [
        ["cargo", "test", "--locked", "--lib"],
        ["cargo", "build", "--locked", "--example", "texlab_config"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        ["node", "tests/test_preview.cjs"],
        ["cargo", "build", "--locked", "--release", "--target", "wasm32-wasip2"],
    ]
    for command in commands:
        print("\nRunning: " + " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    print("\nAll requested checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
