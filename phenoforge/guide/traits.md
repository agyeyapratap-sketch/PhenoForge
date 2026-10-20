# Trait glossary

This page explains every column PhenoForge writes. Find a column with the search box in the
help window (type the column name).

## Units

- When the scan is **metric**, lengths are in **metres (m)**, areas in **m²** and volumes in
  **m³**, even where the column name has no unit (for example `height_max`). Multiply by 100
  for cm, 10,000 for cm² and 1,000,000 for cm³.
- When the scan is **not metric**, the same columns are in the scan's own units, which are
  unknown. The `metric` column tells you which. Do not mix metric and non-metric rows.
- Column names ending in `_m2` or `_m3` keep that name even when the scan is not metric.
- Colours are on a 0–1 scale unless stated.

"Points" are the 3D points of the scan after cleaning (outlier removal, ground removal and the
vegetation filter). Every 3D trait describes only what was scanned: hidden leaves, the inside
of a dense canopy and very thin parts are under-represented.

## Identification columns (CSV files)

| Column | Meaning |
|---|---|
| `scan` | Scan name (the file name without its last extension). The default join column for [Validation](validation.md). |
| `plant_id`, `genotype`, `treatment` | From an iPhonotype package (typed in the app). In `<scan>_plant.csv` and `all_scans.csv`. |
| `operator`, `started_utc` | From an iPhonotype package. In `<scan>_plant.csv` only. |
| `plant` | Plant number (from 0, in reading order). In per-plant and leaf tables. |

## Whole-scan and per-plant traits

These appear on the **Scan** tab (`<scan>_plant.csv`, `all_scans.csv`) for everything left
after cleaning, and on the **Per plant** tab (`<scan>_plants.csv`) for each separated plant.

| Column | Unit | Meaning and how it is computed | Caveats |
|---|---|---|---|
| `n_points` | count | Number of points measured. | Depends on scan density, not the plant. |
| `metric` | True/False | Whether the values are in metres. | |
| `height_max` | m | Highest point above the ground plane (z = 0 after **Fit ground plane**). Without ground fitting, above the lowest point. | Sensitive to a single stray point; prefer `height_p99` for noisy scans. |
| `height_p99` | m | 99th percentile of point heights: 1 % of points are higher. | Robust to strays; slightly below the true top. |
| `height_p95` | m | 95th percentile of point heights. | |
| `height_mean` | m | Mean height of all points. | Depends on where points are dense. |
| `centroid_height` | m | Height of the centre of the points. Same value as `height_mean`. | |
| `spread_x` | m | Width along the scan's x axis, between the 1st and 99th percentile of points. | The x axis is the scan's, not the plant's own orientation. |
| `spread_y` | m | The same along the y axis. | As above. |
| `spread_max_diameter` | m | Twice the 99th percentile distance of points from the plant centre, seen from above. | |
| `footprint_hull_m2` | m² | Area of the convex hull of the plant seen from above (the area inside a rubber band stretched around it). | Includes gaps between leaves. |
| `footprint_perimeter_m` | m | Perimeter of that convex hull. | |
| `projected_area_m2` | m² | Canopy cover seen from above: the area of grid cells that contain at least one point. | Grid size is `grid_size`; gaps between leaves are not filled. Depends a little on point density. |
| `grid_size` | m | Cell size used for `projected_area_m2`: twice the median spacing between points. | Describes the scan, not the plant. |
| `hull_volume_m3` | m³ | Volume of the 3D convex hull (shrink-wrap). | Includes all air between leaves; one stray point can inflate it. |
| `hull_surface_m2` | m² | Surface area of the 3D convex hull. | |
| `voxel_volume_m3` | m³ | "Virtual biomass": the number of occupied cubes (size `voxel_size`) times the cube volume. | A relative measure. Calibrate it against harvested dry weight on the [Validation](validation.md) tab. Depends on `voxel_size`. |
| `voxel_size` | m | Cube size used for `voxel_volume_m3` (same as `grid_size`). | |
| `solidity` | ratio | `voxel_volume_m3` / `hull_volume_m3`: how much of the hull is filled. | Relative; depends on voxel size. |
| `surface_area_m2` | m² | Leaf (surface) area. For a mesh scan (OBJ, GLB, USDZ): the area of the mesh triangles. For a point cloud: points are first smoothed onto local surfaces, then each point is given the small area it covers, and these are added up. | Counts one side of thin leaves. Only surfaces that were seen: overlapping leaves are underestimated. About +4 % on clean synthetic leaves, up to +13 % with heavy noise. |
| `surface_area_method` | text | `mesh` or `mls-density` (the point method). | |
| `lean_deg` | degrees | Angle between vertical and the line from the centre of the lowest 10 % of points to the centre of the highest 10 %. 0 = upright. | |
| `exg_mean` | index | Mean Excess Green, ExG = 2g − r − b on chromatic coordinates (r = R/(R+G+B) etc.). | Depends on light and camera; use [Colour correction](colour.md) to compare sessions. |
| `gli_mean` | index | Mean Green Leaf Index, (2G − R − B) / (2G + R + B). | As above. |
| `vari_mean` | index | Mean VARI, (G − R) / (G + R − B), limited to −1…1. | As above. |
| `green_fraction` | 0–1 | Fraction of points with GLI above 0.05. | Close to 1 after the vegetation filter. |
| `rgb_mean` | 0–1 | Mean red, green and blue. In `<scan>_traits.json` only (not on screen or in CSV files). | |
| `n_labels` | count | Number of different labels (plants or leaves) among the points measured, when the scan has labels. | Usually absent on the Scan tab, 1 in per-plant rows. |

