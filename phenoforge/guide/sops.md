# Capture SOPs

Good traits start with a good capture. The standard operating procedures (SOPs) are
illustrated PDF guides for each capture route. Print the one you use and keep it next to
the imaging setup.

Where to find them:

- In the PhenoForge source folder: `docs/sop/`.
- As a download: `PhenoForge-SOPs.zip` on the PhenoForge Releases page on GitHub.

If you run PhenoForge from the source folder, the links below open the PDFs. In the Windows
zip version the PDFs are not included; download the SOP zip instead.

| SOP | File | What it covers |
|---|---|---|
| SOP-0 | [SOP-0_Overview_capture_to_traits.pdf](../../docs/sop/SOP-0_Overview_capture_to_traits.pdf) | Overview: which device to use for which job, whether it is metric, and how PhenoForge turns each capture into traits. Start here. |
| SOP-1 | [SOP-1_iPhone_LiDAR.pdf](../../docs/sop/SOP-1_iPhone_LiDAR.pdf) | iPhone or iPad Pro with LiDAR: metric 3D scans of single plants and trays in a few minutes. |
| SOP-2 | [SOP-2_Android_phone.pdf](../../docs/sop/SOP-2_Android_phone.pdf) | Android phone: photogrammetry from photos or video, or an app export, scaled with ArUco markers. |
| SOP-3 | [SOP-3_DSLR_mirrorless.pdf](../../docs/sop/SOP-3_DSLR_mirrorless.pdf) | DSLR or mirrorless camera: high-detail multi-view photogrammetry on a turntable. |
| SOP-4 | [SOP-4_3D_roots.pdf](../../docs/sop/SOP-4_3D_roots.pdf) | 3D root phenotyping: root crowns (storage roots), washed root systems and CT volumes. |
| SOP-5 | [SOP-5_Turntable_rig.pdf](../../docs/sop/SOP-5_Turntable_rig.pdf) | Motorised turntable: build, print and run the PhenoForge turntable for root crowns and potted plants. |
| SOP-6 | [SOP-6_iPhone_roots_spike.pdf](../../docs/sop/SOP-6_iPhone_roots_spike.pdf) | iPhone root scanning on a spike stand: fast 3D root scans by one person, without a turntable. |
| SOP-7 | [SOP-7_iPhonotype_app.pdf](../../docs/sop/SOP-7_iPhonotype_app.pdf) | iPhonotype app (iPhone): guided orbit capture on the phone, analysed in PhenoForge from the .ftscan package. |

## Rules that apply to every capture

- Put an ArUco card (printed from the [Tools](tools.md) tab, measured with a ruler) flat
  beside the plant, visible from every side. It is the only independent check of scale.
- Use diffuse light and a plain, matte, non-green background.
- Avoid wind and do not touch the plant during capture.
- Record the plant ID with the scan (in the app, in the file name, or in the
  [library](library.md)).

See also: [iPhonotype packages](iphonotype.md), [Tools](tools.md), [Roots in 3D](roots-3d.md).
