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
        ["Android phone", "Low-cost capture anywhere", "No: ArUco markers", "App export (OBJ/GLB/PLY/splat), or video / photos reconstructed in the app", "SOP-2"],
        ["DSLR / mirrorless", "Highest detail, repeatable lab imaging, publications", "No: ArUco markers", "RAW or JPEG photos reconstructed in the app", "SOP-3"],
        ["Any camera, excavated roots", "Root crowns and washed root systems", "No: ArUco or reference box", "Photos → 3D roots tab", "SOP-4"],
        ["X-ray CT / MRI", "Roots in soil, non-destructive", "Yes (voxel size)", "TIFF stack → Roots 3D tab", "SOP-4"],
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


if __name__ == "__main__":
    overview()
    iphone()
    android()
    dslr()
    roots()
