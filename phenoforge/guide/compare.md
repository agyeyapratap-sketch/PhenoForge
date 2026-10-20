# Compare two scans

The Compare tab analyses two scans with the same settings and shows how each trait changed.
Use it for two time points of one plant (growth), or a treated and a control plant.

## Steps

1. Set up the analysis on the [3D analysis](3d-analysis.md) tab first: preset, cleaning,
   scale and plant settings. The Compare tab uses those settings for both scans.
2. Open the **Compare** tab.
3. Click **Scan A...** and choose the first scan (for example the earlier date).
4. Click **Scan B...** and choose the second scan. You can also paste file paths into the
   boxes.
5. Click **Analyse both (uses 3D settings)**.

Both scans are analysed one after the other. The Log shows the progress.

## Reading the results

- The two 3D views show the cleaned scans side by side. Turning or zooming one view turns
  the other the same way, so you can look at the same side of both plants.
- The table lists every whole-scan trait that is a number in both scans:

| Column | Meaning |
|---|---|
| `trait` | The trait name (see the [Trait glossary](traits.md)). |
| `a` | Value for scan A. |
| `b` | Value for scan B. |
| `change` | b minus a. |
| `change_percent` | Change as a percentage of a. |

The table compares the whole-scan traits (the **Scan** tab), not individual plants or leaves.

## Things to watch

- Use the same scale method for both scans. If one is metric and the other is not, the
  numbers are not comparable.
- The two scans are not moved onto each other. The views only share the camera angle.
  Plants scanned in different positions will appear in different places.
- Rows such as `n_points`, `grid_size` and `voxel_size` describe the scans, not the plants.
  Ignore them when you look at growth.
- For many plants or many dates, use [Analyse a whole folder](batch.md) and compare the
  `all_scans.csv` rows in Excel or R instead.

## From the command line

```
phenoforge compare week1.ply week3.ply --preset tray --expected 6 --out growth
```

This prints each trait with its change and writes `growth\comparison.csv`. It takes the same
analysis options as `phenoforge analyse`. See [Command line](cli.md).
