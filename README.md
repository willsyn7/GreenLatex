# Green LaTeX for Zed

Edit LaTeX documents in Zed, build PDFs on save, and view the results in an
automatically refreshing browser window. Designed for résumés and other
pdfLaTeX documents.

Green LaTeX is an independent project inspired by
[LaTeX Workshop](https://github.com/James-Yu/LaTeX-Workshop). It combines a
Rust/WebAssembly Zed extension, [TexLab](https://github.com/latex-lsp/texlab),
`latexmk`, and a Python preview helper.

**The PDF preview opens in your browser beside Zed. It is not an embedded Zed tab.**

## Features

- LaTeX syntax highlighting, bracket matching, and TexLab command completion.
- Automatic compilation on save and compiler diagnostics in Zed.
- Zed tasks for live preview, one-time builds, and setup checks.
- Browser preview with automatic refresh, build status, and compiler output.
- Last successful PDF stays visible when a subsequent build fails.
- Generated files stay in `.greenlatex/` beside each source document.
- Build locking prevents simultaneous save/preview builds for the same document.

## Quick start

Clone this repository and open its root directory in Zed. With Python 3.10+,
`latexmk`, and pdfLaTeX installed, run:

```bash
python3 scripts/greenlatex.py doctor
python3 scripts/greenlatex.py preview examples/resume.tex
```

A browser opens the preview. Edit `examples/resume.tex` in Zed and save to
rebuild. Keep the preview command running; press **Ctrl+C** to stop it.

The preview works independently of the custom extension. Install the extension
below to add its LaTeX editing support and save-triggered builds in Zed.

## Requirements

| Component | Purpose |
| --- | --- |
| Zed | Editing and project tasks. |
| Python 3.10+ | Build helper and preview server; no pip packages required. |
| TeX distribution with `latexmk` and pdfLaTeX | Document compilation. |
| Browser with inline PDF viewing enabled | Live PDF preview. |
| Stable Rust installed through rustup | Compiling the development extension. |
| TexLab | Editing support; the extension can download it if absent from PATH. |
| Node.js 20+ | Preview JavaScript tests only. |

Linux/WSL compilation and backend tests have been verified. Windows Zed dev
installation with a WSL workspace has also been verified using the staging
workflow below. Native Windows TeX workflows and macOS have not been tested.

### Ubuntu / WSL tools

Install a TeX distribution and common document packages:

```bash
sudo apt update
sudo apt install build-essential curl git latexmk texlive-latex-extra texlive-fonts-recommended
```

Install Rust using the [official rustup installer](https://rustup.rs), choosing
the standard installation:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
rustup target add wasm32-wasip2
cargo --version
```

For the full test suite, install the TexLab version used during development:

```bash
cargo install --git https://github.com/latex-lsp/texlab --locked --tag v5.26.0 texlab
texlab --version
```

The extension can download TexLab for editor use, but the standalone test runner
needs a local executable on PATH or supplied through `TEXLAB_BINARY`.

## Install the extension

### Linux Zed

1. Open **Extensions** with **Ctrl+Shift+X**.
2. Choose **Install Dev Extension** and select this repository's root folder,
   containing `extension.toml`.
3. Disable other extensions providing the `LaTeX` language or `texlab` server
   while using Green LaTeX, to avoid competing providers.
4. Open `examples/resume.tex`.

Zed may download grammar build tools on first installation. See
[Zed's extension development documentation](https://zed.dev/docs/extensions/developing-extensions).

### Windows Zed with a WSL workspace

Windows Zed compiles and installs dev extensions on Windows, while the document
build tools run in WSL. This setup needs:

- **Windows:** Rust on Zed's PATH, with the `wasm32-wasip2` target installed.
- **WSL:** Python, the TeX tools, and Rust/TexLab if running the full tests.

After installing Windows Rust, close Zed and open a fresh **Windows PowerShell**:

```powershell
rustc --version
rustup target add wasm32-wasip2
```

If `rustc` is not found, add the default Rust bin folder to that shell's PATH:

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
```

Launch Zed from that shell so it inherits the updated PATH.

**Stage the extension on the Windows drive.** Zed's installer creates a Windows
junction, which cannot target a WSL UNC share. In your **WSL terminal**, from the
repository root, run the following, replacing `YOUR_WINDOWS_USERNAME`:

```bash
python3 scripts/stage_extension.py /mnt/c/Users/YOUR_WINDOWS_USERNAME/projects/GreenTool-extension
```

In Windows Zed, choose **Install Dev Extension** and select:

```text
C:\Users\YOUR_WINDOWS_USERNAME\projects\GreenTool-extension
```

The staging script copies extension source and available compiled artifacts,
excluding personal documents and build caches. It refuses to overwrite an
unrelated nonempty directory. Rerun it after changing the extension source,
then rebuild the dev extension in Zed.

Keep your working project open through **Open Remote → WSL**, at the original
repository location. Use the Windows copy only for extension installation.

## Use in Zed

With the main `.tex` document active:

1. Press **Ctrl+Shift+P**.
2. Choose **task: spawn**.
3. Select a LaTeX task:

| Task | Action |
| --- | --- |
| **LaTeX: Live PDF preview** | Saves buffers, opens the browser preview, and watches saved inputs. |
| **LaTeX: Build PDF** | Saves buffers and builds the active document once. |
| **LaTeX: Check setup** | Checks Python and the TeX build tools. |

Keep the preview task running and arrange its browser window beside Zed.
Save the document to rebuild and refresh the PDF. The preview includes an
expandable compiler log and an **Open PDF** link.

**Keep this repository as the Zed project root.** The extension expects its build
helper at `<worktree root>/scripts/greenlatex.py`, and the project tasks live in
`.zed/tasks.json`. Opening only a document subfolder as a separate project will
not provide those paths. v0.1 is not yet a self-contained extension for arbitrary
projects without the companion helper and task configuration.

## Command-line usage

```bash
# Compile once:
python3 scripts/greenlatex.py build examples/resume.tex

# Start live preview:
python3 scripts/greenlatex.py preview examples/resume.tex

# Choose a port and open the URL manually:
python3 scripts/greenlatex.py preview examples/resume.tex --port 8765 --no-open

# Check tools:
python3 scripts/greenlatex.py doctor
```

For the included example, output files appear in `examples/.greenlatex/`.
`resume.pdf` is the compiler output; `resume.preview.pdf` is the last successful
PDF published to the browser. Existing PDFs beside the source are not replaced.

The preview listens on `127.0.0.1` with a random URL token and serves only the
preview page, status, and selected document's published PDF. The preview page
uses no third-party scripts or services.

## Configuration

Merge TexLab overrides into `.zed/settings.json`, for example:

```json
{
  "lsp": {
    "texlab": {
      "settings": {
        "texlab": {
          "diagnosticsDelay": 500,
          "build": { "onSave": true }
        }
      }
    }
  }
}
```

To select your own TexLab executable, add
`"binary": { "path": "/absolute/path/to/texlab" }` inside `lsp.texlab`.
Settings merge recursively with the extension defaults. Changing the build
command or artifact directories can disconnect builds from the companion preview.

## Tests

With Rust, Python, Node.js, the TeX tools, and TexLab installed:

```bash
python3 scripts/test.py --require-texlab
```

Or supply TexLab explicitly:

```bash
TEXLAB_BINARY=/absolute/path/to/texlab python3 scripts/test.py --require-texlab
```

The runner executes Rust unit tests, builds the real configuration exporter,
runs Python unit/integration tests and preview JavaScript tests, then compiles
the WebAssembly release. It stops on a failed stage. Without `--require-texlab`,
the TexLab protocol test is explicitly skipped if TexLab is unavailable.

Coverage includes configuration overrides, source/PDF validation, atomic writes,
build concurrency, live refresh and error recovery, HTTP delivery, task path
handling, staging, and TexLab completion/build/diagnostic behavior. Tests use
temporary documents and do not modify personal résumés. HTTP tests require
permission to open localhost sockets.

To run individual groups:

```bash
cargo test --locked --lib
python3 -m unittest discover -s tests -p test_units.py -v
python3 -m unittest discover -s tests -p test_staging.py -v
node tests/test_preview.cjs
```

The JavaScript tests use a DOM stub; native browser PDF rendering and interactive
Zed task execution still need manual checks. Automatic TexLab downloads are not
covered by the protocol test, which uses an installed server.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Missing test prerequisites: cargo` | Load `source "$HOME/.cargo/env"` in WSL, or install Rust through rustup. |
| `Install texlab on PATH` | Install TexLab using the command above or set `TEXLAB_BINARY`. |
| Windows Zed reports `running rustc: program not found` | Check Windows Rust and restart Zed with the Windows Cargo bin directory on PATH. |
| `could not create session directory lock file` | Use the Windows-local staging folder. The dev profile also disables incremental compilation for WSL share compatibility. |
| `Failed to create junction` | Select the Windows-local staging folder, rather than the WSL UNC directory. |
| Task references `/scripts/greenlatex.py` | Choose the updated task through **task: spawn**; **task: rerun** may retain an old command. |
| Browser does not open under WSL | Copy the printed localhost URL into your browser; WSL localhost forwarding must be enabled. |
| Browser downloads the PDF | Enable inline PDF viewing in the browser. |
| Editor support does not start | Check **zed: open log**, then use **editor: restart language server**. |

## v0.1 limitations

- pdfLaTeX only; engine selection and custom build recipes are future work.
- Preview refreshes after saved-file builds, not unsaved edits.
- Browser refreshes may reset PDF scroll position or zoom.
- No embedded Zed PDF viewer or source/PDF SyncTeX navigation. SyncTeX data is generated.
- Open the main document; comprehensive multi-file project/root detection and
  full bibliography workflows are outside v0.1.
- The watcher checks inputs roughly every half second. It watches relevant files
  below the document directory and external inputs recorded by the compiler.

## Project layout

```text
extension.toml              Zed manifest and pinned LaTeX grammar
src/                        Rust integration, shared settings, and unit tests
languages/latex/            Language metadata and Tree-sitter queries
.zed/                       Workspace settings and task definitions
scripts/greenlatex.py        Build helper and live preview server
scripts/stage_extension.py   Windows-local extension staging
scripts/test.py              Full test runner
web/preview.html             Browser preview
examples/resume.tex          Generic sample document
examples/texlab_config.rs    Configuration exporter for integration tests
tests/                      Python and JavaScript tests
```

Build outputs, downloaded grammars, editor-local metadata, and the existing
personal `BE/` résumé folder are excluded by `.gitignore`. Keep `Cargo.lock`
with the source so dependency versions remain reproducible. Git ignore rules
apply to Git-based uploads; they do not filter files manually uploaded through
the GitHub website.

## Related projects

- [Zed](https://zed.dev/)
- [TexLab](https://github.com/latex-lsp/texlab)
- [LaTeX grammar](https://github.com/497e0bdf29873/tree-sitter-latex)
- [LaTeX Workshop](https://github.com/James-Yu/LaTeX-Workshop)

Green LaTeX is not affiliated with Zed or LaTeX Workshop. External dependencies
retain their respective licenses.
