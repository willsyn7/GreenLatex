#!/usr/bin/env python3
"""Copy extension files to a local Windows folder for Zed's dev installer."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
MARKER = ".green-latex-staging.json"
FILES = ("extension.toml", "Cargo.toml", "Cargo.lock", "README.md", "extension.wasm")
DIRECTORIES = ("src", "languages", "examples")


def stage(source: Path, destination: Path):
    source, destination = source.resolve(), destination.expanduser().resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError("Choose a staging directory outside the source workspace.")
    marker = destination / MARKER
    if destination.exists() and any(destination.iterdir()):
        try:
            previous = json.loads(marker.read_text())
        except (OSError, ValueError):
            raise ValueError("Destination contains unrelated files; choose a new directory.") from None
        if previous != {"source": str(source), "extension": "green-latex"}:
            raise ValueError("Destination belongs to another staging source; choose a new directory.")
    for required in ("extension.toml", "Cargo.toml", "src/lib.rs"):
        if not (source / required).is_file():
            raise ValueError(f"Missing extension source: {required}")
    destination.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"source": str(source), "extension": "green-latex"}))
    for name in FILES:
        if (source / name).is_file():
            shutil.copy2(source / name, destination / name)
    for name in DIRECTORIES:
        if (source / name).is_dir():
            shutil.copytree(source / name, destination / name, dirs_exist_ok=True)
    # Reuse grammar binaries when available without copying grammar Git clones.
    for grammar in (source / "grammars").glob("*.wasm"):
        (destination / "grammars").mkdir(exist_ok=True)
        shutil.copy2(grammar, destination / "grammars" / grammar.name)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New folder on the Windows C: drive, expressed as /mnt/c/... from WSL")
    args = parser.parse_args()
    try:
        destination = stage(ROOT, args.destination)
    except (OSError, ValueError) as error:
        print(f"Cannot stage extension: {error}", file=sys.stderr)
        return 1
    print(f"Extension staged at: {destination}")
    print("Select this directory in Windows Zed's Install Dev Extension picker.")
    print("Keep your working project open through WSL. Rerun this script after extension source changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
