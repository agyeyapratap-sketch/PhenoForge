# AI leaf separation (SAM)

Separating a plant into individual leaves is hard. The standard **Leaf candidates** methods
(**components** and **region**) use geometry only, so touching leaves often merge. The **sam**
option uses an AI image model, SAM 2.1 (Segment Anything Model 2.1 from Meta), to separate
leaves instead.

This is an optional add-on. It is not part of the standard installation or the Windows zip.

## Install the add-on

You need PhenoForge installed from source (see [Getting started](getting-started.md)). Then,
in the PhenoForge folder:

```
& $env:LOCALAPPDATA\venvs\phenoforge\Scripts\python.exe -m pip install -r requirements-ai.txt
```

This installs the `ultralytics` package and PyTorch (about 2–3 GB). See
[Optional add-ons](addons.md).

PhenoForge also accepts Meta's own `sam2` package if it is installed together with PyTorch.

### First use downloads the model

The first time you run **sam**, the model file `sam2.1_b.pt` (about 160 MB) is downloaded from
the internet. After that, it runs offline. If your PC is offline or behind a strict proxy, the
first run fails; run it once on a connected network.

## Use it

1. Open the scan on the [3D analysis](3d-analysis.md) tab.
2. Clean it as usual: keep the vegetation filter on, so only the plant is left.
3. In **3 Plants, leaves, heads and objects**, set **Leaf candidates** to **sam**.
4. Click **Run analysis**.

If the add-on is not installed, PhenoForge says: "AI leaf separation is an optional add-on:
install with: pip install ultralytics (downloads sam2.1_b.pt, ~160 MB, on first use). Choose
'components' to continue without it."

## How it works

For each plant:

1. The plant's points are drawn as pictures from 6 directions: one from straight above and 5
   from around the plant, looking down at 40 degrees. Each picture is 1024 × 1024 pixels, and
   PhenoForge remembers which point is seen in each pixel.
2. SAM finds regions ("masks") in each picture automatically, without any input from you.
3. Masks that are mostly background, too small, or cover more than 60 % of the plant (the
   whole plant) are dropped.
4. Each mask is mapped back to the 3D points it shows.
5. Points that most pictures keep together become one leaf. One picture that wrongly joins two
   leaves cannot merge them on its own.
6. Very small leaves are dropped. Unlabelled points (for example leaf undersides hidden in
   every picture) join the nearest leaf if it is close.

The leaves are then measured exactly like the other leaf candidates (area, length, bounding
box) and shown on the **Leaves** tab.

## How long it takes

SAM runs 6 times per plant (once per picture). Speed depends mostly on the graphics card:

- With an **NVIDIA GPU** and a GPU version of PyTorch: expect seconds to a minute per plant.
- On the **CPU only** (most office PCs): expect several minutes per plant.

A tray of many plants takes that time for each plant. The Log shows the time taken for each
plant, for example `leafsam: 9 leaf instance(s), 94% of points labelled (48.2 s, 6 views)`. Try
it on one plant first to judge the time.

## Check the results

AI leaf instances are still "visible leaf candidates", not guaranteed biological leaves. Always
check them:

1. After the analysis, set **Colour** to **Leaves**. Each leaf has its own colour.
2. Turn the view around. Look for leaves split in two (two colours on one leaf), leaves merged
   (one colour across two leaves) and stem pieces counted as leaves.
3. Compare the leaf count with a hand count on a few plants.
4. The Log line per picture (`leafsam: top: 35 masks, 12 kept`) shows how many masks SAM found
   and how many were used.

SAM works best on broad, well-separated leaves seen clearly from above or the side. Thin grass
leaves, dense canopies and leaves seen edge-on are difficult. The method was tested in
PhenoForge on synthetic plants with a stand-in for the model, not on a benchmark of real
plants. Validate it on your own plants before using leaf counts or per-leaf areas as data.

## From the command line

```
phenoforge analyse plant.ply --leaves sam --out results
```

See [Command line](cli.md).
