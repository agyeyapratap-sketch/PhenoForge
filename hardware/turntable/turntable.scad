// PhenoForge motorised turntable: 3D-printable parts (MIT licence).
//
// A 40-50 cm wooden platter on a lazy-susan bearing, turned by a NEMA 17 stepper
// through a GT2 belt (20T motor pulley -> printed 120T pulley, 6:1). The parts carry
// root crowns up to ~5 kg and potted plants up to ~30 cm pots.
//
// Export one part:  openscad -D 'part="big_pulley"' -o big_pulley.stl turntable.scad
// Parts: big_pulley, motor_cradle, riser, crown_hub, stem_cup, pot_ring,
//        home_sensor_post, assembly (preview only)
//
// Print in PETG or PLA+, 0.2 mm layers, 4 walls, 30-40 % gyroid infill.

part = "assembly";
show_platter = true;   // false shows the drive under the platter
show_bearing = true;

/* [Bought parts: measure yours and edit] */
bearing_t        = 8;     // lazy-susan bearing thickness (mm)
bearing_opening  = 130;   // free centre opening of the bearing (needs >= 120 mm)
riser_h          = 75;    // base board to the underside of the bearing
motor_len        = 40;    // NEMA 17 body length (17HS4401 = 40)
motor_pulley_teeth = 20;  // aluminium GT2 20T, 5 mm bore (bought)
big_teeth        = 120;   // printed pulley -> 6:1 reduction
belt_w           = 6;     // GT2 belt width
belt_loop        = 300;   // closed GT2 loop length (300 mm -> 73 mm centre distance)
screw_d          = 4.4;   // M4 clearance
nut_m4_af        = 7.2;   // M4 nut across flats (+ tolerance)
rod_d            = 8.4;   // M8 threaded rod clearance
nut_m8_af        = 13.3;  // M8 nut across flats
pot_d            = 150;   // pot base outer diameter for pot_ring
stem_d           = 50;    // stem stub inner cup diameter for stem_cup

/* [Derived] */
pitch = 2;
pd_big = big_teeth * pitch / PI;            // 76.39 mm for 120T
pd_small = motor_pulley_teeth * pitch / PI; // 12.73 mm for 20T
// centre distance from the belt length: L = 2C + pi(D+d)/2 + (D-d)^2/(4C)
_a = 2; _b = -(belt_loop - PI * (pd_big + pd_small) / 2); _c = pow(pd_big - pd_small, 2) / 4;
centre_dist = (-_b + sqrt(_b * _b - 4 * _a * _c)) / (2 * _a);
cradle_plate_z = 3 + motor_len + 1;         // underside of the motor face plate
belt_z = cradle_plate_z + 5 + 1 + 4 + belt_w / 2 + 1;  // belt centre height on a 20T pulley
platter_z = riser_h + bearing_t;            // underside of the platter
bolt_r = 47;                                // M4 bolt circle through platter (hub <-> pulley)
flange_d = 110;

echo(str("centre distance = ", centre_dist, " mm; belt centre z = ", belt_z, " mm; platter underside z = ", platter_z, " mm"));
$fn = 96;

module hexagon(af, h) { cylinder(d = af / cos(30), h = h, $fn = 6); }

// GT2 pulley body: grooves approximate the 2 mm GT2 tooth (r 0.555 mm, depth 0.75 mm)
module gt2_teeth(teeth, h) {
    od = teeth * pitch / PI - 0.508;
    difference() {
        cylinder(d = od, h = h, $fn = teeth * 4);
        for (i = [0 : teeth - 1]) rotate(i * 360 / teeth)
            translate([od / 2 - 0.195, 0, -1]) cylinder(r = 0.555, h = h + 2, $fn = 16);
    }
}

module bolt_circle(r = bolt_r, n = 4, a0 = 45) {
    for (i = [0 : n - 1]) rotate(a0 + i * 360 / n) translate([r, 0, 0]) children();
}

// Hangs under the platter through the bearing opening; belt runs at belt_z.
module big_pulley() {
    drop = platter_z - belt_z;           // platter underside -> belt centre
    zone = belt_w + 2;
    flg_d = pd_big + 6;
    body = drop - zone / 2;              // solid tube down to the belt zone
    // printed flange-down: z = 0 is the face that touches the platter
    difference() {
        union() {
            cylinder(d = flange_d, h = 6);                              // mounting flange
            cylinder(d = flg_d, h = body);                              // tube + lower belt flange
            translate([0, 0, body]) gt2_teeth(big_teeth, zone);
            translate([0, 0, body + zone]) cylinder(d1 = pd_big - 0.6, d2 = flg_d, h = 3);   // chamfered top flange, no overhang
        }
        translate([0, 0, -1]) cylinder(d = 50, h = body + zone + 5);   // weight saving / rod clearance
        bolt_circle() {
            translate([0, 0, -1]) cylinder(d = screw_d, h = 10);
            translate([0, 0, 3]) hexagon(nut_m4_af, 4);                 // nut recess on the underside
        }
        // magnet pocket (6 x 3 mm) for the optional hall-effect home sensor
        translate([-(flange_d / 2 - 4), 0, 3]) cylinder(d = 6.3, h = 3.1, $fn = 32);   // opposite the motor
    }
}

