"""
Vasarely Múzeum Budapest – Kiállítótér 6 (E-102), emelet
3D room model + artwork hanging tools for Blender (4.2+ / 5.x)

Sources
  * EMELETI ALAPRAJZ 1:100 (Szépművészeti Múzeum Vasarely Múzeuma) – room E-102,
    12.025 x 15.00 m, 178.95 m2, pillars 80x80 cm
  * "falnezetek meretekkel – szerigrafia terem" – wall elevations with cm dimensions
  * Canva "MŰTÁRGYKIOSZTÁS" – new wall layout (1 x 4 m + 2 x 2 m mobile walls,
    1 x 2.5 m + 2 x 2 m new drywalls)

Coordinates (metres)
  X = west -> east   (X = 0 is the inner face of the west wall)
  Y = south -> north (Y = 0 is the inner face of the south wall, towards room 5)
  Z = up             (Z = 0 is the floor)

Wall offsets are always measured the way the elevation drawings are drawn:
standing in the room, facing the wall, from its LEFT end, in cm.

How to use
  1. Blender > Scripting workspace > Open this file > Run Script.
     (Or just open the ready-made .blend – the script is embedded.)
  2. 3D Viewport > press N > "Kiállítás" tab.
  3. Select an artwork: choose wall, offset from left (cm), centre height (cm).
  4. "Import artworks CSV" to load the checklist, "Export hanging list" to get
     positions back as a CSV for the installers.
  5. Walk through: select camera "Eye 160cm – stair entrance", Numpad 0,
     then View > Navigation > Walk Navigation (Shift+`), WASD + mouse.
"""

import bpy
import bmesh
import csv
import math
import os
from mathutils import Vector

# --------------------------------------------------------------------------
# Measured data
# --------------------------------------------------------------------------
ROOM_W = 12.025          # E-W inner width (plan 12,02^5)
ROOM_L = 15.00           # N-S inner length (plan 15,00)
CEILING = 3.29           # floor -> suspended ceiling (belmagasság 329 cm)
WALL_T = 0.60            # drawn thickness of the old masonry walls (visual only)

BENCH_H = 0.37           # radiator enclosure height (radiátor 37 cm)
BENCH_D = 0.69           # radiator enclosure depth (69 cm corner blocks)

PILLAR = 0.80
PILLAR_X0 = 5.77                         # 5,77 from west wall
PILLAR_A_Y0 = ROOM_L - 4.095 - PILLAR    # north pillar (4,09^5 from north wall)
PILLAR_B_Y0 = PILLAR_A_Y0 - 4.37 - PILLAR  # south pillar (4,37 gap)
PX = PILLAR_X0 + PILLAR / 2              # pillar centre line X

MOBILE_T = 0.295          # mobile wall thickness (29.5 cm end view)
MOBILE_FEET = 0.18        # raised on feet 18 cm
MOBILE_H = 2.72           # panel height 272 cm
DRYWALL_T = 0.125         # new gypsum board wall (assumed)
DRYWALL_H = 3.00          # assumed – change if the build height differs
GAP = 0.23                # gap between pillar and mobile wall (elevation ~23 cm)

DEFAULT_CENTRE_CM = 150.0  # default hanging centre line

# Openings per main wall, in wall coordinates (u from LEFT end as seen facing
# the wall, z from floor), metres.  kind: door / window
OPENINGS = {
    # Északi fal – facing north, left end = west.  791 | door 187 | 224
    "N": [("door", 7.91, 9.78, 0.0, 2.675)],
    # Déli fal (6/7) – facing south, left end = east. 178 | 26+198+26 | 765
    #   (door height not on the drawing – assumed same as north door)
    "S": [("door", 1.78, 4.28, 0.0, 2.675)],
    # Keleti fal – facing east, left end = north.
    #   118 | 130 | 392 | 130 | 441 | 129 | 202  (sum 1542 > 1500!)
    #   window 3 is placed from the south corner (202 cm) – please verify 441.
    "E": [("window", 1.18, 2.48, BENCH_H, BENCH_H + 2.54),
          ("window", 6.40, 7.70, BENCH_H, BENCH_H + 2.54),
          ("window", ROOM_L - 2.02 - 1.29, ROOM_L - 2.02, BENCH_H, BENCH_H + 2.54)],
    # Nyugati fal – facing west, left end = south.
    #   210 | 126 | 390 | 128 | 395 | 111 | 135
    "W": [("window", 2.10, 3.36, BENCH_H, BENCH_H + 2.52),
          ("window", 7.26, 8.54, BENCH_H, BENCH_H + 2.52),
          ("window", 12.49, 13.60, BENCH_H, BENCH_H + 2.52)],
}
WINDOW_SILL = 1.33        # glass starts at pm 133 (radiator niche below)

