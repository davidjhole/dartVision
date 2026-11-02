// ============================================================
//  DART HALO v3  –  slim profile
//  Ring section ~42 wide x 24 deep, fully rounded outer edge.
//  The translucent diffuser IS the inner bevel (glows onto the
//  board, never visible from the oche).  Camera pods carry the
//  extra depth the camera needs as a bulge on the BACK.
//
//  z = 0 wall, z = board_thick board face.  PLA throughout.
//  Set `part`, F6, export STL.
// ============================================================

/* [Render] */
// assembly | seg_plain | seg_cam_a | seg_cam_b | pod | diffuser | leg | splice | pad | knob
part = "assembly";

/* [Board] */
board_d     = 451;
board_thick = 38;

/* [Ring] */
Rin     = 258;    // inner front edge
Rout    = 300;    // outer edge  -> 600 mm across
D       = 24;     // ring depth (front to back)
zf      = 110;    // front face height off the wall
bev_run = 14;     // radial run of the inner bevel
skin    = 2.4;    // wall thickness
segments = 8;

/* [LED + diffuser] */
led_gap   = 6;    // strip -> diffuser
diff_t    = 1.5;
diff_arc  = 39;   // degrees per diffuser piece (2 per bay)

/* [Camera pods] */
cam_tilt  = 33;
cam_z     = 86.5; // lens centre height (board face is 38)
pcb_w     = 32.5;
lens_len  = 12;
lens_d    = 15;
hole_sp   = 28;
win_w     = 44;
boss_w    = 11;
bulge_z   = 66;   // pod bulges back to here (hidden behind ring)

/* [Legs] */
leg_w     = 24;
clamp_gap = 11;
lip       = 8;
m6 = 6.6;  m6_af = 10;  m6_nut_t = 5.4;

/* [Hardware] */
m3_insert = 4.2;  m3_clear = 3.4;
m4_insert = 5.6;  m4_clear = 4.5;

$fn = 48;

// ---------------- derived ----------------
Rb   = board_d / 2;
face = board_thick;
zb   = zf - D;
rr   = D / 2;                     // outer round radius (full half-round)
rc   = Rout - rr;                 // centre of the round
L    = sqrt(bev_run*bev_run + D*D);
vr = bev_run/L;  vz = -D/L;       // along bevel (front-inner -> back)
nr = -D/L;       nz = -bev_run/L; // bevel normal (towards board)
A  = [Rin, zf];
B  = [Rin + bev_run, zb];
seg_a = 360 / segments;
cham_n = -(led_gap + 3);          // LED chamber floor (strip sits here)
wall_n = cham_n - skin;           // back of LED wall
function bp(u, n) = [A[0] + u*vr + n*nr, A[1] + u*vz + n*nz];
// radius of the LED-wall back line at height z
function wall_r(z) = let(p = bp(0, wall_n)) p[0] + vr * (p[1] - z) / (-vz);
open_r0 = wall_r(zb) + 0.5;  open_r1 = rc + 5;   // cable slot at the back
back_r0 = B[0];  back_r1 = open_r0;              // solid back face for screws
scr_r   = (back_r0 + back_r1) / 2;
function ang(len, r) = len / r * 180 / PI;

// ---------- 2D ----------
function round_pts(c, r, a0, a1, n=24) = [for (i=[0:n]) let(a = a0 + (a1-a0)*i/n) [c[0] + r*cos(a), c[1] + r*sin(a)]];
// outer front edge: 45 deg chamfer (prints cleanly front-face-down, no droop);
// back corner square. Segments print FRONT FACE DOWN.
module hull2d() { polygon([A, [rc, zf], [Rout, zf - rr], [Rout, zb], B]); }
module bev2d() { multmatrix([[vr, nr, 0, A[0]], [vz, nz, 0, A[1]], [0,0,1,0], [0,0,0,1]]) children(); }
module chamber2d() {
    intersection() {                                   // LED chamber, kept clear of the front skin
        bev2d() translate([-5, cham_n]) square([L - 2.5 + 5, -cham_n + 0.3]);
        translate([0, -1000]) square([1000, zf - skin + 1000]);
    }
    bev2d() {
        translate([2.5, -1.3]) square([L - 2.5 + 1, 1.6]); // light window (open at the back end: the
                                                         // diffuser's back edge sits on a ledge, no lip)
        translate([2.7, -3.0]) square([L - 3.7, 1.8]);  // diffuser groove (slide-in); starts at 2.7 so it
                                                         // stays under the front skin instead of cutting it off
    }
}
module channel2d() {
    intersection() { offset(delta=-skin) hull2d(); bev2d() translate([-60, -100]) square([200, 100 + wall_n]); }
    translate([open_r0, zb - 1]) square([open_r1 - open_r0, skin + 2]);
}
module led2d() { bev2d() translate([L/2 - 5, cham_n]) square([10, 1.2]); }
module diffuser2d() { bev2d() translate([2.85, -2.85]) square([L - 4.0, diff_t]); }
module body2d() { difference() { hull2d(); chamber2d(); channel2d(); } }