// NEMA 17 hangs face-up under the top plate; slots let it slide to tension the belt.
module motor_cradle() {
    w = 60; post = 8; top_t = 5; slot = 16;
    difference() {
        union() {
            translate([-w / 2, -w / 2, 0]) cube([w, w, 3]);                          // foot
            for (sx = [-1, 1], sy = [-1, 1]) translate([sx * (w / 2 - post / 2) - post / 2, sy * (w / 2 - post / 2) - post / 2, 0])
                cube([post, post, cradle_plate_z + top_t]);                             // posts
            translate([-w / 2, -w / 2, cradle_plate_z]) cube([w, w, top_t]);          // face plate
            for (sx = [-1, 1]) translate([sx * (w / 2 + 15) - 15, -w / 2, 0]) cube([30, w, 3]);   // slotted ears
        }
        translate([0, 0, -1]) cylinder(d = 23, h = 100);                               // motor boss / shaft
        for (sx = [-1, 1], sy = [-1, 1]) translate([sx * 15.5, sy * 15.5, cradle_plate_z - 1]) cylinder(d = 3.4, h = 10);
        translate([-21.5, -21.5, 2.99]) cube([43, 43, cradle_plate_z - 3]);           // motor body
        // slots along x (the belt direction) for +-8 mm of belt tension
        for (sx = [-1, 1], y = [-18, 18]) hull() for (dx = [-slot / 2, slot / 2])
            translate([sx * (w / 2 + 15) + dx, y, -1]) cylinder(d = screw_d, h = 5);
    }
}

// U-bracket: foot screwed to the base board, top slot under a bearing mounting hole.
module riser() {
    w = 34; t = 5;
    difference() {
        union() {
            translate([-w / 2, -20, 0]) cube([w, 40, t]);                   // foot
            translate([-w / 2, -t / 2, 0]) cube([w, t, riser_h]);           // web
            translate([-w / 2, -20, riser_h - t]) cube([w, 40, t]);         // top
            for (sx = [-1, 1]) translate([sx * (w / 2 - 2) - 2, -20, 0]) cube([4, 40, riser_h]);  // side walls
        }
        for (y = [-12, 12]) translate([0, y, -1]) cylinder(d = screw_d, h = t + 2);
        for (y = [-12, 12]) translate([0, y, t]) cylinder(d = 10, h = riser_h - 2 * t - 0.01);   // screwdriver access
        hull() for (y = [6, 16]) translate([0, y, riser_h - t - 1]) cylinder(d = screw_d, h = t + 2);
        hull() for (y = [-16, -6]) translate([0, y, riser_h - t - 1]) cylinder(d = screw_d, h = t + 2);
    }
}

// On top of the platter: clamps it to the big pulley and holds an M8 rod upright.
module crown_hub() {
    difference() {
        union() {
            cylinder(d = flange_d, h = 6);
            cylinder(d = 32, h = 18);
        }
        translate([0, 0, -1]) cylinder(d = rod_d, h = 30);
        translate([0, 0, 8]) hexagon(nut_m8_af, 11);                        // two M8 nuts lock the rod
        bolt_circle() { translate([0, 0, -1]) cylinder(d = screw_d, h = 10); translate([0, 0, 4]) cylinder(d = 8.5, h = 10); }
    }
}

// Cup on the top of the rod: grips a 5-10 cm stem stub with three M5 thumb screws,
// so a root crown sits stem-down with the roots free all round.
module stem_cup() {
    h = 40; wall = 5; base = 14;
    difference() {
        union() {
            cylinder(d = stem_d + 2 * wall, h = base + h);
            for (i = [0 : 2]) rotate(i * 120) translate([stem_d / 2 + wall - 2, -7, base + h / 2 - 7]) cube([8, 14, 14]);
        }
        translate([0, 0, base]) cylinder(d = stem_d, h = h + 1);
        translate([0, 0, -1]) cylinder(d = rod_d, h = base + 2);
        translate([0, 0, -0.01]) hexagon(nut_m8_af, 7);
        for (i = [0 : 2]) rotate(i * 120) translate([0, 0, base + h / 2]) rotate([0, 90, 0]) {
            cylinder(d = 5.4, h = stem_d);
            translate([0, 0, stem_d / 2 + wall + 1]) rotate(30) hexagon(8.3, 4.2);   // M5 nut slot
        }
    }
}