Per-plant rows use the same ground plane as the whole scan, so plant heights are comparable.

## Head and tiller summary (Scan tab)

Added when **Count wheat heads** or **Count tillers** is ticked. See [Wheat](wheat.md).

| Column | Unit | Meaning |
|---|---|---|
| `head_count` | count | Number of heads found (heuristic). |
| `head_length_mean`, `head_length_sd` | m | Mean and standard deviation of head length. |
| `head_width_mean` | m | Mean head width. |
| `head_top_height_mean` | m | Mean height of the head tops above the ground. |
| `method` | text | How head candidates were chosen: `auto:colour` (straw hue) or `auto:shape` (bulky shape). |
| `tiller_count` | count | Number of tillers (stems that continue through at least half of a band above the ground). |
| `band_low`, `band_high` | m | Height range of the band used for the tiller count. |
| `band_counts` | list | Tiller count in each band tried (JSON only). |
| `band_coverage` | 0–1 | Mean fraction of slices in which each counted stem was seen. |
| `stem_diameter_mean` | m | Mean diameter of the counted stems. |
| `plant_height` | m | Plant height used to set the search limits (99.8th percentile of plant point heights). |
| `heuristic` | True | A reminder that these counts are rule-based estimates. |

The head and tiller methods also write `metric`.

## Heads tab (`<scan>_heads.csv`)

| Column | Unit | Meaning |
|---|---|---|
| `head_id` | | Head number. |
| `length` | m | Extent along the head's long axis (1st to 99th percentile of its points). |
| `width` | m | Extent along the second axis. Awns make it larger. |
| `thickness` | m | Extent along the third axis. |
| `aspect` | ratio | length / width. |
| `top_height` | m | 99th percentile height of the head's points above the ground. |
| `centroid_x`, `centroid_y`, `centroid_z` | m | Centre of the head. |
| `tilt_deg` | degrees | Angle of the head's long axis from vertical. |
| `n_points` | count | Points in the head. |
| `mean_r`, `mean_g`, `mean_b` | 0–1 | Mean colour. |

## Leaves tab (`<scan>_leaves.csv`)

One row per leaf candidate. See [The 3D analysis tab](3d-analysis.md) and
[AI leaf separation](leaves-ai.md).

| Column | Unit | Meaning | Caveats |
|---|---|---|---|
| `plant` | | Plant the leaf belongs to (0 for a single plant). | |
| `leaf` | | Leaf number within the scan. | |
| `n_points` | count | Points in the leaf. Candidates under 30 points are dropped. | |
| `area_m2` | m² | One-sided leaf area, by the same point method as `surface_area_m2`. | Empty (NaN) for mesh scans (OBJ, GLB, USDZ). |
| `pca_length` | m | Approximate leaf length from the spread of its points along its main direction (4 × the standard deviation). | A straight-line estimate; curved leaves read short. |
| `length_geodesic` | m | Length along the leaf surface between its two farthest ends (approximates midrib length). | Large leaves are sub-sampled to 4,000 points. |
| `bbox_x`, `bbox_y`, `bbox_z` | m | Size of the box around the leaf along x, y and z. | |
| `cx`, `cy`, `cz` | m | Centre of the leaf. | |
| `top_z` | m | Highest point of the leaf. | |

Leaf candidates are visible-leaf candidates: touching leaves can merge, and one leaf can be
split.

## Objects tab (`<scan>_objects.csv`)

See [Fruit, tubers and seeds](objects.md) for details.