// skin that stays continuous across a camera window: front plate + outer rim + back corner
module keep2d() {
    intersection() {
        difference() { hull2d(); offset(delta=-skin) hull2d(); }
        union() {
            translate([0, zf - skin]) square([1000, 50]);          // front plate
            translate([rc, -1000]) square([1000, 2000]);            // outer rim / wall / back corner
        }
    }
}
module window2d() { difference() { offset(delta=0.01) hull2d(); keep2d(); } }

// ---------- 3D helpers ----------
module sector(a) { rotate(-a/2) rotate_extrude(angle=a, $fn=360) children(); }
module polar_box(r0, r1, z0, z1, w) { translate([r0, -w/2, z0]) cube([r1-r0, w, z1-z0]); }
module bev3d() { multmatrix([[vr, nr, 0, A[0]], [0,0,1,0], [vz, nz, 0, A[1]], [0,0,0,1]]) children(); }
module solid_block(a) { sector(a) difference() { hull2d(); chamber2d(); } }   // fills the cable channel

// ---------- segment ----------
jb_w = 12;  jb_a = ang(jb_w, 285);
module seg_base(extra_cut=false) {
    difference() {
        union() {
            sector(seg_a) body2d();
            for (s=[-1,1]) rotate(s*(seg_a/2 - jb_a/2)) solid_block(jb_a);
        }
        for (s=[-1,1]) rotate(s*(seg_a/2 - jb_a/2)) for (r=[scr_r, open_r1 - 3.5])
            translate([r, 0, zb - 1]) cylinder(d=m3_insert, h=7);
    }
}
leg_off = 15;          // legs sit 15 deg from each camera -> 2, 4, 8, 10 o'clock
leg_boss_a = ang(30, 285);
module leg_boss_add() { solid_block(leg_boss_a); }
module leg_boss_cut() {
    for (r=[scr_r, open_r1 - 4]) translate([r, 0, zb - 1]) cylinder(d=m4_insert, h=10);
    intersection() { sector(leg_boss_a + 2) channel2d(); translate([0,0,zb + 9]) cylinder(r=400, h=50); }
}
module seg_plain() { seg_base(); }
win_a  = ang(win_w, Rin);
boss_a = ang(boss_w, 285);
module seg_cam(leg_s=0) {
    difference() {
        union() {
            seg_base();
            if (leg_s != 0) rotate(leg_s*leg_off) leg_boss_add();
            for (s=[-1,1]) rotate(s*(win_a/2 + boss_a/2)) solid_block(boss_a);
        }
        if (leg_s != 0) rotate(leg_s*leg_off) leg_boss_cut();
        rotate(-win_a/2) rotate_extrude(angle=win_a, $fn=360) window2d();
        for (s=[-1,1]) rotate(s*(win_a/2 + boss_a/2)) translate([scr_r, 0, zb - 1]) cylinder(d=m3_insert, h=8);
        // LED wires from chamber into channel, just past the bosses
        for (s=[-1,1]) rotate(s*(win_a/2 + boss_a + 2)) hull() {
            p0 = bp(L/2, cham_n + 0.5); p1 = bp(L/2, wall_n - 2);
            translate([p0[0], 0, p0[1]]) sphere(d=4.5, $fn=16);
            translate([p1[0], 0, p1[1]]) sphere(d=4.5, $fn=16);
        }
    }
}

