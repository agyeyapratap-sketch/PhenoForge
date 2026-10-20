# Optional add-ons

The standard installation covers everything except three optional features. They need extra
Python packages, which are large or only useful for some users:

| Feature | Package | Size |
|---|---|---|
| [AI leaf separation (SAM 2.1)](leaves-ai.md) | `ultralytics` (with PyTorch) | about 2–3 GB, plus a 160 MB model file on first use |
| [Wheat-head detector training and counting](wheat.md) | `ultralytics` (with PyTorch) | the same install |
| Spoken narration for [root videos](roots-2d.md) | `pyttsx3` and `imageio-ffmpeg` | small |

The list is in the file `requirements-ai.txt` in the PhenoForge folder.

The add-ons need PhenoForge installed **from source** (with Python). They cannot be added to
the Windows zip version.

## Install

1. Install PhenoForge from source first (see [Getting started](getting-started.md)). Keep the
   Python environment on a local disk, not a network drive.
2. Open PowerShell in the PhenoForge folder.
3. Install all add-ons:

   ```
   & $env:LOCALAPPDATA\venvs\phenoforge\Scripts\python.exe -m pip install -r requirements-ai.txt
   ```

   Or only the ones you need:

   ```
   & $env:LOCALAPPDATA\venvs\phenoforge\Scripts\python.exe -m pip install ultralytics
   & $env:LOCALAPPDATA\venvs\phenoforge\Scripts\python.exe -m pip install pyttsx3 imageio-ffmpeg
   ```

4. Restart PhenoForge.

## Using an NVIDIA graphics card (GPU)

`pip install ultralytics` normally installs the CPU version of PyTorch on Windows. Everything
works, but SAM and detector training are slow. If your PC has an NVIDIA graphics card, install
the GPU (CUDA) version of PyTorch by following the instructions on pytorch.org, then install
`ultralytics`. Ask IT for help on managed PCs.

## Check that they work

- **AI leaves**: set **Leaf candidates** to **sam** and click **Run analysis**. Without the add-on
  you get a message that it is an optional add-on.
- **Head detector**: open **Tools > Wheat-head detector (photos)...**. With the add-on the top line
  says "Ready: ultralytics ..."; without it, "Optional add-on not installed." and the tabs are
  greyed out.
- **Narration**: make a short [root video](roots-2d.md) with **Spoken narration** ticked. Without
  the add-on the video has no sound and the Log gives the reason.

## Internet access

- `pip install` needs internet access.
- SAM downloads `sam2.1_b.pt` (about 160 MB) the first time it runs.
- Detector training downloads the starting model (`yolov8n.pt`) the first time.

After that, everything runs offline. Narration uses the voices built into Windows and never
needs the internet.

## HEIC photos

Reading iPhone HEIC photos needs the `pillow-heif` package. It is now part of the standard
installation (`requirements.txt`), so no add-on is needed. HEIC/HEIF photos are read
everywhere PhenoForge reads photos.
