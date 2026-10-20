# Fruit, tubers and seeds

PhenoForge can measure each separate object in a scan: fruit on a bench, tubers or potatoes
after harvest, seeds or grains on a tray. For each object you get length, width, thickness,
volume, shape and colour.

## Capture tips

- Lay the objects on a flat bench or tray, **not touching** each other. Objects that touch are
  measured as one.
- Put an ArUco card flat on the bench for the scale (see [Tools](tools.md)).
- Scan from all around and from above. A scan sees only the top and sides of an object lying
  on a bench, so its underside is missing (see "Limits" below).
- For small seeds, use a high-resolution method (DSLR photogrammetry, SOP-3) rather than phone
  LiDAR.

## Steps

1. On the Start page click **Fruit, tubers or seeds** and choose the scan. Or open the scan and
   choose the preset **Fruit / objects on a bench** on the 3D analysis tab.
2. The preset ticks **Measure each object (fruit, tubers, seeds)**, sets **Vegetation index** to
   **none** (keeps all colours, so red fruit or brown tubers are not removed) and turns leaf
   candidates off.
3. Keep **Fit ground plane, set z = 0** and **Remove ground points** ticked. The bench must be
   removed, otherwise it joins all objects into one.
4. Set the scale in **2 Metric scale** (ArUco markers are recommended).
5. Click **Run analysis**.

The results open on the **Objects** tab, one row per object. The Log says how many objects
were measured and how many points were left over (noise and pieces too small to be an
object).

## How objects are separated

Points closer together than a small distance (worked out from the point spacing) are joined
into one object (DBSCAN clustering). Groups of fewer than 50 points are ignored.

## Results

Lengths are in m, areas in m² and volumes in m³ when the scan is metric.

| Column | Meaning |
|---|---|
| `object_id` | Object number. |
| `n_points` | Points in the object. |
| `centroid_x`, `centroid_y`, `centroid_z` | Centre of the object. |
| `length`, `width`, `thickness` | Size along the object's three main axes (longest, middle, shortest), measured between the 1st and 99th percentile of the points so a few stray points are ignored. On a scanned surface this reads about 2 % short of a calliper measurement. |
| `axis_length_x`, `axis_length_y`, `axis_length_z` | Direction of the long axis (a unit vector). |
| `hull_volume`, `hull_area` | Volume and surface area of the convex hull (the shrink-wrap shape). |
| `equiv_diameter` | Diameter of a sphere with the same hull volume. |
| `sphericity` | 1 for a perfect sphere, lower for long or flat objects. Uses the hull, so dents are bridged. |
| `elongation` | length / width. |
| `flatness` | width / thickness. |
| `height_max`, `height_min` | Top and bottom of the object above the bench. |
| `mean_r`, `mean_g`, `mean_b` | Mean colour (0–1). |
| `hue_deg` | Hue of the mean colour, in degrees (0 = red, 60 = yellow, 120 = green). |
| `metric` | True if the values are in metres. |

The **Scan** tab still shows the whole-scan traits of everything together.

## Limits

- **Touching objects** are measured as one. Spread them out.
- **One-sided scans**: an object lying on a bench is only seen from above and the sides. Its
  hull volume is the volume of what was seen, which underestimates the true volume. Thickness
  is affected the same way. Turn the objects over and scan again if you need the underside, or
  validate against water displacement.
- **Concave shapes** (for example a kidney-shaped tuber): hull volume and sphericity bridge the
  hollows, so volume is overestimated for strongly concave objects.
- There is no fruit-specific or crop-specific model. The method is generic.

## From the command line

```
phenoforge analyse bench.ply --preset fruit --aruco-mm 50 --out results
```

This writes `bench_objects.csv` among the result files. See [Command line](cli.md).