// ---------- camera pod ----------
Lc = [Rin + bev_run * (zf - cam_z) / D, cam_z];
module cam_frame() { translate([Lc[0], 0, Lc[1]]) rotate([0, -cam_tilt, 0]) rotate([0,0,180]) children(); }
module pcb_pocket() { cam_frame() translate([-lens_len - 3.5, -pcb_w/2, -pcb_w/2]) cube([3.51, pcb_w, pcb_w]); }
module cam_cuts() {
    hull() { pcb_pocket(); translate([0, 0, -40]) pcb_pocket(); }        // module drops in from the back
    cam_frame() {
        rotate([0, 90, 0]) translate([0,0,-lens_len - 1]) cylinder(d=lens_d, h=lens_len + 2);
        rotate([0, 90, 0]) translate([0,0,-0.5]) cylinder(d1=lens_d, d2=lens_d + 60, h=25);   // view flare
        for (y=[-1,1], z=[-1,1]) translate([-lens_len + 0.01, y*hole_sp/2, z*hole_sp/2])
            rotate([0, 90, 0]) cylinder(d=1.7, h=6);
    }
}
pod_rmax = open_r1 - 0.4;     // must pass the back lip when inserted from behind
module pod() {
    difference() {
        union() {
            rotate(-win_a/2 + 0.2) rotate_extrude(angle=win_a - 0.4, $fn=360)
                intersection() {
                    difference() {
                        union() {
                            hull2d();
                            translate([B[0] - 6, bulge_z]) square([pod_rmax - B[0] + 6, zb - bulge_z + 0.01]);
                        }
                        offset(delta=0.3) keep2d();                         // clearance to the ring skin
                    }
                    translate([0, -1000]) square([pod_rmax, 2000]);
                }
            span = win_a + 2*boss_a;
            rotate(-span/2) rotate_extrude(angle=span, $fn=360)
                translate([back_r0, zb - 4]) square([back_r1 - back_r0, 4]);   // flange onto the bosses
        }
        cam_cuts();
        for (s=[-1,1]) rotate(s*(win_a/2 + boss_a/2)) translate([scr_r, 0, zb - 10]) cylinder(d=m3_clear, h=20);
    }
}

// ---------- diffuser ----------
module diffuser() { sector(diff_arc) diffuser2d(); }

// ---------- splice ----------
module splice() {
    a = 2*jb_a - 0.5;
    difference() {
        sector(a) translate([back_r0 + 0.5, zb - 4]) square([open_r1 - back_r0 - 1, 3.8]);
        for (s=[-1,1]) rotate(s*jb_a/2) for (r=[scr_r, open_r1 - 3.5]) {
            translate([r, 0, zb - 10]) cylinder(d=m3_clear, h=20);
            translate([r, 0, zb - 10]) cylinder(d=6.2, h=10 - 4 + 1.6);
        }
    }
}

// ---------- leg ----------
pad_r0 = back_r0;  pad_r1 = open_r1 + 1;
P = [
    [Rb + clamp_gap,      4],
    [Rb + clamp_gap + 22, 4],
    [Rb + clamp_gap + 22, 18],
    [pad_r1,              zb - 14],
    [pad_r1,              zb],
    [pad_r0,              zb],
    [pad_r0,              zb - 8],
    [Rb + 6,              face + lip],
    [Rb - lip,            face + lip],
    [Rb - lip,            face],
    [Rb + clamp_gap,      face]
];
clamp_z = face / 2;
module leg() {
    difference() {
        rotate([90,0,0]) linear_extrude(leg_w, center=true) polygon(P);
        translate([0, leg_w/2 - 8, 0]) rotate([90,0,0]) translate([0,0,-10]) linear_extrude(10)
            offset(delta=-4.5) polygon([P[2], P[3], P[6], P[7]]);
        translate([Rb + clamp_gap - 1, 0, clamp_z]) rotate([0, 90, 0]) cylinder(d=m6, h=40);
        translate([Rb + clamp_gap + 11 - m6_nut_t/2, 0, clamp_z]) hull() {
            rotate([0, 90, 0]) cylinder(d=(m6_af + 0.4)/cos(30), h=m6_nut_t, $fn=6);
            translate([0, -30, 0]) rotate([0, 90, 0]) cylinder(d=(m6_af + 0.4)/cos(30), h=m6_nut_t, $fn=6);
        }
        for (r=[scr_r, open_r1 - 4]) {
            translate([r, 0, zb - 12]) cylinder(d=m4_clear, h=20);
            translate([r, 0, -1]) cylinder(d=8.5, h=zb - 12 + 1);
        }
    }
}
module pad() { difference() { union() { cylinder(d=20, h=3); cylinder(d=12, h=8); } translate([0,0,3]) cylinder(d=6.2, h=6); } }
module knob() {
    difference() {
        union() { cylinder(d=30, h=10, $fn=24); cylinder(d=16, h=14); }
        translate([0,0,-1]) cylinder(d=(m6_af + 0.3)/cos(30), h=5.2, $fn=6);
        translate([0,0,-1]) cylinder(d=m6, h=20);
    }
}