| Column | Unit | Meaning |
|---|---|---|
| `object_id` | | Object number. |
| `n_points` | count | Points in the object. |
| `centroid_x`, `centroid_y`, `centroid_z` | m | Centre. |
| `length`, `width`, `thickness` | m | Extents along the object's three main axes (1st to 99th percentile). About 2 % short of calliper size on a scanned surface. |
| `axis_length_x`, `axis_length_y`, `axis_length_z` | | Direction of the long axis (unit vector). |
| `hull_volume` | m³ | Convex hull volume. One-sided scans give the volume of what was seen. |
| `hull_area` | m² | Convex hull surface area. |
| `equiv_diameter` | m | Diameter of the sphere with the same hull volume. |
| `sphericity` | 0–1 | Wadell sphericity from the hull: 1 for a sphere. |
| `elongation` | ratio | length / width. |
| `flatness` | ratio | width / thickness. |
| `height_max`, `height_min` | m | Top and bottom of the object above the bench. |
| `mean_r`, `mean_g`, `mean_b` | 0–1 | Mean colour. |
| `hue_deg` | degrees | Hue of the mean colour (0 red, 60 yellow, 120 green). |
| `metric` | True/False | Whether lengths are in metres. |

## vs iPhonotype tab (`<scan>_vs_iphonotype.csv`)

| Column | Meaning |
|---|---|
| `trait` | The trait compared, with its unit (cm, cm², cm³). |
| `PhenoForge` | PhenoForge's value converted to cm units. Empty (NaN) when the scan is not metric. |
| `iPhonotype app` | The app's own value from the package. |
| `difference_percent` | (PhenoForge − app) / app × 100. |

See [iPhonotype](iphonotype.md) for which traits are paired.

## Package tab (`<scan>_package.csv`)

The fields read from an iPhonotype package (`source`, `plant_id`, `genotype`, `treatment`,
`operator`, `notes`, `session_id`, `started_utc`, `ended_utc`, `capture_seconds`, `scan_mode`,
`scan_workflow`, `scan_target`, `app_version`, `device`, `ios_version`, `photos`,
`photos_recommended`, `photos_minimum`, `coverage_estimate`, `light_lux_mean`, `light_lux_min`,
`light_lux_max`, `par_mean_umol_m2_s`, `leaf_reflectance_mean_percent`, `splat_units`,
`scale_source`, `scale_confidence`, `scale_verified`, `used_lidar`, `label_text`, `warnings`).
They are explained on the [iPhonotype](iphonotype.md) page. The light and PAR values are the
app's estimates from the camera, not sensor readings.

## Extra items in `<scan>_traits.json`