// Centres a pot on the platter; the pot rests on the inner ledge above the hub.
module pot_ring() {
    h = 26; wall = 3; ledge = 8;
    difference() {
        union() {
            cylinder(d = pot_d + 2 * wall, h = h);
            for (i = [0 : 2]) rotate(i * 120) translate([pot_d / 2, -8, 0]) cube([18, 16, 3]);
        }
        translate([0, 0, 20]) cylinder(d = pot_d + 0.8, h = h);
        translate([0, 0, -1]) cylinder(d = pot_d - 2 * ledge, h = h);
        for (i = [0 : 2]) rotate(i * 120) translate([pot_d / 2 + 11, 0, -1]) cylinder(d = screw_d, h = 5);
    }
}

// Holds an A3144 / KY-003 hall sensor 2 mm under the magnet in the big pulley flange.
module home_sensor_post() {
    h = platter_z - 6 - 2;
    difference() {
        union() {
            translate([-15, -15, 0]) cube([30, 30, 3]);
            translate([-6, -6, 0]) cube([12, 12, h]);
        }
        for (s = [-1, 1]) translate([s * 10.5, s * 10.5, -1]) cylinder(d = screw_d, h = 5);
        translate([-2.5, -1, h - 4]) cube([5, 2, 5]);          // TO-92 slot
        translate([-1.5, -6.5, 8]) cube([3, 4, h]);            // wire channel
    }
}

module platter_dummy() { color("BurlyWood", 0.6) translate([0, 0, platter_z]) cylinder(d = 450, h = 12); }

module parts_layout() {
    translate([0, 0, 0]) color("ForestGreen") big_pulley();
    translate([140, 0, 0]) color("ForestGreen") crown_hub();
    translate([290, 0, 0]) color("SteelBlue") motor_cradle();
    translate([0, 150, 0]) color("ForestGreen") stem_cup();
    translate([130, 150, 0]) color("Orange") home_sensor_post();
    translate([300, 170, 0]) color("ForestGreen") pot_ring();
    for (i = [0 : 3]) translate([-20 + i * 50, 260, 0]) color("SteelBlue") riser();
}

module assembly() {
    color("SaddleBrown", 0.5) translate([-250, -250, -18]) cube([500, 500, 18]);           // base board
    for (a = [45 : 90 : 360]) rotate(a) translate([135, 0, 0]) rotate(90) color("SteelBlue") riser();
    if (show_bearing) color("Silver", 0.7) translate([0, 0, riser_h]) difference() { cylinder(d = 300, h = bearing_t); translate([0, 0, -1]) cylinder(d = bearing_opening, h = bearing_t + 2); }
    if (show_platter) platter_dummy();
    color("ForestGreen") translate([0, 0, platter_z]) mirror([0, 0, 1]) big_pulley();
    color("ForestGreen") translate([0, 0, platter_z + 12]) crown_hub();
    color("Gray") translate([0, 0, platter_z + 12]) cylinder(d = 8, h = 220);
    color("ForestGreen") translate([0, 0, platter_z + 12 + 200]) stem_cup();
    translate([centre_dist, 0, 0]) {
        color("SteelBlue") motor_cradle();
        color("DimGray") translate([-21, -21, 3]) cube([42, 42, motor_len]);
        color("Gold") translate([0, 0, belt_z - 8]) cylinder(d = 16, h = 16);
    }
    color("Black") translate([0, 0, belt_z - belt_w / 2]) linear_extrude(belt_w)
        difference() { hull() { circle(d = pd_big + 1.5); translate([centre_dist, 0]) circle(d = pd_small + 1.5); }
                       hull() { circle(d = pd_big - 0.5); translate([centre_dist, 0]) circle(d = pd_small - 0.5); } }
    translate([-(flange_d / 2 - 4), 0, 0]) color("Orange") home_sensor_post();
}

if (part == "big_pulley") big_pulley();
else if (part == "motor_cradle") motor_cradle();
else if (part == "riser") riser();
else if (part == "crown_hub") crown_hub();
else if (part == "stem_cup") stem_cup();
else if (part == "pot_ring") pot_ring();
else if (part == "home_sensor_post") home_sensor_post();
else if (part == "parts_layout") parts_layout();
else assembly();