// ---------- assembly ----------
c_halo = [0.17, 0.17, 0.19];  c_leg = [0.12, 0.12, 0.13];
c_pod  = [0.22, 0.22, 0.24];  c_diff = [1.0, 0.95, 0.80];
module board_model() {
    color([0.1,0.1,0.1]) cylinder(r=Rb, h=face - 0.6, $fn=180);
    for (i=[0:19]) rotate(i*18 + 9) {
        color(i%2 ? [0.86,0.81,0.66] : [0.09,0.09,0.09])
            translate([0,0,face - 0.6]) rotate(-9) rotate_extrude(angle=18, $fn=120) translate([16,0]) square([154, 0.6]);
        color(i%2 ? [0.1,0.5,0.2] : [0.75,0.1,0.1])
            translate([0,0,face - 0.5]) rotate(-9) rotate_extrude(angle=18, $fn=120)
                union() { translate([99,0]) square([8, 0.6]); translate([162,0]) square([8, 0.6]); }
    }
    color([0.1,0.5,0.2]) translate([0,0,face - 0.5]) cylinder(r=16, h=0.6);
    color([0.75,0.1,0.1]) translate([0,0,face - 0.4]) cylinder(r=6.35, h=0.6);
}
module assembly(show_board=true) {
    if (show_board) board_model();
    for (i=[0:segments-1]) rotate(i*seg_a) color(c_halo)
        if (i%2==0) seg_plain(); else seg_cam(((i-1)/2) % 2 == 0 ? -1 : 1);
    for (a=[30, 150, 210, 330]) rotate(a) color(c_leg) leg();
    for (i=[0:3]) rotate(45 + i*90) color(c_pod) pod();
    for (i=[0:3]) rotate(i*90 + 45) for (s=[-1,1]) rotate(s*(win_a/2 + 0.4 + diff_arc/2)) color(c_diff) diffuser();
    for (i=[0:segments-1]) rotate(i*seg_a + seg_a/2) color(c_leg) splice();
}
module brain_ghost() { rotate(-90) translate([open_r1 - 2, -55, 6]) color([0.1,0.1,0.11]) cube([44, 110, zb - 10]); }
module back_down()  { translate([0,0,-zb]) children(); }            // back face on the bed
module front_down() { translate([0,0,zf]) rotate([180,0,0]) children(); }   // front face on the bed
module flip()       { rotate([180,0,0]) children(); }

// ---- print orientation: every STL comes out ready to drop on the plate ----
if (part == "assembly")  assembly();
if (part == "seg_plain") front_down() seg_plain();
if (part == "seg_cam_a") front_down() seg_cam(-1);   // cameras at 45 / 225 deg
if (part == "seg_cam_b") front_down() seg_cam(1);    // cameras at 135 / 315 deg (mirror)
if (part == "pod")       flip() pod();               // front face down - needs supports under the 2 tabs
if (part == "diffuser")  diffuser();
if (part == "leg")       rotate([90,0,0]) leg();     // pocket side up
if (part == "splice")    flip() splice();            // screw recesses up
if (part == "pad")       pad();
if (part == "knob")      knob();