| Item | Meaning |
|---|---|
| `options` | Every analysis setting used. |
| `scale` | How the scale was set: `method` (`aruco` or `manual`), `factor` (multiplier applied to the coordinates), and for ArUco `markers` (each marker's measured side in scan units), `cv_percent` (spread between markers) and `rejected` (marker IDs left out). |
| `pot_centres` | Pot centres used for a pot grid. |
| `leaf_labels_note` | A reminder of what the leaf candidates are. |
| `history` | Every processing step applied to the scan, in order. |
| `units` | `m, m2, m3`, or `scan units (not scaled)`. |

## Roots 3D: crown and system (`roots3d.csv`)

See [Roots in 3D](roots-3d.md). Columns ending in `_m`, `_m2`, `_m3` also appear as `_cm`,
`_cm2`, `_cm3` (the same value in cm units).

Root crown mode:

| Column | Unit | Meaning |
|---|---|---|
| `voxel_size` | m | Cube size of the solid model. |
| `n_points` | count | Points of the cleaned crown. |
| `crown_volume_m3` | m³ | Volume of the filled solid crown (summed over sectors when **Split crown into sectors** is above 1). |
| `crown_volume_whole_m3` | m³ | Volume of the whole crown filled in one piece. |
| `crown_surface_m2` | m² | Surface area of the smoothed solid. |
| `surface_to_volume_per_m` | 1/m | `crown_surface_m2` / `crown_volume_m3`. |
| `crown_diameter_m` | m | Largest width across the crown, seen along the stem axis. |
| `crown_depth_m` | m | Depth from the top of the oriented object (the stem top, before the stem cut) to the deepest point. |
| `cylinder_soil_volume_m3` | m³ | Volume of a cylinder with the crown diameter and depth (the soil the crown occupies). |
| `compactness_percent` | % | Crown volume as a percentage of the cylinder soil volume. |
| `convex_hull_volume_m3` | m³ | Convex hull volume of the crown points. |
| `root_density_kg_m3`, `root_density_g_cm3` | kg/m³, g/cm³ | Fresh weight divided by crown volume (only when **Root fresh weight** is given). |
| `root_number` | count | Number of storage roots found. |
| `root_length_mean_m`, `root_length_max_m` | m | Mean and longest storage root length. |
| `root_angle_mean_deg` | degrees | Mean storage root angle from vertical. |
| `root_volume_sum_m3` | m³ | Sum of the storage root volumes. |


Individual roots (`..._individual_roots.csv`, **Individual roots** tab):

| Column | Unit | Meaning |
|---|---|---|
| `root` | | Root number. |
| `volume_m3` | m³ | Volume of the root. |
| `length_m` | m | Length along the root, from where it leaves the crown core to its tip. |
| `straight_length_m` | m | Straight-line distance from attachment to tip. |
| `angle_from_vertical_deg`, `angle_from_horizontal_deg` | degrees | Angle of the attachment-to-tip line. |
| `mean_diameter_m` | m | Diameter of a cylinder with the root's volume and length. |
| `tip_depth_m` | m | Depth of the tip below the top of the oriented object. |
| `attach_x`, `attach_y` | m | Where the root leaves the core. |
| `tip_x`, `tip_y`, `tip_z` | m | Position of the tip. |

Fibrous root system and CT mode:

| Column | Unit | Meaning |
|---|---|---|
| `voxel_size` | m | Cube size. |
| `root_volume_m3` | m³ | Volume of the solid root system. |
| `total_length_m` | m | Total length of the 3D skeleton (all centre lines). |
| `n_tips` | count | Skeleton end points. |
| `n_branch_points` | count | Branching points. |
| `max_depth_m`, `max_width_m` | m | Vertical and largest horizontal extent. |
| `convex_hull_volume_m3` | m³ | Convex hull volume of the skeleton. |
| `solidity` | ratio | Root volume / convex hull volume. |
| `primary_length_m` | m | Longest path along the skeleton from the top point. |
| `length_width_ratio` | ratio | `max_depth_m` / `max_width_m`. |
| `length_by_depth_m`, `depth_bin_edges_m` | m | Root length in 10 depth layers and the layer boundaries. Calculated, but in this version not shown on screen or written to the CSV file. |
| `d50_depth_m` | m | Depth above which half of the root length lies. |
| `mean_diameter_m` | m | Diameter of a cylinder with the root volume and total length. |

## 2D photos (`images_summary.csv`, `images_blobs.csv`)

Listed on [Photos from above](images-2d.md): `image`, `width_px`, `height_px`,
`canopy_area_px`, `canopy_cover`, `n_blobs`, `mm_per_px`, `n_markers`, `exg_mean_canopy`,
`canopy_area_mm2`; and per blob `blob`, `area_px`, `hull_area_px`, `perimeter_px`, `cx`, `cy`,
`length_px`, `width_px`, `solidity`, `area_mm2`, `hull_area_mm2`, `length_mm`.

## 2D roots (`roots.csv`, Roots tab, root video CSV)

Listed on [Root photos and video](roots-2d.md): `total_length_px`, `primary_length_px`,
`lateral_length_px`, `n_tips`, `n_laterals`, `n_branch_points`, `mask_area_px`, `depth_px`,
`width_px`, `hull_area_px`, the `_mm` and `_mm2` versions, and `mm_per_px`. The root video CSV
adds `frame`, `image`, `name`, `change_total_pct`, `sentence`, `start_s` and `duration_s`.

## Other outputs

- **Compare** (`comparison.csv`): `trait`, `a`, `b`, `change`, `change_percent`. See
  [Compare](compare.md).
- **Validation**: `n`, `mae`, `rmse`, `bias`, `mape_percent`, `r2`, `pearson_r`, `ccc`, `slope`,
  `intercept`, `loa_low`, `loa_high`, `calib_a`, `calib_b`; masks: `iou`, `dice`, `precision`,
  `recall`, `area_pred_px`, `area_ref_px`, `area_error_percent`. See [Validation](validation.md).
- **Frame check** (`frame_check.csv`): `name`, `iou`, `dice`, `precision`, `recall`,
  `points_in_view`, `rendered_px`, `photo_px`, `roi_px`, `error`. See [Validation](validation.md).
- **Head detector** (`heads.csv`, `head_boxes.csv`): `image`, `head_count`, `mean_conf`;
  `box`, `x1`, `y1`, `x2`, `y2`, `conf`. See [Wheat](wheat.md).
- **Scale evidence**: `frame`, `time_s`, `sharpness`, `n_markers`, `marker_ids`,
  `marker_side_px`, `mm_per_px`, `mm_per_px_each`, `skew_pct`, `usable`. See [Tools](tools.md).