# Colours (approximations of the Pantone ideas in the Canva board)
COL = {
    "wall":      (0.93, 0.90, 0.84),   # törtfehér / csontszín main walls
    "mobile":    (0.95, 0.93, 0.88),   # neutral mobile walls
    "drywall":   (0.91, 0.74, 0.72),   # ~PANTONE 7605 C powder pink
    "pillar":    (0.90, 0.88, 0.83),
    "floor":     (0.60, 0.36, 0.27),   # terracotta tiles (kerámia)
    "ceiling":   (0.97, 0.97, 0.96),
    "bench":     (0.92, 0.91, 0.88),
    "glass":     (0.62, 0.72, 0.80),
    "door":      (0.33, 0.24, 0.18),
    "reveal":    (0.88, 0.86, 0.80),
    "frame":     (0.08, 0.08, 0.08),
    "art":       (0.45, 0.47, 0.55),
    "person":    (0.25, 0.35, 0.55),
    "label":     (0.15, 0.15, 0.15),
}

ROOT = "Kiallitoter_6"

# --------------------------------------------------------------------------
# Hanging surfaces
# --------------------------------------------------------------------------
# Each surface: id -> dict(name, origin (x,y) = LEFT end on the face,
#   right (unit vector), normal (into the room / towards viewer), length,
#   z0, z1 usable height, wall key for openings)


def _surface(sid, name, origin, right, normal, length, z0, z1, openings_key=None):
    return dict(id=sid, name=name, origin=Vector((origin[0], origin[1], 0.0)),
                right=Vector((right[0], right[1], 0.0)),
                normal=Vector((normal[0], normal[1], 0.0)),
                length=length, z0=z0, z1=z1, openings=openings_key)


def _partition(sid, label, p0, p1, thick, z0, z1):
    """Two hangable faces for a free-standing wall with centre line p0->p1."""
    p0 = Vector((p0[0], p0[1], 0.0))
    p1 = Vector((p1[0], p1[1], 0.0))
    d = (p1 - p0).normalized()
    length = (p1 - p0).length
    out = []
    for n in (Vector((-d.y, d.x, 0.0)), Vector((d.y, -d.x, 0.0))):
        right = Vector((-n.y, n.x, 0.0))
        left_end = p0 if (p0 - p1).dot(right) < 0 else p1
        origin = left_end + n * (thick / 2)
        side = _dir_name(n)
        out.append(_surface(f"{sid}_{side[0]}", f"{label} – {side[1]}",
                            (origin.x, origin.y), (right.x, right.y),
                            (n.x, n.y), length, z0, z1))
    return out


def _dir_name(n):
    if abs(n.x) > abs(n.y):
        return ("E", "keleti oldal") if n.x > 0 else ("W", "nyugati oldal")
    return ("N", "északi oldal") if n.y > 0 else ("S", "déli oldal")


def build_surfaces():
    s = [
        _surface("N", "Északi fal (lépcső felé)", (0, ROOM_L), (1, 0), (0, -1), ROOM_W, 0, CEILING, "N"),
        _surface("S", "Déli fal 6/7 (5-ös terem felé)", (ROOM_W, 0), (-1, 0), (0, 1), ROOM_W, 0, CEILING, "S"),
        _surface("E", "Keleti fal (ablakok)", (ROOM_W, ROOM_L), (0, -1), (-1, 0), ROOM_L, BENCH_H, CEILING, "E"),
        _surface("W", "Nyugati fal (ablakok)", (0, 0), (0, 1), (1, 0), ROOM_L, BENCH_H, CEILING, "W"),
    ]
    for pid, label, p0, p1, t, z0, z1 in PARTITIONS:
        s += _partition(pid, label, p0, p1, t, z0, z1)
    return {x["id"]: x for x in s}


