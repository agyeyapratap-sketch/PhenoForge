"""Build the illustrated capture SOP PDFs (one per device type, plus an overview).

    python docs/sop/make_sops.py            -> docs/sop/*.pdf

Illustrations were created in BioRender (links in FIGURE_CREDITS). Screenshots are of
PhenoForge itself. Requires reportlab (pip install reportlab).
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

HERE = Path(__file__).parent
FIG = HERE / "figures"
GREEN = colors.HexColor("#2f6b3a")
LIGHT = colors.HexColor("#eef5ec")
SLATE = colors.HexColor("#33424a")
AMBER = colors.HexColor("#fff4dc")
RED = colors.HexColor("#fdecec")

FIGURE_CREDITS = {
    "iphone": "https://app.biorender.com/illustrations/8c40acaec5d437ac422dca1d",
    "android": "https://app.biorender.com/illustrations/c16d76e2f2bfdeed9ce947ed",
    "dslr": "https://app.biorender.com/illustrations/dcb078d4934d95822056474a",
    "roots": "https://app.biorender.com/illustrations/53fe8fbd66876aab190cfa24",
    "workflow": "https://app.biorender.com/illustrations/a8401c1320ac7f644c979d35",
    "turntable": "https://app.biorender.com/illustrations/a2975abb81ffae11939a0145",
    "spike": "https://app.biorender.com/illustrations/39c6091d1dab60274f047648",
}

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=20, leading=24, textColor=colors.white, alignment=TA_LEFT)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], fontSize=10.5, leading=14, textColor=colors.white)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=13.5, leading=17, textColor=GREEN, spaceBefore=8, spaceAfter=4, keepWithNext=1)
BODY = ParagraphStyle("BODY", parent=ss["Normal"], fontSize=9.6, leading=13)
SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=8, leading=10, textColor=colors.HexColor("#5b6670"))
STEP_T = ParagraphStyle("STEPT", parent=BODY, fontName="Helvetica-Bold", fontSize=10.5, leading=13)
NUM = ParagraphStyle("NUM", parent=BODY, fontName="Helvetica-Bold", fontSize=15, textColor=colors.white, alignment=1)

W = A4[0] - 30 * mm


def banner(title, subtitle, sop_id):
    t = Table([[Paragraph(title, H1)], [Paragraph(subtitle, SUB)], [Paragraph(f"{sop_id} · PhenoForge capture SOP · version 1.0 (October 2026)", SUB)]],
              colWidths=[W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (0, 0), 10), ("BOTTOMPADDING", (0, -1), (-1, -1), 10)]))
    return t


def figure(name, width=W, caption=None):
    p = FIG / name
    from PIL import Image as PI

    w, h = PI.open(p).size
    img = Image(str(p), width=width, height=width * h / w)
    out = [img]
    if caption:
        out.append(Paragraph(caption, SMALL))
    return out


def box(title, items, bg=LIGHT, cols=1):
    paras = [Paragraph("• " + i, BODY) for i in items]
    if cols == 2:
        half = (len(paras) + 1) // 2
        rows = [[paras[i], paras[i + half] if i + half < len(paras) else ""] for i in range(half)]
        inner = Table(rows, colWidths=[(W - 16) / 2] * 2)
    else:
        inner = Table([[p] for p in paras], colWidths=[W - 16])
    inner.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 1)]))
    t = Table([[Paragraph(f"<b>{title}</b>", BODY)], [inner]], colWidths=[W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def steps(rows):
    data = []
    for k, (title, text) in enumerate(rows, 1):
        n = Table([[Paragraph(str(k), NUM)]], colWidths=[9 * mm], rowHeights=[9 * mm])
        n.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ROUNDEDCORNERS", [4, 4, 4, 4])]))
        data.append([n, [Paragraph(title, STEP_T), Paragraph(text, BODY)]])
    t = Table(data, colWidths=[13 * mm, W - 13 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                           ("LINEBELOW", (1, 0), (1, -2), 0.3, colors.HexColor("#d6dfd4"))]))
    return t


def table(header, rows, widths):
    data = [[Paragraph(f"<b>{h}</b>", BODY) for h in header]] + [[Paragraph(c, BODY) for c in r] for r in rows]
    t = Table(data, colWidths=[w * W for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c9d3c6")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5)]))
    return t


def footer(canvas, doc, credit):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(colors.HexColor("#6b7680"))
    canvas.drawString(15 * mm, 9 * mm, f"Illustration created in BioRender ({credit}). Screenshots: PhenoForge (MIT licence).")
    canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"page {doc.page}")
    canvas.restoreState()


def build(fname, credit_key, story):
    doc = SimpleDocTemplate(str(HERE / fname), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=12 * mm, bottomMargin=16 * mm, title=fname[:-4].replace("_", " "),
                            author="PhenoForge")
    cb = lambda c, d: footer(c, d, FIGURE_CREDITS[credit_key])
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    print("wrote", HERE / fname)


SCALE_NOTE = ("Print the ArUco sheet from <b>Tools &gt; Printable ArUco marker sheet</b> (DICT_4X4_50, 50 mm). "
              "Print at 100 %, measure one marker with a ruler, and write the measured size on the card. "
              "Glue it flat on rigid card; a curled marker reads short.")

ANALYSE_STEPS = [
    ("Open the scan", "<b>3D analysis</b> tab &gt; <b>Open scan…</b>, or add it to the library (left panel: Project + / Session + / Import) "
                      "so metadata and results are stored with it."),
    ("Clean and frame", "Keep <i>Remove outliers</i>, <i>Fit ground plane</i> and <i>Remove ground points</i> ticked. "
                        "Tick <i>Input is Y-up</i> for GLB/glTF/USDZ exports from phone apps if the plant lies on its side."),
    ("Set the scale", "Section 2: choose <b>ArUco markers</b> and type the measured marker side. For LiDAR scans choose "
                      "<i>Already metric</i> but still check: <b>Markers image</b> shows each marker's size after scaling."),
    ("Segment", "Section 3: <i>single</i> for one plant, <i>watershed</i> for a tray of touching plants (enter the number of plants), "
                "or <i>grid</i> with rows, columns and pot pitch for a bench of equally spaced pots."),
    ("Run and export", "Press <b>Run analysis</b>. Results appear in the Scan / Per plant / Leaves tables; "
                       "<b>Save results</b> writes JSON and CSV. Colour the view by Height, Greenness or Plants to check the segmentation."),
]


def overview():
    s = [banner("PhenoForge: from capture to traits", "Which device to use, what to capture, and how the app turns it into numbers", "SOP-0"),
         Spacer(1, 6)]
    s += figure("workflow.jpg", caption="Workflow: import → clean → scale → segment → measure and export.")
    s.append(Paragraph("Choose a capture route", H2))
    s.append(table(["Device", "Best for", "Metric scale", "Output to PhenoForge", "SOP"], [
        ["iPhone / iPad Pro with LiDAR", "Fast single plants and trays, field work", "Yes (check with markers)", "PLY, OBJ, GLB, USDZ from the scanning app", "SOP-1"],
        ["iPhonotype app (iPhone)", "Guided single-plant scans with traits on the phone", "Camera-based (check with markers)", ".ftscan package → Open scan", "SOP-7"],
        ["Android phone", "Low-cost capture anywhere", "No: ArUco markers", "App export (OBJ/GLB/PLY/splat), or video / photos reconstructed in the app", "SOP-2"],
        ["DSLR / mirrorless", "Highest detail, repeatable lab imaging, publications", "No: ArUco markers", "RAW or JPEG photos reconstructed in the app", "SOP-3"],
        ["Any camera, excavated roots", "Root crowns and washed root systems", "No: ArUco or reference box", "Photos → 3D roots tab", "SOP-4"],
        ["X-ray CT / MRI", "Roots in soil, non-destructive", "Yes (voxel size)", "TIFF stack → Roots 3D tab", "SOP-4"],
        ["iPhone + spike stand (no turntable)", "Quick root scans by one person, no rig to run", "LiDAR: yes, still check with ArUco; video: ArUco", "PLY export or video → Roots 3D tab", "SOP-6"],
        ["Motorised turntable + any camera", "Repeatable lab imaging of root crowns and potted plants", "No: ArUco on the platter", "Session folder → Tools import (Turntable rig)", "SOP-5"],
    ], [0.19, 0.22, 0.17, 0.32, 0.10]))
    s.append(Paragraph("Rules that apply to every device", H2))
    s.append(box("Do", ["Put the ArUco card flat beside every plant, in view from every side.",
                        "Use diffuse, even light; avoid wind (plants must not move during capture).",
                        "Use a plain, matte, non-green background.",
                        "Record plant ID, genotype and treatment in the library (or a QR label in view).",
                        "Capture a colour chart photo at the start of each session for comparable greenness."], cols=1))
    s.append(Spacer(1, 4))
    s.append(box("Avoid", ["Direct sun and hard shadows, glossy pots and reflective surfaces.",
                           "Fast movement, digital zoom, HDR or beauty filters on phones.",
                           "Changing focus or zoom between shots (photogrammetry needs fixed optics).",
                           "Trusting one number without a check: validate against manual measurements (Validation tab)."], bg=RED))
    s.append(Paragraph(SCALE_NOTE, BODY))
    s.append(Spacer(1, 4))
    s.append(Paragraph("Analyse in PhenoForge", H2))
    s.append(steps(ANALYSE_STEPS))
    s += figure("gui_3d.png", caption="3D analysis tab after running the demo tray: six plants separated, convex hulls shown, ArUco scale within 0.1 %.")
    build("SOP-0_Overview_capture_to_traits.pdf", "workflow", s)


def iphone():
    s = [banner("SOP-1  iPhone / iPad Pro with LiDAR", "Metric 3D scans of single plants and trays in a few minutes", "SOP-1"), Spacer(1, 6)]
    s += figure("iphone.jpg")
    s.append(Paragraph("What you need", H2))
    s.append(box("Checklist", ["iPhone 12 Pro or later Pro / Pro Max, or iPad Pro (2020+) with LiDAR",
                               "A LiDAR scanning app that exports PLY or OBJ (e.g. 3d Scanner App, Polycam, Scaniverse, Record3D)",
                               "ArUco card (50 mm markers) and the plant label", "Matte surface, diffuse light",
                               "USB cable, AirDrop to a Mac, or cloud folder to move files to the PC"], cols=2))
    s.append(Paragraph("Capture", H2))
    s.append(steps([
        ("Set up", "Put the pot on a matte surface with the ArUco card flat beside it. Leave 50 cm of free space around the plant to walk."),
        ("Choose the mode", "In the app use the <b>LiDAR / point cloud</b> mode with the highest resolution and confidence; "
                            "for thin wheat leaves prefer <i>high resolution, low max depth (≈1 m)</i>."),
        ("Scan 360°", "Hold the phone 30–50 cm from the plant. Walk one slow circle at pot height, then a second circle from above "
                      "(about 45°). Keep the plant in the centre of the screen; a full circle should take 40–60 s."),
        ("Check coverage", "Look at the preview: no grey holes on the leaves, the markers visible and sharp. Re-scan rather than patch."),
        ("Export", "Export <b>PLY (point cloud)</b> or <b>OBJ / USDZ (mesh)</b> with colour, in metres. "
                   "Name the file with the plant ID and date, e.g. <i>W123_2026-10-19.ply</i>, and copy it to the PC."),
    ]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("In PhenoForge", H2))
    s.append(steps([("Import", "<b>Tools &gt; Import from a capture device</b>, device <i>iPhone / iPad with LiDAR</i>, choose the file, "
                               "<b>Import</b>. Or open it directly in the 3D analysis tab."),
                    ("Keep the LiDAR scale, but verify it", "Scale source <i>Already metric</i>. Click <b>Markers image</b>: each marker should read "
                                                             "within ±2 % of the printed size. If not, switch the scale source to <b>ArUco markers</b>.")]
                   + ANALYSE_STEPS[3:]))
    s.append(Paragraph("Quality checks", H2))
    s.append(table(["Check", "Pass", "If it fails"], [
        ["Marker size after scaling", "within ±2 %", "Use ArUco scaling; check that the card is flat"],
        ["Plant height vs ruler", "within 1 cm", "Fit ground plane on soil, not on leaves (crop the scan)"],
        ["Leaves look solid, not double", "single surface", "Scan slower; avoid wind; re-scan"],
        ["Points on the plant", "> 50 000", "Move closer; use a higher resolution mode"],
    ], [0.35, 0.2, 0.45]))
    s.append(Spacer(1, 4))
    s.append(box("Limits of phone LiDAR", ["The LiDAR depth grid is coarse (≈ 256×192 per frame); apps fuse it with the RGB camera. "
                                           "Thin awns, fine tillers and leaves narrower than ~3 mm are often lost or thickened.",
                                           "Wheat heads and thin leaves are better captured by photogrammetry (SOP-2 or SOP-3) with ArUco scaling."], bg=AMBER))
    build("SOP-1_iPhone_LiDAR.pdf", "iphone", s)


def android():
    s = [banner("SOP-2  Android phone", "Photogrammetry from photos or video, or an app export, scaled with ArUco markers", "SOP-2"), Spacer(1, 6)]
    s += figure("android.jpg")
    s.append(Paragraph("What you need", H2))
    s.append(box("Checklist", ["Any recent Android phone with a good main camera (4K video)",
                               "Option A: a scanning app that exports OBJ / GLB / PLY or Gaussian-splat PLY (e.g. Polycam, Scaniverse, KIRI Engine, RealityScan)",
                               "Option B: just the camera app (photos or video) – PhenoForge reconstructs with COLMAP",
                               "ArUco card (50 mm markers), turntable optional", "USB cable to copy files"], cols=1))
    s.append(Paragraph("Capture", H2))
    s.append(steps([
        ("Lock the camera", "Turn off HDR, beauty and AI scene modes. Use the main (1×) lens only. Tap and hold on the plant to lock focus and exposure (AE/AF lock)."),
        ("Capture three rings", "Photos: 20–40 per ring with ~70 % overlap, at low, middle and top-down heights (60–120 in total). "
                                "Video: 4K 30 fps, one slow circle per ring, ~40 s per circle, no fast turns."),
        ("Keep the markers in view", "The ArUco card must appear in most photos, flat and sharp."),
        ("Export or copy", "Option A: export the app's model as OBJ/GLB/PLY. Option B: copy the photo folder or the video to the PC by USB (DCIM/Camera)."),
    ]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("In PhenoForge", H2))
    s.append(steps([("Import", "<b>Tools &gt; Import from a capture device</b>, device <i>Android phone</i>. Choose the app export, the video "
                               "(<b>File/video…</b>) or the photo folder (<b>Photo folder…</b>). For video the sharpest ~120 frames are picked automatically; "
                               "blurred or over-exposed photos are rejected and listed in the log."),
                    ("Reconstruct", "Photos and video are reconstructed with COLMAP (set its path once in Tools; install from colmap.github.io). "
                                    "Use quality <i>medium</i> first; <i>high</i> needs an NVIDIA GPU and more time."),
                    ("Scale with ArUco", "The model opens in the 3D analysis tab with scale source <b>ArUco markers</b> preselected. Type the measured marker size.")]
                   + ANALYSE_STEPS[3:]))
    s += figure("gui_tools.png", width=W * 0.9, caption="Tools tab: device import with capture tips for the chosen device.")
    s.append(Paragraph("Troubleshooting", H2))
    s.append(table(["Symptom", "Likely cause", "Fix"], [
        ["COLMAP registers few images", "Too little overlap or motion blur", "Move slower; more photos per ring; better light"],
        ["Plant is doubled or smeared", "Plant moved (wind, touching)", "Capture indoors; do not touch the pot"],
        ["No markers detected", "Card curved, too small or out of view", "Flat card, 50 mm markers, in view from all sides"],
        ["Scale differs between markers", "Marker not flat or partly hidden", "Rejected automatically above 4 %; reposition the card"],
    ], [0.3, 0.33, 0.37]))
    build("SOP-2_Android_phone.pdf", "android", s)


def dslr():
    s = [banner("SOP-3  DSLR / mirrorless camera", "High-detail multi-view photogrammetry on a turntable", "SOP-3"), Spacer(1, 6)]
    s += figure("dslr.jpg")
    s.append(Paragraph("What you need", H2))
    s.append(box("Checklist", ["DSLR or mirrorless body, 35–50 mm (full-frame equivalent) prime lens", "Tripod, remote release or interval timer",
                               "Turntable (manual with 10° marks, or motorised)", "Two softboxes / LED panels, plain grey or blue backdrop (not green)",
                               "ArUco card on the turntable", "Colour chart for the first shot of each session"], cols=2))
    s.append(Paragraph("Camera settings", H2))
    s.append(table(["Setting", "Value", "Why"], [
        ["Mode", "Manual (M)", "Identical exposure in every photo"],
        ["Aperture", "f/8 – f/11", "Depth of field covers the whole plant"],
        ["ISO", "100 – 400", "Low noise keeps fine leaf texture"],
        ["Shutter", "≥ 1/60 s on a tripod (use remote)", "No camera shake"],
        ["Focus", "Manual, set once on the plant centre", "Focus changes the lens geometry"],
        ["Stabilisation", "Off on a tripod", "Prevents tiny image shifts"],
        ["Format", "RAW + JPEG", "RAW for colour work; JPEG is enough for 3D"],
        ["White balance", "Fixed (daylight or custom)", "Comparable colour between sessions"],
    ], [0.22, 0.38, 0.40]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("Capture", H2))
    s.append(steps([
        ("Set up", "Plant centred on the turntable, markers flat on the turntable, lights at 45° on both sides, backdrop 1 m behind."),
        ("Shoot ring 1 (low)", "Camera at pot height, plant filling ~60 % of the frame. Rotate 10° between shots: 36 photos."),
        ("Rings 2 and 3", "Raise the tripod to eye level (≈30° down) and to near top-down (≈60° down); 36 photos each."),
        ("Copy to the PC", "Copy the whole card folder (RAW and JPEG) into one folder per plant, named with the plant ID and date."),
    ]))
    s.append(Paragraph("In PhenoForge", H2))
    s.append(steps([("Import", "<b>Tools &gt; Import from a capture device</b>, device <i>DSLR / mirrorless camera</i>, <b>Photo folder…</b>. "
                               "RAW files are developed with the camera white balance (JPEGs with the same name are skipped), "
                               "blurred shots are rejected, and an optional colour correction from the Colour tab is applied."),
                    ("Reconstruct and scale", "COLMAP builds the dense cloud, which opens in the 3D analysis tab. Choose <b>ArUco markers</b> and type the marker size.")]
                   + ANALYSE_STEPS[3:]))
    s.append(Spacer(1, 4))
    s.append(box("Tips", ["A turntable moves the plant, so the background must be plain: a textured background that does not rotate confuses the reconstruction.",
                          "Leaves that move as the turntable starts and stops cause doubling: wait 2 s after each rotation.",
                          "108 photos at 24 MP take about 20–60 min in COLMAP on a desktop GPU."], bg=AMBER))
    build("SOP-3_DSLR_mirrorless.pdf", "dslr", s)


def roots():
    s = [banner("SOP-4  3D root phenotyping", "Root crowns (storage roots), washed root systems and CT volumes", "SOP-4"), Spacer(1, 6)]
    s += figure("roots.jpg")
    s.append(Paragraph(
        "Method after Sunvittayakul et al. (2022) <i>Cassava root crown phenotyping using three-dimension (3D) multi-view stereo reconstruction</i>, "
        "Scientific Reports 12, 10030 (doi:10.1038/s41598-022-14325-4). The paper used Agisoft Metashape and Blender; PhenoForge does the same "
        "steps with open tools and computes the traits automatically.", BODY))
    s.append(Paragraph("Capture a root crown", H2))
    s.append(steps([
        ("Excavate and wash", "Dig out the crown, wash off soil, let it drain. Cut the stem leaving a 5–10 cm stub and weigh the roots (fresh weight)."),
        ("Lay out with scale references", "Lay the crown on its side on a green plastic sheet (the green is removed automatically). Place the ArUco card "
                                          "and, optionally, a box of known size next to it."),
        ("Photograph 360°", "25–40 overlapping photos with a DSLR (SOP-3 settings) or phone (SOP-2), walking around the crown at two heights. "
                            "The paper found 25 images to be the minimum for a complete model."),
        ("Reconstruct", "<b>Tools &gt; Import from a capture device</b> with the photo folder (COLMAP). Scale with ArUco in the 3D analysis tab settings."),
    ]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("Measure in PhenoForge (Roots 3D tab)", H2))
    s.append(steps([
        ("Load", "<b>Use scan from 3D tab</b> after import (or Help &gt; Load demo root crown to practise)."),
        ("Orient", "Stem direction: the axis from the roots to the stem (e.g. <i>-y</i> if the crown lies on its side), or "
                   "<i>two picked points</i>: Ctrl+click the stem top, then the crown bottom."),
        ("Cut the stem", "Type the stub length to remove (the paper removes the stem before measuring)."),
        ("Measure", "Root type <i>Root crown</i>, then <b>Measure roots</b>. The scan is closed and filled with a voxel remesh "
                    "(like Blender's remesh at octree depth 8), and each storage root is separated and coloured."),
    ]))
    s += figure("gui_roots3d.png", width=W * 0.9, caption="Roots 3D tab: demo crown with six storage roots separated.")
    s.append(Paragraph("Traits", H2))
    s.append(table(["Trait", "Definition in PhenoForge", "Paper equivalent"], [
        ["Crown volume", "Filled voxel volume of the crown (optionally summed over sectors: 'split in half' = 2)", "3D crown volume"],
        ["Crown surface", "Marching-cubes surface of the filled crown", "3D crown surface area"],
        ["Surface-to-volume", "Surface ÷ volume", "Same"],
        ["Root density", "Fresh weight ÷ crown volume (enter the weight)", "Root density"],
        ["Root number", "3D components after removing the crown core", "Root number"],
        ["Root angle", "Angle of each root (attachment → tip) from the vertical; mean reported", "Root angle"],
        ["Root length", "Geodesic length from the crown core to the tip, per root", "Root length"],
        ["Crown diameter", "Largest width across the axis", "Crown diameter"],
        ["Cylinder soil volume", "π (diameter/2)² × crown depth", "Cylinder soil volume"],
        ["Compactness", "Crown volume ÷ cylinder soil volume × 100", "CRC compactness"],
    ], [0.2, 0.55, 0.25]))
    s.append(Paragraph("Fibrous roots and CT", H2))
    s.append(box("Washed cereal root systems and X-ray CT", [
        "Washed roots: float the root system in water in a clear tray, or hang it, and photograph it as above; choose root type <i>Fibrous root system</i>.",
        "CT / MRI: <b>Open CT stack…</b> with the TIFF stack and the voxel size; roots are thresholded (Otsu) and the largest connected system is kept.",
        "Traits: total root length, number of tips and branch points, maximum depth and width, convex hull volume, solidity, "
        "root length by depth layer and the depth above which 50 % of the length lies (D50)."]))
    s.append(Spacer(1, 4))
    s.append(box("Accuracy on synthetic test objects", [
        "Root crowns: crown volume within 2–3 %, all roots found, root angles within 4°, root lengths within ~10 %.",
        "Fibrous roots: total length about 9 % high (voxel staircase), tips within 1.",
        "Check against your own manual measurements (Validation tab) before relying on a trait."], bg=AMBER))
    build("SOP-4_3D_roots.pdf", "roots", s)


def turntable():
    s = [banner("SOP-5  Motorised turntable", "Build, print and run the PhenoForge turntable for root crowns and potted plants", "SOP-5"),
         Spacer(1, 6)]
    s += figure("turntable.jpg")
    s.append(Paragraph(
        "The camera stays still and the sample turns in fixed steps. A Raspberry Pi 5 moves the platter and takes a photo at every "
        "stop, so every session is captured the same way. Design files are in <b>hardware/turntable</b>: the OpenSCAD source, STL files, "
        "Bambu Studio plates for the X1 Carbon, and the Pi script.", BODY))
    s.append(Paragraph("1  Print the parts", H2))
    s += figure("tt_parts.png", width=W * 0.6,
                caption="Printed parts: four risers, stem cup, hall-sensor post, pot ring, big pulley (120T), crown hub and motor cradle.")
    s.append(table(["Plate (Bambu Studio file)", "Parts", "Settings (X1 Carbon, 0.4 mm)"], [
        ["plate1_drive_parts.3mf", "big pulley, crown hub, motor cradle, stem cup, sensor post", "PETG, 0.20 mm, 4 walls, 35 % gyroid, no supports, ≈250 g"],
        ["plate2_risers_pot_ring.3mf", "4 risers, pot ring (150 mm pot)", "same, ≈265 g"],
    ], [0.3, 0.38, 0.32]))
    s.append(Spacer(1, 3))
    s.append(Paragraph("Open each 3MF in Bambu Studio, choose the <i>Bambu Lab X1 Carbon 0.4 nozzle</i> printer, PETG and the "
                       "<i>0.20 mm Standard</i> process, set walls to 4 and infill to 35 % gyroid, then slice and print. To change a size "
                       "(bearing, pot or stem diameter), edit the parameters at the top of <b>turntable.scad</b> and export again.", BODY))
    s.append(Paragraph("2  Buy the other parts", H2))
    s.append(box("Shopping list (about AUD 120–160)", [
        "300 mm lazy-susan ball bearing, rated ≥ 100 kg, centre opening ≥ 120 mm",
        "NEMA 17 stepper (40 mm body) and a TMC2209 driver",
        "GT2 20T pulley (5 mm bore) and a GT2 closed belt, 300 mm, 6 mm wide",
        "12 V 3 A power supply and a 100 µF capacitor",
        "Plywood base 500 × 500 × 18 mm; 450 mm platter, painted matte grey",
        "M8 threaded rod 250–300 mm, M4×40 bolts, M3×8 screws, M5 thumb screws",
        "Optional: A3144 hall sensor and a 6 × 3 mm magnet for homing",
        "Raspberry Pi 5 (your camera rig), DSLR on USB or the Arducam USB cameras"], cols=2))
    s.append(Paragraph("3  Assemble", H2))
    s += figure("tt_drive.png", width=W * 0.62, caption="Under the platter (platter and bearing hidden): the printed pulley hangs through the bearing "
                                                         "opening, and the motor cradle slides outward to tension the belt.")
    s.append(steps([
        ("Base and bearing", "Screw the 4 risers to the base on a 270 mm circle. Screw the bearing's lower ring onto the risers."),
        ("Platter and pulley", "Drill the platter centre: one 9 mm hole, and four 4.5 mm holes on a 94 mm circle. Bolt the crown hub on top and the "
                               "big pulley underneath with 4 × M4×40, with the nuts in the pulley recesses. Screw the platter to the bearing's upper ring."),
        ("Motor and belt", "Fix the motor under the cradle plate and fit the 20T pulley and belt. Place the cradle about 73 mm from the centre, slide "
                           "it out until the belt deflects about 3 mm under a light press, then screw down the slotted feet. Slide the 20T pulley "
                           "on its shaft until the belt runs level."),
        ("Wire the Pi", "GPIO18 → STEP, GPIO23 → DIR, GPIO24 → EN, 3V3 and GND to the driver logic, 12 V to the driver motor supply (with the capacitor), "
                        "and optionally the hall sensor to GPIO25. Set the driver current to about 70 % of the motor rating. Wiring details are in "
                        "hardware/turntable/README.md."),
        ("Mount the sample", "Root crown: screw the M8 rod into the hub and clamp the stem stub in the stem cup with the 3 thumb screws. "
                             "Potted plant: remove the rod and screw the pot ring to the platter."),
        ("Markers", "Print 4–8 ArUco markers (Tools &gt; Marker sheet, 40–50 mm) and glue them flat around the platter edge. They turn with the "
                    "sample, which is what the reconstruction needs."),
    ]))
    s.append(Paragraph("4  Capture a session", H2))
    s.append(table(["Setting", "Root crown", "Potted wheat"], [
        ["Stops per ring", "36 (10°)", "36 (10°)"],
        ["Rings (camera heights)", "3: below, level, 45° above", "3: pot height, 30°, 60° above"],
        ["Settle time after each move", "1.5 s (heavy roots swing)", "2–3 s (leaves and heads sway)"],
        ["Speed and acceleration", "15°/s, 15°/s²", "10°/s, 10°/s²"],
        ["Camera", "DSLR f/8–f/11, ISO 100–400, manual focus and white balance", "same; or both Arducams for two heights at once"],
    ], [0.3, 0.35, 0.35]))
    s.append(Spacer(1, 4))
    s.append(steps([
        ("Test the drive", "<font face='Courier'>python3 pi/turntable_capture.py --jog 90</font>: the platter should turn a quarter turn smoothly. "
                           "Use <i>--reverse</i> to change direction."),
        ("Set up the camera", "Tripod 60–100 cm away, sample filling about 60 % of the frame, plain backdrop and two lights at 45°. "
                              "Lock focus, exposure and white balance. Nothing else in view may move."),
        ("Run", "<font face='Courier'>python3 pi/turntable_capture.py --out ~/scans/C07 --camera gphoto2 --shots 36 --rings low mid top "
                "--settle 1.5 --speed 15 --accel 15</font>. After each ring the script asks you to move the camera to the next height."),
        ("Phone or other cameras", "Use <i>--camera opencv --cam 0 2</i> for the two Arducam USB cameras. Use <i>--camera none --settle 3</i> with a phone "
                                   "on an interval timer, then copy the photos into the session folder."),
        ("Copy to the PC", "The session folder holds ring_index_angle.jpg photos and a turntable.json file. Copy the whole folder."),
    ]))
    s.append(Paragraph("5  Reconstruct and measure in PhenoForge", H2))
    s.append(steps([
        ("Import", "<b>Tools &gt; Import from a capture device</b>, device <i>Turntable rig (session folder)</i>, <b>Photo folder…</b>. "
                   "Blurred photos are rejected. Masks are then made from the room, which is identical in every photo, so COLMAP only uses "
                   "the turning sample and the platter."),
        ("Scale", "In the 3D analysis tab choose <b>ArUco markers</b> and type the measured marker size."),
        ("Measure", "Root crowns: <b>Roots 3D</b> tab (SOP-4), stem direction <i>+z</i> or <i>-z</i>. Potted plants: <b>3D analysis</b>, plant mode <i>single</i>."),
    ]))
    s.append(Spacer(1, 4))
    s.append(KeepTogether(box("Troubleshooting", [
        "Doubled leaves or roots: increase <i>--settle</i>, and lower <i>--speed</i> and <i>--accel</i>.",
        "COLMAP reconstructs the room or the backdrop: something static was mistaken for the sample. Check that nothing else moved, that the "
        "markers are on the platter (not the table), and that the backdrop is plain.",
        "The platter stalls or skips: raise the driver current a little, check the belt tension, and centre heavy samples.",
        "The motor hums but does not turn: the EN pin is not low or the coil pairs are swapped (swap A2 and B1).",
        "Wrong angle per stop: <i>--microsteps</i> does not match the driver's MS pins."], bg=AMBER)))
    build("SOP-5_Turntable_rig.pdf", "turntable", s)


def spike():
    s = [banner("SOP-6  iPhone root scanning on a spike stand", "Fast 3D root scans by one person: the roots stay still and you walk around them", "SOP-6"),
         Spacer(1, 6)]
    s += figure("spike.jpg")
    s.append(Paragraph(
        "This is the quickest way to get 3D roots: no motor, no Raspberry Pi and no photo session. The washed root crown is pushed onto a "
        "vertical spike, stem up, so the roots hang freely, and the operator walks around it with an iPhone. Allow about <b>2 minutes per plant</b> to capture, then "
        "process in PhenoForge. Use it when time is short. Use the turntable (SOP-5) when you need the most detail and repeatability.", BODY))
    s.append(Paragraph("1  Build the spike stand (once)", H2))
    t = Table([[figure("spike_stand.png", width=W * 0.42)[0],
                [Paragraph("<b>Parts</b>", BODY),
                 Paragraph("• Heavy base: 400 × 400 mm plywood (18 mm) or a paving stone, painted <b>matte green</b>", BODY),
                 Paragraph("• Printed <b>crown hub</b> and <b>stem cup</b> from the turntable print files (plate 1); the cup is an optional support collar", BODY),
                 Paragraph("• M8 threaded rod 300 mm, with one end ground to a sharp point; 3 M8 nuts; 4 wood screws for the hub", BODY),
                 Paragraph("• Green electrical tape for the rod (green parts are removed automatically)", BODY),
                 Paragraph("• 4 ArUco markers, 50 mm (Tools &gt; Marker sheet), glued flat on rigid card", BODY),
                 Spacer(1, 4),
                 Paragraph("<b>Assemble</b>", BODY),
                 Paragraph("Screw the hub to the centre of the base. Screw the blunt end of the rod into the hub and lock it with two nuts. "
                           "Wrap the rod in green tape, leaving the top 3 cm of the point bare. For heavy crowns, thread the stem cup onto the rod "
                           "just below the point (third nut) so the crown rests on it. Glue the 4 markers flat on the base, about 14 cm from the rod "
                           "at 90° to each other. Measure one marker with a ruler and write the size on the base.", BODY)]]],
              colWidths=[W * 0.45, W * 0.55])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    s.append(t)
    s.append(Paragraph("2  Prepare the roots", H2))
    s.append(steps([
        ("Excavate and wash", "Dig out the root system, wash off all soil, and let it drip dry for 5–10 minutes. Wet, shiny roots reflect light and scan poorly."),
        ("Cut the stem", "Leave a 5–10 cm stem stub. Weigh the roots now if you want root density (fresh weight)."),
        ("Mount it on the spike", "Hold the crown stem up and push it straight down onto the point, through the centre of the crown base, until it "
                                  "sits firmly (on the stem cup if you use it). The roots hang freely around the rod, and no root should touch the base."),
        ("Fibrous roots (wheat)", "Push the spike into the crown at the base of the shoot, or clamp the shoot base in the stem cup's thumb screws, with "
                                  "the roots hanging down. Spread them gently with a soft brush so they do not clump. For very fine roots, use the video route below."),
    ]))
    s.append(Paragraph("3  Scan with the iPhone", H2))
    s.append(table(["", "Route A: LiDAR scan", "Route B: video (photogrammetry)"], [
        ["Use for", "Thick roots: cassava storage roots, tubers, taproots", "Fine and fibrous roots (wheat) and anything thinner than ~3 mm"],
        ["Phone", "iPhone 12 Pro or later Pro / Pro Max, or iPad Pro", "Any iPhone (or Android phone)"],
        ["App", "Scaniverse, Polycam (LiDAR mode) or 3d Scanner App", "The camera app: 4K, 30 fps, HDR off"],
        ["Live view", "Yes: you see the 3D model build while scanning", "No: the model is built on the PC"],
        ["Scale", "Metric already, but check it with ArUco", "ArUco markers (required)"],
        ["Time on the PC", "Seconds", "10–30 min (COLMAP)"],
    ], [0.16, 0.42, 0.42]))
    s.append(Spacer(1, 4))
    s.append(steps([
        ("Set up", "Plain backdrop behind the stand, two soft lights, and no fan or draught. Lock the phone's focus and exposure (tap and hold on the roots)."),
        ("Circle 1: root level", "Hold the phone 30–50 cm from the roots at their height. Walk one slow full circle in about 40 s, keeping the roots in the centre of the screen."),
        ("Circle 2: from above", "Raise the phone to about 45° above and walk a second circle. For long roots, add a third circle low down, looking up."),
        ("Check", "LiDAR: look for grey holes in the live model and rescan rather than patch. Video: play it back and check that the roots are sharp, not blurred."),
        ("Export and copy", "LiDAR: export <b>PLY</b> (points) or OBJ with colour. Video: copy the .mov or .mp4 file. Name it with the plant ID and date, "
                            "e.g. <i>C07_2026-10-19.ply</i>, and copy it to the PC (AirDrop, USB or a cloud folder)."),
    ]))
    s.append(Paragraph("4  Measure in PhenoForge", H2))
    s.append(steps([
        ("Import", "<b>Tools &gt; Import from a capture device</b>. Choose <i>iPhone / iPad with LiDAR</i> for a PLY or OBJ, or "
                   "<i>Android phone</i> and <b>File/video…</b> for a video. For a video, the sharpest ~120 frames are picked and reconstructed with COLMAP."),
        ("Scale", "In the 3D analysis tab choose <b>ArUco markers</b> and type the measured marker size. For a LiDAR scan, click "
                  "<b>Markers image</b> to check that each marker reads within ±2 % of its true size."),
        ("Roots 3D", "Click <b>Use scan from 3D tab</b>. Set the stem direction to <b>+z</b> (stem up) and the stem length to remove (the stub, "
                     "5–10 cm). Keep <i>Remove green background sheet</i> and <i>Remove background plane</i> ticked: they delete the green rod, "
                     "base and markers. Choose <i>Root crown</i> for storage roots or <i>Fibrous root system</i> for wheat, then click <b>Measure roots</b>."),
        ("Save", "<b>Save results</b> writes the trait table (CSV and JSON): crown volume, root number, length, diameter and angle per root, "
                 "or total length, tips and depth for fibrous roots."),
    ]))
    s.append(Spacer(1, 4))
    s.append(KeepTogether(box("Good to know", [
        "Only the 3D model is live on the phone. The traits are calculated on the PC afterwards.",
        "LiDAR thickens or misses roots thinner than about 3 mm. Use the video route for wheat roots.",
        "If a thin vertical 'root' appears under the crown, the rod was not fully green: re-tape it, or paint the stem cup green too.",
        "Validate first: measure 3–5 plants by hand (root length, diameter, fresh weight) and compare them in the <b>Validation</b> tab "
        "before trusting the numbers for a whole experiment."], bg=AMBER)))
    build("SOP-6_iPhone_roots_spike.pdf", "spike", s)


def iphonotype():
    s = [banner("SOP-7  iPhonotype app (iPhone)", "Guided orbit capture on the phone, analysed in PhenoForge from the .ftscan package", "SOP-7"),
         Spacer(1, 6)]
    s += figure("iphone.jpg")
    s.append(Paragraph(
        "iPhonotype guides you around the plant and takes 90–140 photos. On the phone it then builds a textured mesh (Apple photogrammetry, "
        "USDZ), a 3D Gaussian-splat cloud (PLY, in metres) and preliminary traits, and exports everything as one <b>.ftscan</b> package "
        "(a zip file). PhenoForge opens the package directly and measures the splat cloud. A test scan took 2.6 min to capture and about "
        "4 min to process on the phone. LiDAR is not needed: the app uses the rear camera and the motion sensors.", BODY))
    s.append(Paragraph("What you need", H2))
    s.append(box("Checklist", ["iPhone with the iPhonotype app (tested with app version 2.3.1, iOS 26)",
                               "ArUco card (DICT_4X4_50, 50 mm) beside the pot; the app also recommends markers for scale checks",
                               "Plain, matte, non-green background and diffuse light (the test scan had about 600 lux)",
                               "About 50 cm of free space all round the plant, and no wind",
                               "A way to copy files to the PC (AirDrop to a Mac, OneDrive or USB): a package is about 250–300 MB"], cols=1))
    s.append(Paragraph("Capture", H2))
    s.append(steps([
        ("Set up", "Put the pot on a matte surface with the ArUco card flat beside it, in view from every side. Put the plant label where the camera sees it."),
        ("Start a scan and label it", "Start a new <b>Spatial Orbit</b> scan. Fill in the plant ID, genotype, treatment and operator: they are stored in the "
                                      "package (manifest.json) and are otherwise empty."),
        ("Orbit", "Follow the app's guide: one slow, close orbit, then a <b>higher pass</b> and a <b>lower pass</b>. Keep the whole plant and the "
                  "card in the frame. Aim for about 140 photos; 90 is the app's minimum."),
        ("Let it process", "Wait until the mesh and the splat are finished on the phone before you export. Keep the phone plugged in and out of the sun "
                           "so it does not slow down from heat."),
        ("Export", "Export the <b>.ftscan</b> package. Either copy it to the PC (AirDrop, OneDrive or USB), or send it over Wi-Fi: "
                   "in PhenoForge choose <b>File &gt; Receive from phone (Wi-Fi)</b>, press <b>Start</b>, scan the QR code with the "
                   "iPhone camera and pick the package on the web page that opens. You do not need to unzip it."),
    ]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("In PhenoForge", H2))
    s.append(steps([
        ("Open the package", "On the <b>Start</b> tab click <b>Analyse an iPhonotype scan</b> and choose the .ftscan.zip (or drop it on "
                             "the window). PhenoForge stands the splat cloud upright, takes the metric scale, plant ID, genotype, treatment "
                             "and light readings from the package, and runs the analysis straight away. The <b>vs iPhonotype</b> tab "
                             "compares its traits with the app's; the <b>Package</b> tab lists what the app recorded."),
        ("Clean and frame", "Leave <i>Input is Y-up</i> <b>unticked</b>: the package is already turned upright on loading, and ticking it lays the "
                            "plant on its side. If you open the USDZ mesh on its own, also leave it unticked. Keep <i>Remove outliers</i>, "
                            "<i>Fit ground plane</i> and <i>Remove ground points</i> ticked, and use vegetation index <i>exg</i> to remove the pot and soil."),
        ("Check the scale", "The package scale is used automatically (<i>Already metric</i>). With a card in view, switch to "
                            "<b>ArUco markers</b>, type the measured marker size and press <b>Run analysis</b> again; <b>Markers image</b> "
                            "shows each marker's size. Without a card, <i>Two picked points</i> across a known distance such as the pot rim also works."),
        ("Check the model", "<b>Check vs photos</b> draws the 3D scan over each of the app's photos and reports the overlap (IoU). "
                            "Most frames above about 0.6 means the model matches what the camera saw."),
        ("Save", "<b>Save results</b> writes JSON and CSV files, including the comparison with the app and the package details. "
                 "For many scans use <b>File &gt; Analyse a whole folder</b>: one row per scan in all_scans.csv."),
    ]))
    s.append(Paragraph("What is in the package", H2))
    s.append(table(["File", "What it is", "Use in PhenoForge"], [
        ["splats/iphone_splat_reconstruction.ply", "Gaussian-splat cloud in metres, scaled from the camera path (confidence in 3dgs/workflow.json)",
         "Default. Its height matched the app's plant height within 1.5 cm in the test scan"],
        ["mesh/photogrammetry_mesh.usdz", "Textured mesh in Apple reconstruction units; includes the pot", "Optional. Height includes the pot unless it is filtered out"],
        ["analysis/on_device_*.json", "The app's preliminary traits and top-view plant masks", "For comparison only; the package says desktop results replace them"],
        ["rgb/, 3dgs/images, 3dgs/transforms.json", "Photos and camera poses", "Re-run in COLMAP or Nerfstudio if needed"],
    ], [0.38, 0.34, 0.28]))
    s.append(Paragraph("Quality checks", H2))
    s.append(table(["Check", "Pass", "If it fails"], [
        ["Photos in the package (logs/native_object_capture.json, image_count)", "≥ 90, ideally 140", "Rescan with a slower orbit"],
        ["Coverage (manifest.json, quality.coverage_estimate)", "≥ 0.8 (suggested)", "Add the higher and lower passes; avoid gaps behind leaves"],
        ["Plant stands upright after the ground fit", "upright", "Untick Y-up. If the splat .ply was opened on its own (not the package), "
                                                                  "tick Y-up. Crop away a tilted table or the background"],
        ["Marker size after scaling", "within ±2 %", "Use ArUco scaling; check that the card is flat"],
        ["Plant height vs ruler", "within 1 cm", "Check the scale; fit the ground plane on soil, not on leaves"],
    ], [0.42, 0.2, 0.38]))
    s.append(Spacer(1, 4))
    s.append(KeepTogether(box("Good to know", [
        "The app's on-device traits are a preliminary estimate. Use the PhenoForge results, and validate them against manual measurements "
        "(Validation tab) before relying on them.",
        "The app may warn that metric scale is not verified: that refers to the mesh. The splat cloud carries the camera-based scale. Still put a "
        "card in view, because it is the only independent check.",
        "Projected area and leaf area differ between the splat and the mesh because sparse leaf edges are treated differently. Compare a trait "
        "only between scans analysed the same way.",
        "The app reads any text in view as a possible tray label (in the test scan it read safety signs). Type the plant ID rather than relying on it.",
        "Leaves and awns thinner than about 3 mm can be thickened or lost."], bg=AMBER)))
    build("SOP-7_iPhonotype_app.pdf", "iphone", s)


if __name__ == "__main__":
    overview()
    iphone()
    android()
    dslr()
    roots()
    turntable()
    spike()
    iphonotype()
