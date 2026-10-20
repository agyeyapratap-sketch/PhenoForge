# Analyse a whole folder

Use this to analyse many scans with the same settings, for example all plants from one
imaging day. You get one set of result files per scan and one summary table,
`all_scans.csv`, with one row per scan.

## Steps

1. Put all scans in one folder. Each `.ftscan`, `.zip`, `.ply`, `.obj`, `.usdz` (or other
   supported 3D file) is one scan. An unzipped `.ftscan` folder also counts as one scan.
   Sub-folders are not searched.
2. Open **File > Analyse a whole folder...** (or the Start page button **Analyse a whole
   folder**, or the Tools tab button **Analyse a whole folder…**).
3. **Scans**: click **Browse…** and choose the folder.
4. **Results folder**: where the files go. By default `batch_results` in your workspace.
5. **Settings**: choose a preset (see [The 3D analysis tab](3d-analysis.md)). It starts
   with the preset selected on the 3D analysis tab.
6. Optional: tick **Use the current 3D-tab settings instead (scale, plants, leaves…)** to use
   exactly what is set on the 3D analysis tab, including the scale source, marker size and
   any changes you made.
7. Optional: tick **Also save each cleaned point cloud (.ply)**.
8. Click **Run**. The window closes and the work continues in the background.

The Log shows `[3/20] scanname` for each scan. When it finishes it says
`batch done: 19 of 20 scans; table in ...\all_scans.csv`.

Scans that fail are listed in the Log as `FAILED name: reason` and skipped. The others
continue.

## Which settings to use

A preset alone uses its own defaults. In particular, the presets do not set a scale except
"Photos or video with ArUco", which uses 50 mm ArUco markers. If your scans need a
different marker size, two picked points or a manual factor, set it on the 3D analysis tab
and tick **Use the current 3D-tab settings instead**.

"Two picked points" cannot be used in a batch in a meaningful way, because the same picks
would be applied to every scan.

## Output files

For each scan (`<scan>` is the file name without its last extension):

- `<scan>_traits.json`, `<scan>_plant.csv` and, when they have rows, `<scan>_plants.csv`,
  `<scan>_leaves.csv`, `<scan>_heads.csv`, `<scan>_objects.csv`, `<scan>_vs_iphonotype.csv`
  and `<scan>_package.csv`. These are the same as **Save results** on the 3D analysis tab.
- `<scan>_clean.ply` if you ticked **Also save each cleaned point cloud (.ply)**.

And one summary table:

- `all_scans.csv`: one row per successful scan. The first column is `scan` (the file name).
  For iPhonotype packages it is followed by `plant_id`, `genotype` and `treatment`. Then come
  the whole-scan traits (the **Scan** tab columns). See the [Trait glossary](traits.md).

The `scan` column is the default join column on the [Validation](validation.md) tab, so you
can compare `all_scans.csv` directly with a table of hand measurements that has a `scan`
column.

Batch results are not added to the workspace library.

## From the command line

```
phenoforge analyse D:\scans\2026-10-20 --preset iphonotype --out D:\results\2026-10-20
```

This writes the same per-scan files and, when there is more than one scan, `all_scans.csv`.
See [Command line](cli.md).