# Free-standing walls – layout from the Canva board (new plan)
PA_C = PILLAR_A_Y0 + PILLAR / 2   # north pillar centre Y
PB_C = PILLAR_B_Y0 + PILLAR / 2   # south pillar centre Y
PARTITIONS = [
    # id, label, p0, p1, thickness, z0, z1
    ("MOB4", "Nagy mobilfal 4 m",
     (PX, PILLAR_A_Y0 + PILLAR + 0.03), (PX, PILLAR_A_Y0 + PILLAR + 0.03 + 4.00),
     MOBILE_T, MOBILE_FEET, MOBILE_FEET + MOBILE_H),
    ("MOB2N", "Kis mobilfal 2 m (északi oszlop)",
     (PILLAR_X0 - GAP - 2.0, PA_C), (PILLAR_X0 - GAP, PA_C),
     MOBILE_T, MOBILE_FEET, MOBILE_FEET + MOBILE_H),
    ("MOB2S", "Kis mobilfal 2 m (déli oszlop)",
     (PILLAR_X0 - GAP - 2.0, PB_C), (PILLAR_X0 - GAP, PB_C),
     MOBILE_T, MOBILE_FEET, MOBILE_FEET + MOBILE_H),
    ("GK25", "Gipszkarton fal 2,5 m (oszlopok között)",
     (PX, PILLAR_A_Y0 - 2.50), (PX, PILLAR_A_Y0),
     DRYWALL_T, 0.0, DRYWALL_H),
    ("GK2S", "Gipszkarton fal 2 m (bejárat felé)",
     (PX, PILLAR_B_Y0 - 2.00), (PX, PILLAR_B_Y0),
     DRYWALL_T, 0.0, DRYWALL_H),
    ("GK2E", "Gipszkarton fal 2 m (kelet felé)",
     (PILLAR_X0 + PILLAR, PB_C), (PILLAR_X0 + PILLAR + 2.00, PB_C),
     DRYWALL_T, 0.0, DRYWALL_H),
]

