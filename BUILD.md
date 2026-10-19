# Building PhenoForge for Windows

The result is `dist\PhenoForge\` containing `PhenoForge.exe` (desktop app) and
`phenoforge-cli.exe` (command line), plus `dist\PhenoForge-windows-x64.zip`. The folder is
about 1.5–2 GB because Open3D, Qt, OpenCV and USD are bundled. Users need nothing else installed.

> Status: the PyInstaller spec was built and smoke-tested on Linux (the frozen GUI starts
> and the frozen CLI runs `analyse`). It has not yet been built on a Windows machine. Run
> option A or B below for the first Windows build.

## Option A: on a Windows PC

1. Install 64-bit Python 3.12 from python.org and tick "Add to PATH". Open3D has wheels
   for 3.10 to 3.12.
2. Open a terminal in this folder and run `build_windows.bat`.
   - It creates `.venv`, installs `requirements.txt` plus PyInstaller, runs the tests and freezes the app.
3. Run `dist\PhenoForge\PhenoForge.exe`.

To do it by hand:

```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pyinstaller pytest
pytest -q tests
pyinstaller packaging\phenoforge.spec --noconfirm
```

## Option B: GitHub Actions (no Windows PC needed)

Push this folder to a GitHub repository. `.github/workflows/build-windows.yml` runs on
`windows-latest` when you push a tag `v*`, or manually from the Actions tab. It tests,
freezes, smoke-tests the CLI, and uploads `PhenoForge-windows-x64.zip` as an artifact. On
a tag it also attaches the zip to the release.

## Running from source (any OS)

```
pip install -r requirements.txt
python -m phenoforge          # GUI
python -m phenoforge --help   # CLI
```

## Optional extras

| Extra | What it enables | How |
|---|---|---|
| COLMAP 3.9+ | Photogrammetry from Android or DSLR photos and video | Download the Windows CUDA or no-CUDA zip from github.com/colmap/colmap/releases. Put `COLMAP.bat` on PATH or browse to it in Tools > COLMAP |
| Ollama | Local AI assistant tab | Install from ollama.com, then run `ollama pull gemma3:4b` (or any model) |
| rawpy | Reading RAW photos (CR2, CR3, NEF, ARW, DNG and so on) | In requirements.txt and bundled when installed. Without it, shoot RAW+JPEG |
| usd-core | USDZ import | In requirements.txt. Optional in the spec |
| laspy + lazrs | LAS/LAZ import | In requirements.txt. Optional in the spec |

## Notes

- Make the app icon with `packaging\phenoforge.ico`.
- Antivirus: unsigned PyInstaller apps sometimes trigger SmartScreen. Choose "More info, then
  Run anyway", or sign the exe with your university's code-signing certificate.
- Rebuild the SOP PDFs with `python docs\sop\make_sops.py` (needs reportlab).
- If the frozen app fails to start, run `phenoforge-cli.exe gui` from a terminal to see the traceback.
