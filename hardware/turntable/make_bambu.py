"""Lay the turntable STLs out on 256 x 256 mm plates (Bambu Lab X1 Carbon / P1 / X1E)
and write 3MF projects that Bambu Studio opens with every part named and placed.

    python make_bambu.py      (after exporting the STLs from turntable.scad)
"""

import zipfile
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).parent
BED = 256.0
PLATES = {
    "plate1_drive_parts": [("big_pulley", (65, 65)), ("crown_hub", (190, 65)), ("motor_cradle", (95, 185)),
                           ("stem_cup", (210, 190)), ("home_sensor_post", (125, 237))],
    "plate2_risers_pot_ring": [("pot_ring", (100, 128)), ("riser", (220, 38)), ("riser", (220, 98)),
                               ("riser", (220, 158)), ("riser", (220, 218))],
}

CT = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="config" ContentType="text/xml"/>
</Types>"""
RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""


def load(name):
    m = trimesh.load(HERE / "stl" / f"{name}.stl")
    lo, hi = m.bounds
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    return m


def write_plate(fname, items):
    objs, build, cfg, boxes = [], [], [], []
    for i, (name, (x, y)) in enumerate(items, start=1):
        m = load(name)
        lo, hi = m.bounds
        boxes.append((name, lo[:2] + (x, y), hi[:2] + (x, y)))
        v = "".join(f'<vertex x="{a:.4f}" y="{b:.4f}" z="{c:.4f}"/>' for a, b, c in m.vertices)
        t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
        label = f"{name}_{i}"
        objs.append(f'<object id="{i}" name="{label}" type="model"><mesh><vertices>{v}</vertices>'
                    f'<triangles>{t}</triangles></mesh></object>')
        build.append(f'<item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 {x} {y} 0" printable="1"/>')
        cfg.append(f'<object id="{i}"><metadata key="name" value="{label}"/><metadata key="extruder" value="1"/></object>')
    for k, (na, alo, ahi) in enumerate(boxes):
        assert (alo >= 0).all() and (ahi <= BED).all(), f"{na} off the bed"
        for nb, blo, bhi in boxes[k + 1:]:
            assert not ((alo < bhi).all() and (blo < ahi).all()), f"{na} overlaps {nb}"
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             '<metadata name="Application">PhenoForge turntable</metadata>'
             f'<resources>{"".join(objs)}</resources><build>{"".join(build)}</build></model>')
    config = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>' + "".join(cfg) + "</config>")
    with zipfile.ZipFile(HERE / "bambu" / f"{fname}.3mf", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/model_settings.config", config)
    print("wrote", HERE / "bambu" / f"{fname}.3mf")


if __name__ == "__main__":
    (HERE / "bambu").mkdir(exist_ok=True)
    for f, items in PLATES.items():
        write_plate(f, items)
