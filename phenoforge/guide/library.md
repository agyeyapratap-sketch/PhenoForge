# The workspace library

The library keeps your scans organised as **projects**, then **sessions**, then **scans**.
It stores a copy of each scan, its metadata (genotype, treatment and so on) and its
results. You can export one table of all scans for Excel or R.

The library lives in the **Workspace** panel on the left of the window. Everything is stored
as ordinary folders and files on your computer. Nothing is sent anywhere.

## The workspace folder

By default the workspace is the folder `PhenoForge` in your home folder (for example
`C:\Users\<you>\PhenoForge`). The path is shown at the top of the Workspace panel.

To use another folder (for example a project drive), choose **File > Open workspace
folder...**. PhenoForge remembers the last workspace.

Inside the workspace:

```
<workspace>/
    workspace.json                         list of projects
    <project>/project.json                 project details and its sessions
    <project>/<session>/<scan id>/         the copied scan file
    <project>/<session>/<scan id>/scan.json      metadata
    <project>/<session>/<scan id>/results/traits.json   latest results
```

Scan IDs are the file name plus a short random code, for example `W123_a1b2c3`.

## Set up a project and session

1. Click **Project +** and type a project name, for example `Wheat drought 2026`.
2. Select the project in the tree.
3. Click **Session +**. The name suggested is today's date (`yyyy-MM-dd`). Change it if you
   like, for example `Week 3`.

## Add scans

1. Select a session in the tree.
2. Click **Import** (or **File > Import scan into library...**).
3. Choose one or more scans. They are copied into the session folder.

Other ways to add scans:

- Select a session, then drag several scan files from Windows Explorer onto the window.
- In the [Wi-Fi receive](wifi.md) window, tick **Add each scan to the library session
  selected on the left**.

The tree shows each scan's file name, with the plant ID and treatment in the **Info** column
when they are filled in. A session shows how many scans it holds.

## Metadata

Double-click a scan in the tree to open it. The **Scan metadata** form below the tree shows
its details. The fields are:

| Field | Use it for |
|---|---|
| species | The species, for example *Triticum aestivum*. |
| genotype | Line, variety or genotype code. |
| treatment | Treatment name, for example `drought`. |
| plant id | Plant, pot or barcode ID. |
| tray | Tray or bench position. |
| qr | Text from a QR label. |
| gps | Field coordinates. |
| notes | Anything else. |

Type in the boxes and click **Save metadata**. Save metadata only works for a scan that was
opened from the library (double-clicked in the tree).

For iPhonotype packages, the plant id, genotype, treatment and notes typed in the app are
copied into empty boxes when the scan loads. Click **Save metadata** to keep them.

## Results are saved automatically

When you open a scan by double-clicking it in the library and click **Run analysis**, the
results are saved into that scan's `results/traits.json`. The Log says "results saved to the
library". Running the analysis again replaces them.

Scans received over [Wi-Fi](wifi.md) with **Add each scan to the library session** ticked are
opened from the library too, so their results are also saved. Scans opened in other ways
(Open scan, drag and drop, the Start page, Recent scans) are not linked to the library, even
if a copy is in the library. Their results are only saved when
you click **Save results**. To link them, double-click the scan in the library tree.

## Export the library table

1. Choose **File > Export library table (CSV)...**.
2. Choose a file name (default `library.csv`).

The table has one row per scan in the whole workspace, with:

- `project` and `session`,
- the scan record: `id`, `file` (the copy in the library), `original` (where it was imported
  from), `imported` (date and time) and every metadata field,
- the whole-scan traits from the latest saved results (the same columns as the **Scan**
  tab). Scans that have never been analysed have empty trait columns.

Per-plant, leaf, head and object tables are not in the library table. Use **Save results**
or [Analyse a whole folder](batch.md) for those.

## Tips

- Keep one workspace per experiment, or one for everything: both work.
- The workspace can be on a network drive, but large scans load faster from a local disk.
- Back up the workspace folder like any other data folder.