SURFACES = build_surfaces()
STAGING = "NONE"

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def get_collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def _lin(c):
    """sRGB (0-1, as you would pick in a colour picker) -> linear for Blender."""
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def material(key, color=None, rough=0.8):
    name = f"M_{key}"
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        c = _lin(color or COL[key])
        bsdf.inputs["Base Color"].default_value = (*c, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        m.diffuse_color = (*c, 1.0)
    return m


def box(name, center, size, rot_z, mat, col):
    """Axis-aligned (in local frame) box. size = (local x, local y, z)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = center
    ob.rotation_euler = (0, 0, rot_z)
    me.materials.append(mat)
    col.objects.link(ob)
    return ob


def surf_point(s, u, z, off=0.0):
    p = s["origin"] + s["right"] * u + s["normal"] * off
    return Vector((p.x, p.y, z))


def surf_rot(s):
    return math.atan2(s["right"].y, s["right"].x)


def surf_box(name, s, u0, u1, z0, z1, off0, off1, mat, col):
    """Box on a surface frame: u range, z range, offset range along normal."""
    if u1 - u0 < 1e-4 or z1 - z0 < 1e-4:
        return None
    c = surf_point(s, (u0 + u1) / 2, (z0 + z1) / 2, (off0 + off1) / 2)
    return box(name, c, (u1 - u0, abs(off1 - off0), z1 - z0), surf_rot(s), mat, col)


def floor_text(text, x, y, rot_z, size, col, z=0.01):
    cu = bpy.data.curves.new(f"T_{text}", type="FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    ob = bpy.data.objects.new(f"Label – {text}", cu)
    ob.location = (x, y, z)
    ob.rotation_euler = (0, 0, rot_z)
    ob.data.materials.append(material("label"))
    col.objects.link(ob)
    ob.hide_select = True
    return ob


# --------------------------------------------------------------------------
# Room build
# --------------------------------------------------------------------------


def build_main_wall(key, s, col):
    mw, mrev, mglass, mdoor = (material("wall"), material("reveal"),
                               material("glass", rough=0.1), material("door"))
    ops = sorted(OPENINGS.get(key, []), key=lambda o: o[1])
    L = s["length"]
    # extend main walls through the corners
    ext = WALL_T
    u = -ext
    for i, (kind, u0, u1, z0, z1) in enumerate(ops):
        surf_box(f"Fal {key} {i}a", s, u, u0, 0, CEILING, -WALL_T, 0, mw, col)
        surf_box(f"Fal {key} {i} felett", s, u0, u1, z1, CEILING, -WALL_T, 0, mw, col)
        if kind == "window":
            # radiator niche + deep window reveal, glass set back
            surf_box(f"Ablak {key} {i} parapet", s, u0, u1, 0, WINDOW_SILL, -WALL_T, -0.30, mw, col)
            surf_box(f"Ablak {key} {i} üveg", s, u0, u1, WINDOW_SILL, z1, -WALL_T + 0.05, -WALL_T + 0.07, mglass, col)
            for side, (a, b) in (("bal", (u0 - 0.02, u0)), ("jobb", (u1, u1 + 0.02))):
                surf_box(f"Ablak {key} {i} káva {side}", s, a, b, z0, z1, -WALL_T, 0, mrev, col)
        else:
            surf_box(f"Ajtó {key} {i} szárny", s, u0 + 0.10, u1 - 0.10, 0, z1 - 0.08, -0.35, -0.30, mdoor, col)
            surf_box(f"Ajtó {key} {i} tok bal", s, u0, u0 + 0.10, 0, z1, -0.35, 0.02, mrev, col)
            surf_box(f"Ajtó {key} {i} tok jobb", s, u1 - 0.10, u1, 0, z1, -0.35, 0.02, mrev, col)
            surf_box(f"Ajtó {key} {i} tok felső", s, u0, u1, z1 - 0.08, z1, -0.35, 0.02, mrev, col)
        u = u1
    surf_box(f"Fal {key} vég", s, u, L + ext, 0, CEILING, -WALL_T, 0, mw, col)


def build_room():
    scene = bpy.context.scene
    root = get_collection(ROOT)
    c_arch = get_collection("Épület (falak, ablakok)", root)
    c_walls = get_collection("Mobil- és gipszkarton falak", root)
    c_ceil = get_collection("Álmennyezet (rejtsd el felülnézethez)", root)
    c_lab = get_collection("Feliratok (alaprajz)", root)
    c_misc = get_collection("Kamerák, fények, lépték", root)
    get_collection("Műtárgyak", root)

    # floor & ceiling
    box("Padló (kerámia)", (ROOM_W / 2, ROOM_L / 2, -0.05),
        (ROOM_W + 2 * WALL_T, ROOM_L + 2 * WALL_T, 0.1), 0, material("floor", rough=0.5), c_arch)
    box("Álmennyezet 329 cm", (ROOM_W / 2, ROOM_L / 2, CEILING + 0.025),
        (ROOM_W, ROOM_L, 0.05), 0, material("ceiling"), c_ceil)

    for key in ("N", "S", "E", "W"):
        build_main_wall(key, SURFACES[key], c_arch)

    # radiator benches along east & west walls
    mb = material("bench")
    box("Radiátorburkolat nyugat", (BENCH_D / 2, ROOM_L / 2, BENCH_H / 2),
        (BENCH_D, ROOM_L, BENCH_H), 0, mb, c_arch)
    box("Radiátorburkolat kelet", (ROOM_W - BENCH_D / 2, ROOM_L / 2, BENCH_H / 2),
        (BENCH_D, ROOM_L, BENCH_H), 0, mb, c_arch)

    # pillars
    mp = material("pillar")
    for nm, y0 in (("Oszlop északi", PILLAR_A_Y0), ("Oszlop déli", PILLAR_B_Y0)):
        box(nm, (PX, y0 + PILLAR / 2, CEILING / 2), (PILLAR, PILLAR, CEILING), 0, mp, c_arch)

    # partitions
    for pid, label, p0, p1, t, z0, z1 in PARTITIONS:
        p0v, p1v = Vector((*p0, 0)), Vector((*p1, 0))
        mid = (p0v + p1v) / 2
        d = p1v - p0v
        rot = math.atan2(d.y, d.x)
        is_mobile = pid.startswith("MOB")
        m = material("mobile") if is_mobile else material("drywall")
        ob = box(label, (mid.x, mid.y, (z0 + z1) / 2), (d.length, t, z1 - z0), rot, m, c_walls)
        ob["wall_id"] = pid
        if is_mobile:
            mf = material("frame")
            for f in (0.12, 0.88):
                p = p0v + d * f
                box(f"{label} láb", (p.x, p.y, z0 / 2), (0.12, t + 0.25, z0), rot, mf, c_walls)

    # floor labels for each hanging surface (readable in top view)
    for s in SURFACES.values():
        p = surf_point(s, s["length"] / 2, 0, 0.35)
        if s["id"] in ("N", "S"):
            p = surf_point(s, 3.0, 0, 0.45)
        if s["id"] in ("E", "W"):
            p = surf_point(s, s["length"] / 2, 0, BENCH_D + 0.45)
        floor_text(s["id"], p.x, p.y, surf_rot(s), 0.28, c_lab, z=0.02 if s["id"] in "NSEW" else 0.005)
    floor_text("KIÁLLÍTÓTÉR 6  (E-102)  178,95 m²", ROOM_W / 2, 1.1, 0, 0.32, c_lab)
    floor_text("lépcső / előtér felé", 8.85, ROOM_L - 0.6, 0, 0.25, c_lab)
    floor_text("5-ös terem felé", 9.0, 0.55, 0, 0.25, c_lab)

    # scale figure
    mperson = material("person")
    body = box("Látogató 170 cm (lépték)", (2.6, 11.5, 0.72), (0.45, 0.25, 1.44), 0, mperson, c_misc)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(2.6, 11.5, 1.58))
    head = bpy.context.active_object
    head.name = "Látogató fej"
    head.data.materials.append(mperson)
    for c in head.users_collection:
        c.objects.unlink(head)
    c_misc.objects.link(head)
    head.parent = body
    head.matrix_parent_inverse = body.matrix_world.inverted()

    # cameras at eye height
    def cam(name, loc, rot_deg, lens=18):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        ob = bpy.data.objects.new(name, cd)
        ob.location = loc
        ob.rotation_euler = [math.radians(a) for a in rot_deg]
        c_misc.objects.link(ob)
        return ob
    c1 = cam("Szem 160 cm – lépcső felőli bejárat", (8.85, ROOM_L - 0.5, 1.60), (90, 0, 180))
    cam("Szem 160 cm – 5-ös terem felőli bejárat", (9.0, 0.5, 1.60), (90, 0, 0))
    cam("Szem 160 cm – sarok DNy", (1.2, 0.9, 1.60), (90, 0, -35))
    top = cam("Felülnézet (alaprajz)", (ROOM_W / 2, ROOM_L / 2, 25), (0, 0, 0), 35)
    top.data.type = "ORTHO"
    top.data.ortho_scale = ROOM_L + 2.5
    scene.camera = c1

    # lights – soft gallery light from the ceiling
    for i, x in enumerate((3.0, 9.0)):
        for j, y in enumerate((3.0, 7.5, 12.0)):
            ld = bpy.data.lights.new(f"Mennyezeti fény {i}{j}", "AREA")
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = 2.5, 3.0
            ld.energy = 110
            lo = bpy.data.objects.new(ld.name, ld)
            lo.location = (x, y, CEILING - 0.02)
            c_misc.objects.link(lo)

    # world
    w = scene.world or bpy.data.worlds.new("World")
    scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.85, 0.87, 0.9, 1)
        bg.inputs[1].default_value = 0.12

    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "CENTIMETERS"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            pass


# --------------------------------------------------------------------------
# Artworks
# --------------------------------------------------------------------------

def _art_material(title, image_path):
    m = bpy.data.materials.new(f"Art – {title}")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.6
    ok = False
    if image_path and os.path.isfile(image_path):
        try:
            img = bpy.data.images.load(image_path, check_existing=True)
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.location = (-400, 200)
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            ok = True
        except RuntimeError:
            pass
    if not ok:
        bsdf.inputs["Base Color"].default_value = (*_lin(COL["art"]), 1)
    m.diffuse_color = (*_lin(COL["art"]), 1)
    return m


def create_artwork(title, w_cm, h_cm, d_cm=3.0, image_path="", wall=STAGING,
                   offset_cm=0.0, centre_cm=DEFAULT_CENTRE_CM, note=""):
    w, h, d = w_cm / 100, h_cm / 100, max(d_cm, 0.5) / 100
    me = bpy.data.meshes.new(f"Art {title}")
    bm = bmesh.new()
    # local frame: X = right, Z = up, -Y = towards the viewer, back face at y = 0
    xs, zs = (-w / 2, w / 2), (-h / 2, h / 2)
    v = {}
    for ix, x in enumerate(xs):
        for iy, y in enumerate((0.0, -d)):
            for iz, z in enumerate(zs):
                v[ix, iy, iz] = bm.verts.new((x, y, z))
    F = lambda *k: bm.faces.new([v[i] for i in k])
    front = F((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1))
    F((1, 0, 0), (0, 0, 0), (0, 0, 1), (1, 0, 1))              # back
    F((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1))              # left
    F((1, 1, 0), (1, 0, 0), (1, 0, 1), (1, 1, 1))              # right
    F((0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1))              # top
    F((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))              # bottom
    bm.normal_update()
    uv = bm.loops.layers.uv.new()
    for f in bm.faces:
        f.material_index = 0 if f is front else 1
        for loop in f.loops:
            co = loop.vert.co
            loop[uv].uv = ((co.x + w / 2) / w, (co.z + h / 2) / h)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(title, me)
    me.materials.append(_art_material(title, image_path))
    me.materials.append(material("frame"))
    get_collection("Műtárgyak", get_collection(ROOT)).objects.link(ob)
    ob.exh_is_art = True
    ob.exh_title = title
    ob.exh_w_cm, ob.exh_h_cm, ob.exh_d_cm = w_cm, h_cm, d_cm
    ob.exh_note = note
    ob.exh_image = image_path or ""
    ob.exh_centre_cm = centre_cm
    ob.exh_offset_cm = offset_cm
    ob.exh_wall = wall if wall in SURFACES else STAGING
    place_artwork(ob)
    return ob


def _staging_slot(ob):
    arts = [o for o in bpy.data.objects if getattr(o, "exh_is_art", False) and o.exh_wall == STAGING]
    arts.sort(key=lambda o: o.name)
    x = 0.0
    for o in arts:
        if o == ob:
            return x + o.exh_w_cm / 200
        x += o.exh_w_cm / 100 + 0.3
    return x


def place_artwork(ob):
    if not getattr(ob, "exh_is_art", False):
        return
    w, h = ob.exh_w_cm / 100, ob.exh_h_cm / 100
    zc = ob.exh_centre_cm / 100
    if ob.exh_wall == STAGING or ob.exh_wall not in SURFACES:
        # staging row south of the room (outside), facing north
        ob.location = (_staging_slot(ob), -2.5, max(zc, h / 2 + 0.05))
        ob.rotation_euler = (0, 0, 0)
        return
    s = SURFACES[ob.exh_wall]
    u = ob.exh_offset_cm / 100 + w / 2
    p = surf_point(s, u, zc, 0.002)
    ob.location = p
    ob.rotation_euler = (0, 0, surf_rot(s))


def _upd(self, context):
    place_artwork(self)
    for o in bpy.data.objects:        # keep staging row tidy
        if getattr(o, "exh_is_art", False) and o.exh_wall == STAGING and o != self:
            place_artwork(o)


_ENUM_CACHE = []


def _wall_items(self, context):
    if not _ENUM_CACHE:
        _ENUM_CACHE.append((STAGING, "— raktár / nincs kihelyezve —", "Staging row outside the room"))
        for s in SURFACES.values():
            _ENUM_CACHE.append((s["id"], s["name"], f"{s['length']*100:.0f} cm hosszú"))
    return _ENUM_CACHE


def check_problems(ob):
    """Return list of warnings for an artwork (openings, overlaps, bounds)."""
    out = []
    if ob.exh_wall not in SURFACES:
        return out
    s = SURFACES[ob.exh_wall]
    u0 = ob.exh_offset_cm / 100
    u1 = u0 + ob.exh_w_cm / 100
    zc = ob.exh_centre_cm / 100
    z0, z1 = zc - ob.exh_h_cm / 200, zc + ob.exh_h_cm / 200
    if u0 < -1e-3 or u1 > s["length"] + 1e-3:
        out.append("kilóg a falról")
    if z0 < s["z0"] - 1e-3 or z1 > s["z1"] + 1e-3:
        out.append("túl magas/alacsony a falhoz")
    for kind, a, b, oz0, oz1 in OPENINGS.get(s["openings"] or "", []):
        if u0 < b and u1 > a and z0 < oz1 and z1 > oz0:
            out.append("ajtóba lóg" if kind == "door" else "ablakba lóg")
    for o in bpy.data.objects:
        if o is ob or not getattr(o, "exh_is_art", False) or o.exh_wall != ob.exh_wall:
            continue
        a0 = o.exh_offset_cm / 100
        a1 = a0 + o.exh_w_cm / 100
        oc = o.exh_centre_cm / 100
        if u0 < a1 and u1 > a0 and z0 < oc + o.exh_h_cm / 200 and z1 > oc - o.exh_h_cm / 200:
            out.append(f"átfed: {o.exh_title}")
    return out


# --------------------------------------------------------------------------
# UI: operators + panel
# --------------------------------------------------------------------------

class EXH_OT_add(bpy.types.Operator):
    bl_idname = "exh.add_artwork"
    bl_label = "Új műtárgy"
    bl_options = {"REGISTER", "UNDO"}
    title: bpy.props.StringProperty(name="Cím", default="Új mű")
    w_cm: bpy.props.FloatProperty(name="Szélesség (cm)", default=82.5, min=1)
    h_cm: bpy.props.FloatProperty(name="Magasság (cm)", default=76.5, min=1)
    d_cm: bpy.props.FloatProperty(name="Mélység (cm)", default=3.3, min=0.1)
    image: bpy.props.StringProperty(name="Kép (opcionális)", subtype="FILE_PATH")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        ob = create_artwork(self.title, self.w_cm, self.h_cm, self.d_cm, bpy.path.abspath(self.image))
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {"FINISHED"}


class EXH_OT_import(bpy.types.Operator):
    bl_idname = "exh.import_csv"
    bl_label = "Műtárgylista importálása (CSV)"
    bl_options = {"REGISTER", "UNDO"}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.csv", options={"HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        n = import_csv(self.filepath)
        self.report({"INFO"}, f"{n} műtárgy importálva")
        return {"FINISHED"}


class EXH_OT_export(bpy.types.Operator):
    bl_idname = "exh.export_csv"
    bl_label = "Függesztési lista exportálása (CSV)"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.csv", options={"HIDDEN"})

    def invoke(self, context, event):
        base = bpy.path.abspath("//") or os.path.expanduser("~")
        self.filepath = os.path.join(base, "fuggesztesi_lista_terem6.csv")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        n, warn = export_csv(self.filepath)
        self.report({"WARNING"} if warn else {"INFO"},
                    f"{n} sor mentve: {self.filepath}" + (f" – {warn} figyelmeztetés" if warn else ""))
        return {"FINISHED"}


class EXH_OT_snap(bpy.types.Operator):
    """Move the selected artworks onto the nearest wall face (keeps position)"""
    bl_idname = "exh.snap_nearest"
    bl_label = "Legközelebbi falra illeszt"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for ob in context.selected_objects:
            if not getattr(ob, "exh_is_art", False):
                continue
            best = None
            for s in SURFACES.values():
                rel = ob.location - s["origin"]
                u = rel.dot(s["right"])
                dist = abs(Vector((rel.x, rel.y, 0)).dot(s["normal"]))
                if -0.5 < u < s["length"] + 0.5 and (best is None or dist < best[0]):
                    best = (dist, s, u)
            if best:
                _, s, u = best
                ob.exh_centre_cm = round(ob.location.z * 100, 1)
                ob.exh_offset_cm = round((u - ob.exh_w_cm / 200) * 100, 1)
                ob.exh_wall = s["id"]
        return {"FINISHED"}


class EXH_OT_centre(bpy.types.Operator):
    """Set the centre height of the selected artworks"""
    bl_idname = "exh.set_centre"
    bl_label = "Középvonal a kijelölteknek"
    bl_options = {"REGISTER", "UNDO"}
    centre: bpy.props.FloatProperty(name="Középmagasság (cm)", default=DEFAULT_CENTRE_CM)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        for ob in context.selected_objects:
            if getattr(ob, "exh_is_art", False):
                ob.exh_centre_cm = self.centre
        return {"FINISHED"}


class EXH_PT_panel(bpy.types.Panel):
    bl_label = "Kiállítás – Terem 6"
    bl_idname = "EXH_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Kiállítás"

    def draw(self, context):
        lay = self.layout
        col = lay.column(align=True)
        col.operator("exh.add_artwork", icon="ADD")
        col.operator("exh.import_csv", icon="IMPORT")
        col.operator("exh.export_csv", icon="EXPORT")
        col.separator()
        col.operator("exh.snap_nearest", icon="SNAP_ON")
        col.operator("exh.set_centre", icon="ALIGN_MIDDLE")
        ob = context.active_object
        if ob and getattr(ob, "exh_is_art", False):
            box_ = lay.box()
            box_.prop(ob, "exh_title", text="Cím")
            box_.label(text=f"{ob.exh_w_cm:g} × {ob.exh_h_cm:g} × {ob.exh_d_cm:g} cm")
            box_.prop(ob, "exh_wall", text="Fal")
            if ob.exh_wall in SURFACES:
                s = SURFACES[ob.exh_wall]
                box_.label(text=f"Fal hossza: {s['length']*100:.0f} cm (balról mérve)")
            box_.prop(ob, "exh_offset_cm", text="Bal széle a fal bal végétől (cm)")
            box_.prop(ob, "exh_centre_cm", text="Középvonal a padlótól (cm)")
            zc = ob.exh_centre_cm
            box_.label(text=f"Alsó él {zc - ob.exh_h_cm/2:.1f} / felső él {zc + ob.exh_h_cm/2:.1f} cm")
            box_.prop(ob, "exh_note", text="Megjegyzés")
            for w in check_problems(ob):
                box_.label(text=w, icon="ERROR")
        else:
            lay.label(text="Jelölj ki egy műtárgyat.", icon="INFO")


CLASSES = (EXH_OT_add, EXH_OT_import, EXH_OT_export, EXH_OT_snap, EXH_OT_centre, EXH_PT_panel)


def register():
    T = bpy.types.Object
    T.exh_is_art = bpy.props.BoolProperty(default=False)
    T.exh_title = bpy.props.StringProperty(default="")
    T.exh_w_cm = bpy.props.FloatProperty(default=50, update=_upd)
    T.exh_h_cm = bpy.props.FloatProperty(default=50, update=_upd)
    T.exh_d_cm = bpy.props.FloatProperty(default=3)
    T.exh_note = bpy.props.StringProperty(default="")
    T.exh_image = bpy.props.StringProperty(default="")
    T.exh_wall = bpy.props.EnumProperty(items=_wall_items, update=_upd)
    T.exh_offset_cm = bpy.props.FloatProperty(default=0, step=100, precision=1, update=_upd)
    T.exh_centre_cm = bpy.props.FloatProperty(default=DEFAULT_CENTRE_CM, step=100, precision=1, update=_upd)
    for c in CLASSES:
        try:
            bpy.utils.unregister_class(c)
        except RuntimeError:
            pass
        bpy.utils.register_class(c)


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
CSV_FIELDS = ["title", "width_cm", "height_cm", "depth_cm", "image", "wall", "offset_cm", "centre_cm", "note"]


def _f(v, default):
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def import_csv(path):
    base = os.path.dirname(path)
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        for row in csv.DictReader(fh, dialect=dialect):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not row.get("title"):
                continue
            img = row.get("image", "")
            if img and not os.path.isabs(img):
                img = os.path.join(base, img)
            create_artwork(row["title"], _f(row.get("width_cm"), 50), _f(row.get("height_cm"), 50),
                           _f(row.get("depth_cm"), 3), img, (row.get("wall") or STAGING).upper(),
                           _f(row.get("offset_cm"), 0), _f(row.get("centre_cm"), DEFAULT_CENTRE_CM),
                           row.get("note", ""))
            n += 1
    return n


def export_csv(path):
    arts = [o for o in bpy.data.objects if getattr(o, "exh_is_art", False)]
    arts.sort(key=lambda o: (o.exh_wall, o.exh_offset_cm))
    warns = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.writer(fh, delimiter=";")
        wr.writerow(["cím", "fal_id", "fal", "szélesség_cm", "magasság_cm", "mélység_cm",
                     "bal_él_a_fal_bal_végétől_cm", "jobb_él_cm", "középvonal_cm",
                     "alsó_él_cm", "felső_él_cm", "figyelmeztetés", "megjegyzés"])
        for o in arts:
            s = SURFACES.get(o.exh_wall)
            w = check_problems(o)
            warns += bool(w)
            wr.writerow([o.exh_title, o.exh_wall, s["name"] if s else "raktár",
                         f"{o.exh_w_cm:g}", f"{o.exh_h_cm:g}", f"{o.exh_d_cm:g}",
                         f"{o.exh_offset_cm:.1f}", f"{o.exh_offset_cm + o.exh_w_cm:.1f}",
                         f"{o.exh_centre_cm:.1f}",
                         f"{o.exh_centre_cm - o.exh_h_cm / 2:.1f}", f"{o.exh_centre_cm + o.exh_h_cm / 2:.1f}",
                         " | ".join(w), o.exh_note])
    return len(arts), warns


# --------------------------------------------------------------------------
# Entry
# --------------------------------------------------------------------------

def build(clear=True):
    if clear:
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        for c in list(bpy.data.collections):
            bpy.data.collections.remove(c)
        for m in list(bpy.data.materials):
            bpy.data.materials.remove(m)
    build_room()


register()
if bpy.data.collections.get(ROOT) is None:
    build()
