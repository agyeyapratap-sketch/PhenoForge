# 3D print export

The **3D print** tab turns a scan into files for a multi-colour 3D printer: a 3MF file with
one material per colour, one STL file per colour, and an OBJ file. Use it for outreach,
teaching or to keep a physical record of a plant.

## Steps

1. Open the scan on the [3D analysis](3d-analysis.md) tab. Usually run the analysis too, so
   stray points, soil and pot are removed first. The tab's note says: "Uses the analysed
   (cleaned) scan from the 3D tab, or the original if not analysed."
2. Open the **3D print** tab.
3. Choose the settings (table below).
4. Click **Export 3MF + STL + OBJ bundle...** and choose an output folder.
5. When it finishes, the box at the bottom shows the colours, the size in mm and the files
   written.

## Settings

| Setting | What it does | Default |
|---|---|---|
| **Filament colours** | How many colours to reduce the scan to (1–16). Colours are grouped automatically (k-means clustering in Lab colour space). | 4 |
| **Fixed palette** | Leave empty for automatic colours. Or type your filament colours as hex codes separated by commas, for example `2d5a1e,7fb341,c9b26b,5b3a1e`. Then the number of colours is the number of codes. | Empty |
| **Print height (0 = true size)** | Scales the model so it is this tall, in mm. With 0, a metric scan is printed at true size. | 120 mm |
| **Surface** | How a surface is made from the points. **poisson**: smooth, closed surface (best for most plants). **alpha** and **ball**: follow the points more closely, may leave holes. **existing**: use the scan's own mesh (for OBJ, GLB, USDZ scans). | poisson |
| **Poisson depth** | Detail of the poisson surface (5–12). Higher = more detail and larger files. | 9 |
| **Base plate** | Thickness (mm) of a flat base added under the model so it stands up. 0 = no base. The base takes the first colour: the darkest with automatic colours, or the first code of a fixed palette. | 2 mm |
| **Use the original scan (keep soil and pot)** | Prints the scan as loaded, without cleaning. | Off |

## Output files

In the folder you chose (`<name>` is the scan name):

| File | Contents |
|---|---|
| `<name>.3mf` | One model with one part and material per colour. Open in Bambu Studio, PrusaSlicer or similar and assign filaments. |
| `<name>_c0_xxxxxx.stl`, `<name>_c1_...stl` | One STL per colour; `xxxxxx` is the colour's hex code. |
| `<name>.obj` | The coloured model as OBJ. |
| `<name>_palette.json` | The colours, triangles per colour, size in mm and file list. |

## Tips

- Thin leaves print badly at small sizes. Print larger, or accept thicker leaves from the
  poisson surface.
- If the surface has "bubbles" or a skin between leaves, try **alpha** or **ball**, or a lower
  **Poisson depth**.
- A 3D print is a model of the scan, not of the plant. Missing parts in the scan are missing
  in the print.

## From the command line

```
phenoforge print plant.ply --colours 4 --height-mm 120 --out print_files
```

Add `--raw` to skip cleaning. See [Command line](cli.md).
