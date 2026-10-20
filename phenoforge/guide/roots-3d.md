# Roots in 3D

The **Roots 3D** tab measures excavated root systems from 3D scans, and root systems in CT
or MRI image stacks. It has two modes:

- **Root crown (storage roots)**: crowns with thick storage roots, such as cassava. Follows
  the method of Sunvittayakul et al. 2022 (*Sci Rep* 12:10030): crown volume, surface,
  diameter, depth, compactness, and the number, length, angle and volume of each storage
  root.
- **Fibrous root system**: washed cereal root systems and CT volumes. The roots are reduced
  to a 3D skeleton (centre lines): total length, tips, branch points, depth, width and root
  length per depth layer.

For capture instructions see SOP-4, SOP-5 and SOP-6 in [Capture SOPs](sops.md).

## Try the demo

1. Choose **Help > Load demo root crown**.
2. The Roots 3D tab opens with a synthetic crown of 6 storage roots, already metric. Stem
   direction is z and the stem cut is 60 mm.
3. Click **Measure roots**.

## Measure a root crown from a scan

1. Open the scan on the [3D analysis](3d-analysis.md) tab (**Open scan...**).
2. Set the scale there, in section **2 Metric scale** (ArUco markers, two picked points or a
   manual factor). LiDAR scans that are already metric need nothing. You do not need to
   click Run analysis on the 3D tab.
3. Go to the **Roots 3D** tab and click **Use scan from 3D tab**. The scan appears in the view.
4. Set **Root type** to **Root crown (storage roots)**.
5. Set **Stem direction**: the direction from the roots towards the stem in the scan.
   - **z** if the crown hangs with the stem up (most scans after a normal capture).
   - **-z** if it was scanned upside down (stem down).
   - **x**, **-x**, **y**, **-y** for other directions.
   - **pca**: the longest direction of the object (a guess; check the result).
   - **two picked points**: Ctrl+click the top of the stem, then the bottom of the crown.
     The tab's hint reads "Ctrl+click: stem top, then crown bottom".
6. Check the other settings (table below).
7. Click **Measure roots**.

The view then shows the crown with each storage root in its own colour (Colour **Roots**).
Check that each storage root has one colour and that the stem stub was removed.

### Settings

| Setting | What it does | Default |
|---|---|---|
| **Remove green background sheet** | Removes strongly green points (Excess Green 0.12 or more), for a green photo backdrop. | On |
| **Remove flat background plane** | Removes the largest flat surface (table, backdrop), but only if it makes up more than 15 % of the points. | On |
| **Cut stem stub (top)** | Removes this length (mm) from the top, along the stem direction, so the stem does not count as crown. | 0 |
| **Voxel (0 = auto)** | Size of the cubes (mm) used to build a solid model. 0 chooses it from the remesh depth. | 0 |
| **Remesh depth (auto voxel)** | Like Blender's remesh octree depth: voxel = object size / 2^depth (but not finer than the point spacing allows). 8 as in the paper. Higher = finer. | 8 |
| **Split crown into sectors (paper: 2)** | Fills and measures the crown volume in this many wedges around the axis and adds them up. The paper split the crown in half (2) to reduce volume bias. 1 = whole crown. | 1 |
| **Crown core radius (0 = auto)** | Radius (mm) of the central core removed to separate the storage roots. 0 tries several radii and keeps the one that separates the most roots. | 0 |
| **Root fresh weight** | Fresh weight (kg) of the roots. When given, root density is calculated. | 0 |

The tab's note says: "Scale comes from the 3D tab settings (ArUco, picks or factor). LiDAR
scans are already metric." If the scan is not metric, the Log warns you and the numbers are
in scan units.

### How it works (briefly)

The background and stem stub are removed, stray points are removed and only the largest
piece is kept. The points are turned into small cubes (voxels). Small gaps are closed and
the inside is filled, so the shell from the scan becomes a solid. Volume is the filled
voxels; surface area comes from a smoothed surface of the solid. Storage roots are found by
removing a central core and taking the separate pieces that remain; pieces smaller than 1 %
of the crown volume are ignored. Each root's length is measured along the root from where
it leaves the core to its tip.

## Measure a fibrous root system from a scan

1. Open the scan on the 3D analysis tab and set the scale there.
2. On the Roots 3D tab click **Use scan from 3D tab**.
3. Set **Root type** to **Fibrous root system** and set **Stem direction**.
4. Optional: set **Voxel (0 = auto)**. Thin roots are scanned as hollow tubes, so the voxel
   must be coarse enough to close them. The automatic voxel is at least 4 × the point
   spacing.
5. Click **Measure roots**.

In fibrous mode the green-sheet and plane options are not used, and the stem is not cut. The
scan should contain only roots. If it contains a backdrop, clean it first: run the analysis on
the 3D analysis tab with **Vegetation index** set to **none**, **Export cloud** to a PLY,
open that PLY and click **Use scan from 3D tab**.

## Measure a CT or MRI stack

1. Click **Open CT stack...** and choose a multi-page TIFF file.
2. Enter the **Voxel size (mm)** of the stack.
3. The stack loads; the Log shows its size and root volume. **Root type** switches to
   **Fibrous root system**.
4. Click **Measure roots**.

The stack is thresholded automatically (Otsu's method) and the largest connected piece is
kept. Slice 0 is taken as the top. Roots must be brighter than the background. For roots
darker than the background, or for a folder of slice images, use the command line:
`phenoforge roots3d <stack> --mode ct --ct-voxel-mm 0.1 --ct-invert`.

## Results

| Tab | Contents |
|---|---|
| **Crown / system** | The traits of the whole crown or root system (trait, value). |
| **Individual roots** | Crown mode only: one row per storage root. |

Values are in metres (m, m², m³) with extra columns in cm, cm² and cm³ for reports. See the
[Trait glossary](traits.md) for every column.

Click **Save CSV...** to save. It writes the file you name (default `roots3d.csv`) with the
crown or system traits, and, in crown mode, a second file ending `_individual_roots.csv`.

## Tips and limits

- Washed roots collapse and overlap when they lie on a surface. Hang them or support them
  (SOP-6, spike stand) so the 3D shape is kept.
- The storage root count depends on the core radius. Check the coloured view; if two roots
  share one colour, try a larger **Crown core radius**.
- Fine roots thinner than a few voxels are lost or merged. Root length in fibrous mode is
  best compared between samples scanned the same way.
- Validate crown volume against water displacement on a few crowns (see
  [Validation](validation.md)).

## From the command line

```
phenoforge roots3d crown.ply --mode crown --aruco-mm 30 --stem-mm 60 --out roots
phenoforge roots3d washed_roots.ply --mode fibrous --axis -z --out roots
phenoforge roots3d stack.tif --mode ct --ct-voxel-mm 0.1 --out ct_roots
```

See [Command line](cli.md).
