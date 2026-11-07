// ============================================================
//  DART HALO v4  –  light-only ring + camera legs
//
//  * The ring is ONLY the light: 8 segments, continuous LED chamber
//    and diffuser all the way round (no camera windows).
//  * Segments join with a 45 deg SCARF (sloped overlap) and 2 M3
//    screws per joint, square to the slope. No splice plates.
//    The slope self-aligns the faces and prints without supports
//    (segments print front face down).
//  * 4 LEGS at 2, 4, 8, 10 o'clock. Each leg clamps the board edge
//    (M6 knob) and HOLDS A CAMERA, so the whole thing moves with the
//    board: works on a wall or a dartboard stand.
//
//  z = 0 wall / back of board, z = board_thick board face.  PLA.
//  Set `part`, F6, export STL.
// ============================================================

/* [Render] */
// assembly | seg_plain | seg_leg_a | seg_leg_b | diffuser | hub | arm | leg_fin
// Cameras sit rotated 90 deg (connector sideways): set rotate: 90 for them in config.yaml
//   (later: ebox | ebox_lid - electronics box, space reserved behind the board at 12 o'clock)
//   (wall/board-clamp version instead of the stand mount: leg | cam_cover | pad | knob)
part = "assembly";

/* [Board] */
board_d     = 451;
board_thick = 38;

/* [Ring] */
Rin     = 258;    // inner front edge
Rout    = 300;    // outer edge  -> 600 mm across
D       = 24;     // ring depth (front to back)
zf      = 110;    // front face height off the wall
bev_run = 14;     // radial run of the inner bevel (LED face)
skin    = 2.4;
segments = 8;

/* [LED + diffuser] */
led_gap   = 6;
diff_t    = 1.5;

/* [Joints] */
scarf_len = 24;   // overlap length along the ring (= D -> 45 deg slope)

/* [Legs + cameras] */
leg_w     = 40;
leg_off   = 15;   // legs sit 15 deg from the 45 deg lines -> 2, 4, 8, 10 o'clock
clamp_gap = 11;
lip       = 8;
cam_r     = 253;  // lens tip (at lens_len), radius from the bull
cam_h     = 28;   // lens height above the board face (raised 4 mm: room for the plug below the camera)
lens_len  = 22;   // PCB front face -> lens tip: yours winds 18..25, 22 is the middle
lens_min = 18;  lens_max = 25;
pcb_w     = 32.5; // camera board size
hole_sp   = 28;   // camera board hole spacing
holder_w  = 27;   // lens holder + its screw ears (clearance recess) - generous until measured
holder_h  = 18;  holder_d = 10;   // holder height, depth off the board front
m6 = 6.6;  m6_af = 10;  m6_nut_t = 5.4;

/* [Hardware] */
m3_insert = 4.2;  m3_clear = 3.4;  m3_head = 6.2;
m4_insert = 5.6;  m4_clear = 4.5;

$fn = 48;

// ---------------- derived ----------------
Rb   = board_d / 2;
face = board_thick;
zb   = zf - D;
zmid = (zf + zb) / 2;
rr   = D / 2;
rc   = Rout - rr;
L    = sqrt(bev_run*bev_run + D*D);
vr = bev_run/L;  vz = -D/L;
nr = -D/L;       nz = -bev_run/L;
A  = [Rin, zf];
B  = [Rin + bev_run, zb];
seg_a = 360 / segments;
cham_n = -(led_gap + 3);
wall_n = cham_n - skin;
function bp(u, n) = [A[0] + u*vr + n*nr, A[1] + u*vz + n*nz];
function wall_r(z) = let(p = bp(0, wall_n)) p[0] + vr * (p[1] - z) / (-vz);
open_r0 = wall_r(zb) + 0.5;  open_r1 = Rout - skin;
function ang(len, r) = len / r * 180 / PI;

// ---------- 2D section (same proven profile as v3) ----------
module hull2d() { polygon([A, [rc, zf], [Rout, zf - rr], [Rout, zb], B]); }
module bev2d() { multmatrix([[vr, nr, 0, A[0]], [vz, nz, 0, A[1]], [0,0,1,0], [0,0,0,1]]) children(); }
module chamber2d() {
    intersection() {
        bev2d() translate([-5, cham_n]) square([L - 2.5 + 5, -cham_n + 0.3]);
        translate([0, -1000]) square([1000, zf - skin + 1000]);
    }
    bev2d() {
        translate([2.5, -1.3]) square([L - 2.5 + 1, 1.6]);   // light window
        translate([2.7, -3.0]) square([L - 3.7, 1.8]);      // diffuser groove
    }
}
module channel2d() {        // cable channel behind the LED wall, open slot at the back
    intersection() { offset(delta=-skin) hull2d(); bev2d() translate([-60, -100]) square([200, 100 + wall_n]); }
    translate([open_r0, zb - 1]) square([open_r1 - open_r0, skin + 2]);
}
module diffuser2d() { bev2d() translate([2.85, -2.85]) square([L - 4.0, diff_t]); }

// ---------- 3D helpers ----------
module sector(a) { rotate(-a/2) rotate_extrude(angle=a, $fn=360) children(); }
module wedge(a)  { rotate(-a/2) rotate_extrude(angle=a, $fn=360) translate([0, -1000]) square([1000, 2000]); }
// prism along x (radial) from a 2D outline drawn in (y, z)
module yz_prism(pts) { multmatrix([[0,0,1,0],[1,0,0,0],[0,1,0,0],[0,0,0,1]]) translate([0,0,150]) linear_extrude(200) polygon(pts); }

// ---------- scarf joint (joint-local frame: x radial, y along the ring, z) ----------
function sf(z) = (z - zmid) * scarf_len / D;      // the sloped face: y = sf(z)
module scarf_keep(s) {                            // s=+1: segment on the +y side keeps y > sf(z)
    z0 = -50; z1 = 250;
    if (s > 0) yz_prism([[sf(z0), z0], [400, z0], [400, z1], [sf(z1), z1]]);
    else       yz_prism([[-400, z0], [sf(z0), z0], [sf(z1), z1], [-400, z1]]);
}
sn = [0, 1, -1] / sqrt(2);                        // screw axis: square to the slope, into the +y part, towards the back
module along(p0, s0, s1, d) { translate(p0 + s0*sn) rotate([225, 0, 0]) cylinder(d=d, h=s1 - s0); }
// [radius, height where the screw crosses the slope, counterbore start along the axis]
joint_screws = [[287.5, 98, 10],     // M3 x 16
                [295.0, 92,  4]];    // M3 x 10
jw_a = ang(36, 285);                              // solid block around each joint
module joint_cut(s) {                             // s=+1: this segment is the +y part (screw heads)
    for (j = joint_screws) {
        p0 = [j[0], sf(j[1]), j[1]];
        if (s > 0) { along(p0, -0.5, 30, m3_clear); along(p0, j[2], 30, m3_head); }
        else         along(p0, -7, 0.5, m3_insert);
    }
}

// ---------- segment ----------
ext = 3.4;                                        // sector reaches past the joint line into the overlap
leg_boss_a = ang(42, 285);
module channel_cut(blocks) {
    difference() {
        sector(seg_a + 2*ext + 2) channel2d();
        for (bk = blocks) rotate(bk[0]) wedge(bk[1]);
    }
}
module segment(leg_s=0) {
    blocks = concat([[-seg_a/2, jw_a], [seg_a/2, jw_a]],
                    leg_s != 0 ? [[leg_s*leg_off, leg_boss_a]] : []);
    difference() {
        intersection() {
            sector(seg_a + 2*ext) hull2d();
            rotate(-seg_a/2) scarf_keep(+1);
            rotate( seg_a/2) scarf_keep(-1);
        }
        sector(seg_a + 2*ext + 2) chamber2d();
        channel_cut(blocks);
        rotate(-seg_a/2) joint_cut(+1);
        rotate( seg_a/2) joint_cut(-1);
        if (leg_s != 0) rotate(leg_s*leg_off) {
            for (y=[-10, 10]) translate([291, y, zb - 1]) cylinder(d=m4_insert, h=9);   // leg screws (M4 inserts)
            // LED wires: from the LED chamber straight back through the leg boss and out of the
            // ring's back face between the two leg screws, into the hole in the top of the leg
            p0 = bp(L/2, cham_n + 0.5); p1 = bp(L/2, wall_n - 2);
            hull() { translate([p0[0], 0, p0[1]]) sphere(d=4.5, $fn=16); translate([p1[0], 0, p1[1]]) sphere(d=4.5, $fn=16); }
            hull() { translate([p1[0], 0, p1[1]]) sphere(d=4.5, $fn=16); translate([leg_scr_r, 0, zb - 1]) cylinder(d=5, h=1); }
        }
    }
}

// ---------- diffuser (8 pieces, joints offset from the ring joints) ----------
module diffuser() { sector(seg_a - 0.3) diffuser2d(); }

// ---------- camera leg (leg-local frame: x radial, y across, z height) ----------
cam_z   = face + cam_h;
cam_t   = atan(cam_h / cam_r);                    // aims at the bull
T_lens  = [cam_r, 0, cam_z];
P_pcb   = T_lens + lens_len * [cos(cam_t), 0, sin(cam_t)];
module pcb_frame() { translate(P_pcb) rotate([0, -cam_t, 0]) children(); }   // +x = away from the board
tun_y   = pcb_w/2 + 0.35;
tun_sag = 0.6;                                    // extra room on the side that prints as a bridge (+y)
tun_z0  = cam_z + lens_len*sin(cam_t) - 16.5;     // straight access tunnel from the back of the leg
tun_z1  = tun_z0 + 33.7;
leg_scr_r = 291;
P4 = [
    [Rb + clamp_gap,      4],
    [Rb + clamp_gap + 22, 4],
    [Rout - 1,            44],
    [Rout - 1,            zb - 0.2],
    [Rin + bev_run,       zb - 0.2],
    [cam_r - 6,           zb - 7.2],              // top slopes away under the LED face (less shadow)
    [cam_r - 6,           face + 10],
    [Rb + 6,              face + lip],
    [Rb - lip,            face + lip],
    [Rb - lip,            face],
    [Rb + clamp_gap,      face]
];
clamp_z = face / 2;
module leg() {
    difference() {
        union() {
            difference() {
                rotate([90,0,0]) linear_extrude(leg_w, center=true) polygon(P4);
                // camera access tunnel (camera slides in from the back of the leg)
                intersection() {
                    translate([cam_r - 20, -tun_y, tun_z0]) cube([60, 2*tun_y + tun_sag, tun_z1 - tun_z0]);
                    pcb_frame() translate([-2, -50, -50]) cube([100, 100, 100]);
                }
            }
            // 4 standoffs the camera board screws to
            pcb_frame() for (y=[-1,1], z=[-1,1]) translate([-2.05, y*hole_sp/2, z*hole_sp/2])
                rotate([0, 90, 0]) cylinder(d=6, h=2.05);
        }
        pcb_frame() {
            for (y=[-1,1], z=[-1,1]) translate([-8, y*hole_sp/2, z*hole_sp/2]) rotate([0, 90, 0]) cylinder(d=1.7, h=8.5);  // M2 self-tap
            translate([-9, -holder_w/2, -holder_h/2]) cube([9.1, holder_w, holder_h]);      // lens holder + ears
            rotate([0, -90, 0]) cylinder(d=15.5, h=40);                                     // lens barrel (focus ring turns)
            hull() {                                                                         // view opening: 100 deg lens
                translate([-lens_len, -7.75, -7.75]) cube([0.01, 15.5, 15.5]);                    // (~92 x 60 deg on 16:9)
                translate([-lens_len - 7, -(7.75 + 7*tan(48)), -(7.75 + 7*tan(34))])
                    cube([0.01, 2*(7.75 + 7*tan(48)), 2*(7.75 + 7*tan(34))]);
            }
        }
        // M6 clamp screw + captive nut (slides in from the side)
        translate([Rb + clamp_gap - 1, 0, clamp_z]) rotate([0, 90, 0]) cylinder(d=m6, h=60);
        translate([Rb + clamp_gap + 11 - m6_nut_t/2, 0, clamp_z]) hull() {
            rotate([0, 90, 0]) cylinder(d=(m6_af + 0.4)/cos(30), h=m6_nut_t, $fn=6);
            translate([0, -40, 0]) rotate([0, 90, 0]) cylinder(d=(m6_af + 0.4)/cos(30), h=m6_nut_t, $fn=6);
        }
        translate([leg_scr_r, 0, tun_z1 - 1]) cylinder(d=6, h=20);     // LED wires down into the tunnel
        // ring screws: M4 x 12 up through the tunnel roof; screwdriver goes in from underneath
        for (y=[-10, 10]) {
            translate([leg_scr_r, y, tun_z1 - 1]) cylinder(d=m4_clear, h=20);
            translate([leg_scr_r, y, -1]) cylinder(d=8.5, h=tun_z0 + 2);
        }
    }
}
// back cover: plugs into the tunnel opening, notch for the USB cable
module cam_cover() {
    difference() {
        union() {
            translate([Rout - 1, -tun_y - 1.5, tun_z0 - 1.5]) cube([2, 2*tun_y + tun_sag + 3, tun_z1 - tun_z0 + 3]);
            translate([Rout - 4, -tun_y + 0.2, tun_z0 + 0.2]) cube([3.01, 2*tun_y + tun_sag - 0.4, tun_z1 - tun_z0 - 0.4]);
        }
        translate([Rout - 5, -4.5, tun_z0 - 2]) cube([10, 9, 6.5]);       // cable notch (bottom)
    }
}
module pad()  { difference() { union() { cylinder(d=20, h=3); cylinder(d=12, h=8); } translate([0,0,3]) cylinder(d=6.2, h=6); } }
module knob() {
    difference() {
        union() { cylinder(d=30, h=10, $fn=24); cylinder(d=16, h=14); }
        translate([0,0,-1]) cylinder(d=(m6_af + 0.3)/cos(30), h=5.2, $fn=6);
        translate([0,0,-1]) cylinder(d=m6, h=20);
    }
}


// ============================================================
//  STAND MOUNT (Winmau stand + any surround, no cutting)
//  hub   : sits between the stand's T-plate and the board; the board's
//          3 screws go through T-plate + hub into the board (screws 14 mm longer)
//  arms  : 4, bolt to the hub, run behind the board + surround
//  leg_s : rises OUTSIDE the surround and holds camera + ring exactly
//          where the clamp leg did (ring unchanged)
//  sled  : camera board rides on it into the leg; it is also the back cover
//  z = 0 is the back of the board.
// ============================================================
/* [Stand mount] */
hub_t      = 10;     // hub thickness (behind the board)
arm_d      = 26;     // arm depth past the hub: deeper = stiffer, there's free space behind the board
tp_holes   = [-70, 0, 70];   // stand T-plate holes (x, mm from the middle one = board centre)
tp_slot    = 3;      // +- slot length for T-plate hole tolerance
tp_hole_d  = 5.5;
sur_r      = 362;    // surround outer radius + gap (fits surrounds up to 720 mm across)
sur_t      = 42;     // surround thickness + gap (from the back of the board)
arm_w      = 40;
hub_r      = 135;    // hub arm length: the arm root sits on the back of the hub from lap_r0 to hub_r
lap_r0     = 95;
post_t     = 24;
legS_w     = 44;
post_r0    = sur_r + 2;  post_r1 = post_r0 + post_t;
legS_z0    = sur_t + 2;                     // underside of the top block (clears the surround)
arm_bolts  = [102, 130];   // 28 mm apart (hub kept small enough for the bed)
post_bolt_r = (post_r0 + post_r1) / 2;
leg_bolts = [[post_r0 + 6, 0], [post_r1 - 6, 0]];   // arm-to-leg bolts one behind the other: foot stays fin-width

module arm_plan(r0, r1) { translate([r0, -arm_w/2]) square([r1 - r0, arm_w]); }
module hub() {
    difference() {
        translate([0, 0, -hub_t]) union() {
            linear_extrude(hub_t) union() {
                circle(r=58);
                translate([-85, -16]) square([170, 32]);                 // bar over the T-plate holes
                for (a=legs) rotate(a) arm_plan(0, hub_r);
            }
        }
        for (x=tp_holes) hull() for (dx=[-tp_slot, tp_slot]) translate([x + dx, 0, -hub_t - 1]) cylinder(d=tp_hole_d, h=hub_t + 2);
        translate([0, 0, -1.5]) cylinder(d=10, h=2);                     // marks the board's centre hole
        for (p=ebox_bolts) translate([p[0], p[1], 0]) {                   // electronics box: M4 x 16 countersunk
            translate([0, 0, -hub_t - 1]) cylinder(d=m4_clear, h=hub_t + 2);   // from the front, before the board
            translate([0, 0, -2.3]) cylinder(d1=m4_clear, d2=8.6, h=2.31);
        }
        for (a=legs) rotate(a) for (r=arm_bolts) {                     // M4 x 30 countersunk from the front
            translate([r, 0, -hub_t - 1]) cylinder(d=m4_clear, h=hub_t + 2);
            translate([r, 0, -2.3]) cylinder(d1=m4_clear, d2=8.6, h=2.31);
        }
    }
}
module hub_plan() {
    circle(r=48);
    translate([-85, -16]) square([170, 32]);
    for (a=legs) rotate(a) arm_plan(0, hub_r);
}
module arm() {               // arm-local: x radial from the board centre
    // A plain bar 40 x 26: printed with 3 walls + 10 % infill it is a closed box, which is ~7x
    // stiffer in twist than an open T for about the same plastic. The root sits on the BACK of the
    // hub (r lap_r0..hub_r) and is bolted through both with 2 bolts 45 mm apart.
    difference() {
        union() {
            translate([lap_r0, -arm_w/2, -arm_d]) cube([hub_r - lap_r0 + 0.01, arm_w, arm_d - hub_t]);   // behind the hub
            translate([hub_r, -arm_w/2, -arm_d]) cube([post_r1 - hub_r, arm_w, arm_d]);                     // behind board + surround
        }
        for (r=arm_bolts) {
            translate([r, 0, -arm_d - 1]) cylinder(d=m4_clear, h=arm_d + 2);
            translate([r, 0, -arm_d - 0.01]) cylinder(d=8.1/cos(30), h=4, $fn=6);       // M4 nut (back)
        }
        for (p=leg_bolts) {                                               // leg bolts (M4 x 16), heads at the back
            translate([p[0], p[1], -arm_d - 1]) cylinder(d=m4_clear, h=arm_d + 2);
            translate([p[0], p[1], -arm_d - 0.01]) cylinder(d=8.5, h=arm_d - 8);
        }
        // past the surround the arm narrows to the fin's width and ends in a rounded tip
        translate([0, 0, -arm_d - 1]) linear_extrude(arm_d + 2) difference() {
            translate([280, -50]) square([200, 100]);
            hull() {                                                       // taper, finished behind the surround
                translate([280, -arm_w/2]) square([1, arm_w]);
                translate([sur_r - 16, -fin_w/2]) square([1, fin_w]);
            }
            hull() {                                                       // then fin-width to a rounded tip
                translate([sur_r - 16, -fin_w/2]) square([1, fin_w]);
                translate([post_r1 - fin_w/2, 0]) circle(d=fin_w);
            }
        }
    }
}
// ---------- sculpted stand leg ("fin") ----------
// A camera pod tucked under the ring (hidden from the oche by the ring itself) and a slim
// 18 mm fin that sweeps out from behind the ring, over the surround and down its outside edge.
// The camera board screws onto 4 posts on the leg's flat front face (see cam_posts).
fin_w  = 18;   fin_rr = 3;      // fin width, edge rounding
ring_lift = 4;  zbl = zb + ring_lift;   // stand mount: ring sits 4 mm further out, room for a camera cover above the posts
pod_w  = 44;   pod_r0 = cam_r - lens_max + lens_len - 6;  pod_r1 = Rout;
pod_z0 = legS_z0;               // pod + fin underside, just above the surround
module fin2d() {
    sw = 31;                                              // 45 deg sweep over the outer edge (prints
    offset(r=10) offset(delta=-10) polygon([              //  upside-down without supports)
        [pod_r1 - 8,  pod_z0], [pod_r1 - 8, zbl - 0.2], [post_r1 - sw, zbl - 0.2],
        [post_r1, zbl - 0.2 - sw],
        [post_r1, 0], [post_r0, 0], [post_r0, pod_z0 - 4], [post_r0 - 4, pod_z0]]);
}
module fin_solid() {
    intersection() {
        minkowski() {
            rotate([90,0,0]) linear_extrude(fin_w - 2*fin_rr, center=true) offset(delta=-fin_rr) fin2d();
            sphere(r=fin_rr, $fn=12);
        }
        translate([0, -50, 0]) cube([500, 100, zbl - 0.2]);
    }
}
module pod_solid() {
    intersection() {
        minkowski() {
            translate([pod_r0 + 8, -pod_w/2 + 8, pod_z0 + 8]) cube([pod_r1 - pod_r0 - 16, pod_w - 16, 60]);
            sphere(r=8, $fn=24);
        }
        // flat top under the ring's back face, 45 deg away under the LED face (no shadow, prints clean)
        // 45 deg all the way down at the front (was a flat shelf, which printed upside down was a
        // floating ledge once the pod got longer for the real lens)
        rotate([90,0,0]) linear_extrude(100, center=true) polygon([[200, 0], [400, 0], [400, zbl - 0.2],
            [Rin + bev_run, zbl - 0.2], [Rin + bev_run - (zbl - 0.2), 0]]);
    }
}
// slice of a rounded bar: at radius r, width w, from z0 to z1, corner radius cr
module rslice(r, w, z0, z1, cr) {
    translate([r, 0, 0]) rotate([0, 90, 0]) linear_extrude(0.01)
        offset(r=cr) offset(delta=-cr) translate([-z1, -w/2]) square([z1 - z0, w]);
}
function blend_w(t, w0, w1) = w1 + (w0 - w1) * (1 + cos(180*t)) / 2;
module pod_blend() {                 // pod (44 wide) flows into the fin (18 wide) on a smooth curve
    // ends EXACTLY at the fin's real width: the fin is rounded with a 12-sided sphere, whose widest
    // ring sits at cos(15 deg) of the radius - ending at the nominal width left a 0.1 mm step (a line)
    fin_true_w = fin_w - 2*fin_rr*(1 - cos(15));
    n = 24;  r0 = pod_r1 - 12;  r1 = pod_r1 + 38;
    for (i=[0:n-1]) hull() for (k=[i, i+1]) {
        t = k / n;
        rslice(r0 + (r1 - r0)*t, blend_w(t, pod_w - 0.6, fin_true_w), pod_z0 + 0.3, zbl - 0.2, 3 + 5*(1 - t));
    }
}
module foot() {
    n = 8;                              // fin flares smoothly into the foot
    for (i=[0:n-1]) hull() for (k=[i, i+1]) {
        t = k / n;  z = 30 - 30*t;  w = blend_w(1 - t, 40, fin_w);
        translate([0, 0, z]) linear_extrude(0.01) offset(r=5) offset(delta=-5)
            translate([post_r0, -w/2]) square([post_r1 - post_r0, w]);
    }
    hull() for (r=[post_r0 + 5, post_r1 - 5], y=[-15, 15]) translate([r, y, 0]) cylinder(r=5, h=0.01, $fn=24);
}
module foot_old() {
    hull() {
        for (r=[post_r0 + 3, post_r1 - 3], y=[-17, 17]) translate([r, y, 0]) cylinder(r=3, h=8, $fn=24);
        translate([post_r0 + 1, -fin_w/2 + 1, 24]) cube([post_r1 - post_r0 - 2, fin_w - 2, 1]);
    }
}
// Camera board rotated 90 deg so its connector points SIDEWAYS (-y) instead of down into the surround
// (set rotate: 90 for these cameras in config.yaml). The whole camera - lens on - drops in from the
// top; the slots are hidden under the ring.
fc = 1.2;  bc = 2.4;            // component height on the front / back of the camera board
con_w = 11;  con_out = 5.5;     // connector: width along the board edge, height off the back
plug = 13;                      // plug + cable bend beyond the board edge
module cam_body(c=0) {          // the camera as a solid (c = clearance all round)
    translate([-fc - c, -16.25 - c, -16.25 - c]) cube([fc + 1.6 + bc + 2*c, 32.5 + 2*c, 32.5 + 2*c]);    // board + parts
    translate([-holder_d - c, -holder_w/2 - c, -holder_h/2 - c]) cube([holder_d + 2*c, holder_w + 2*c, holder_h + 2*c]);
    translate([-lens_max - 0.5, 0, 0]) rotate([0, 90, 0]) cylinder(d=15.5 + 2*c, h=lens_max - holder_d + 1);  // lens, any setting
    translate([1.6 - c, -16.25 - plug - c, -con_w/2 - 1 - c]) cube([con_out + 2*c, plug + 4 + 2*c, con_w + 2 + 2*c]);  // connector + plug
}
// The camera's pieces, each with the lowest point of its (5 deg tilted) underside: [x0, z0] in the
// camera frame. The pocket is each piece's footprint taken straight up from a FLAT floor at that lowest
// point - a flat floor prints as a clean bridge upside down (a 5 deg slope printed as a floating ledge).
function floor_z(x0, z0) = P_pcb[2] + x0*sin(cam_t) + z0*cos(cam_t);
module cam_piece(k, c) {
    if (k == 0) translate([-fc - c, -16.25 - c, -16.25 - c]) cube([fc + 1.6 + bc + 2*c, 32.5 + 2*c, 32.5 + 2*c]);
    if (k == 1) translate([-holder_d - c, -holder_w/2 - c, -holder_h/2 - c]) cube([holder_d + 2*c, holder_w + 2*c, holder_h + 2*c]);
    if (k == 2) translate([-lens_max - 0.5, 0, 0]) rotate([0, 90, 0]) cylinder(d=15.5 + 2*c, h=lens_max - holder_d + 1);
    if (k == 3) translate([1.6 - c, -16.25 - plug - c, -con_w/2 - 1 - c]) cube([con_out + 2*c, plug + 4 + 2*c, con_w + 2 + 2*c]);
}
function piece_floor(k, c) =
    k == 0 ? floor_z(-fc - c, -16.25 - c) :
    k == 1 ? floor_z(-holder_d - c, -holder_h/2 - c) :
    k == 2 ? floor_z(-lens_max - 0.5, -(15.5/2 + c)) :
             floor_z(1.6 - c, -con_w/2 - 1 - c);
module cam_columns(c, top=200) {      // every piece swept straight up from ONE flat floor (the board's
    f = piece_floor(0, c);             //  lowest corner): one level ceiling = one clean bridge upside down
    translate([0, 0, f]) linear_extrude(top - f) union() for (k=[0:3]) projection() pcb_frame() cam_piece(k, c);
}
module cam_slots() {
    cam_columns(0.35);
    // cable from the plug down through the floor to the groove under the fin
    pcb_frame() translate([1.6 - 0.35, -16.25 - plug - 0.35, -60]) cube([con_out + 0.7, 8, 60]);
}
gw = 7;  gd = 8;                // cable groove (USB + LED wires), on the hidden underside of the fin
module cable_groove() {
    translate([P_pcb[0] + 1, -gw/2, pod_z0 - 10]) cube([post_r0 + gd - P_pcb[0] - 1, gw, 10 + gd]);  // along the underside
    translate([post_r0 - 5, -gw/2, 12]) cube([gd + 5, gw, pod_z0 + gd - 12]);              // down the inside of the fin
    translate([post_r0 - 5, -40, 12]) cube([gd + 5, 40, 8]);                               // out of the side, onto the arm
}
module tip_plan() {          // plan outline shared by the arm tip and the fin's foot
    translate([150, -100]) square([sur_r - 16 - 150, 200]);
    hull() {
        translate([sur_r - 16, -fin_w/2]) square([1, fin_w]);
        translate([post_r1 - fin_w/2, 0]) circle(d=fin_w, $fn=48);
    }
}

// ---------- camera: leg ends in a FLAT face; the front mount (hood) carries the shape ----------
// The leg stops at a flat face just behind the camera. 4 posts stick out of it (M2 heat-set inserts),
// the camera board sits on them, and the hood - the whole front of the pod - goes over the camera and
// screws through the board into the posts (4 x M2 x 8). Change the hood without reprinting the leg.
face_x   = 285.5;               // the leg's flat front face (radius)
post_d   = 6;   m2_insert = 3.0;  m2_clear = 2.4;  m2_head = 4.4;  boss_t = 4;
holes4   = [for (y=[-1,1], z=[-1,1]) [y*hole_sp/2, z*hole_sp/2]];
module pod_tucked() {
    difference() {          // pod corners tucked in behind the ring's inner edge
        pod_solid();
        for (sy=[-1,1]) hull() { translate([0, sy*15, -1]) cube([Rin + 1, sy*40, 200]);
                                 translate([0, sy*40, -1]) cube([Rin + 12, sy*1, 200]); }
    }
}
module front_half(keep_front=true, gap=0) {
    if (keep_front) translate([0, -100, -1]) cube([face_x - gap, 200, 200]);
    else translate([face_x, -100, -1]) cube([200, 200, 200]);
}
module cam_posts(cut=false) {   // from the board's back out through the leg face
    pcb_frame() for (h=holes4) translate([1.6, h[0], h[1]]) rotate([0, 90, 0])
        if (cut) translate([0, 0, -0.01]) cylinder(d=m2_insert, h=4);
        else cylinder(d=post_d, h=14);
}
module view_cut() {
    pcb_frame() {
        rotate([0, -90, 0]) cylinder(d=16.5, h=40);
        hull() {                                       // 100 deg view opening, clear for any lens setting
            fl = lens_max - lens_min + 12;
            translate([-lens_min, -8.5, -8.5]) cube([0.01, 17, 17]);
            translate([-lens_min - fl, -(8.5 + fl*tan(50)), -(8.5 + fl*tan(47))])
                cube([0.01, 2*(8.5 + fl*tan(50)), 8.5 + fl*tan(47) + 8.5 + fl*tan(36)]);
        }
    }
}
// DRAFT only, not for printing yet: a front cover to finalise once the real cameras are here.
// The leg face leaves 5.7 mm all round the board (44 mm face, 32.5 mm board) for its walls.
module cam_hood() {               // in leg coordinates, like leg_fin()
    difference() {
        intersection() { pod_tucked(); front_half(true, 0.15); }
        pcb_frame() {
            difference() {        // board + its front parts; 4 bosses press on the corner pads
                translate([-1.6, -16.65, -16.65]) cube([1.6 + 1.6 + 0.4, 33.3, 33.3]);
                for (h=holes4) translate([-boss_t, h[0], h[1]]) rotate([0, 90, 0]) cylinder(d=post_d, h=boss_t);
            }
            translate([1.6, -16.65, -16.65]) cube([bc + 0.6, 33.3, 33.3]);          // parts on the back
            for (h=holes4) translate([1.6, h[0], h[1]]) rotate([0, 90, 0]) cylinder(d=post_d + 0.8, h=20);  // posts
            translate([1.6, -con_w/2 - 0.5, -16.65]) cube([20, con_w + 1, 6]);      // connector
            translate([1.0, -5, -40]) cube([20, 10, 40 - 16.25 + 1]);               // plug + cable, straight down
            translate([-holder_d - 0.3, -holder_w/2 - 0.3, -holder_h/2 - 0.3]) cube([holder_d + 0.4, holder_w + 0.6, holder_h + 0.6]);  // lens holder
            for (h=holes4) translate([-50, h[0], h[1]]) rotate([0, 90, 0]) {
                cylinder(d=m2_clear, h=51);                       // M2 x 8: head sits on the boss
                cylinder(d=m2_head, h=50 - boss_t);               // tunnel for the screwdriver
            }
        }
        view_cut();
        cable_groove();
    }
}
module leg_fin() {
    difference() {
        union() {
            intersection() {     // the fin's outer end follows the arm tip exactly (same rounded outline)
                union() {
                    intersection() { pod_tucked(); front_half(false); }   // flat face at the front
                    pod_blend(); fin_solid();
                    translate([post_r0, -fin_w/2, 0]) cube([post_t, fin_w, 14]);   // flat foot: sits square on the arm
                }
                translate([0, 0, -1]) linear_extrude(200) tip_plan();
            }
            intersection() { cam_posts(); translate([0, -50, pod_z0]) cube([400, 100, zbl - 0.2 - pod_z0]); }
        }
        cam_posts(cut=true);
        for (y=[-10, 10]) {                     // ring screws: M4 x 16 from underneath (fit legs to the ring on the bench)
            translate([leg_scr_r, y, zbl - 9]) cylinder(d=m4_clear, h=20);
            translate([leg_scr_r, y, pod_z0 - 10]) cylinder(d=8.5, h=(zbl - 9) - (pod_z0 - 10));
        }
        translate([leg_scr_r, 0, pod_z0 - 5]) cylinder(d=6, h=50);     // LED wires down from the ring
        cable_groove();
        for (p=leg_bolts) translate([p[0], p[1], -0.01]) cylinder(d=m4_insert, h=9);   // arm bolts (M4 inserts)
    }
}
// plug that fills the slots above the camera: holds it down, closes the slots, the ring sits on it.
// Crush ribs on its sides make it a push fit, so it stays in before the ring goes on.
module cam_key() {
    kz = 16.25 + 0.35;           // sits on the top edge of the camera board (the space above the lens,
    intersection() {             //  holder and plug stays empty - only the board needs holding down)
        cam_columns(0.2);
        pcb_frame() translate([-60, -60, kz]) cube([120, 120, 100]);
        translate([0, -60, 0]) cube([400, 120, zb - 0.4]);
    }
    intersection() {             // crush ribs, 0.25 mm proud, on the front and back faces
        pcb_frame() {
            translate([-lens_max - 0.5 - 0.25, -1, -100]) cube([0.75, 2, 300]);
            translate([1.6 + con_out + 0.2 - 0.5, -16.25 - plug/2 - 1, -100]) cube([0.75, 2, 300]);
        }
        cam_columns(0.45);
        pcb_frame() translate([-60, -60, kz + 1]) cube([120, 120, 100]);
        translate([0, -60, 0]) cube([400, 120, zb - 3]);
    }
}

// ---------- electronics box ----------
// Behind the board at 12 o'clock, between the two upper arms (hidden from the front by the board).
// Holds the ESP32-C3, MOSFET module, 24 V -> 5 V converter, DC socket; room for a Pi 5 later
// (standoffs for its 58 x 49 holes). Lid on the back, 5 screws, vents over the Pi.
ebox_d = 36;  ebox_wall = 2.5;
ebox_z0 = -hub_t - ebox_d;                                   // back rim (lid side)
ebox_bolts = [[-15, 50], [15, 50]];
lid_scr = [[-63, 140], [63, 140], [-63, 84], [63, 84], [0, 54]];
pi_holes = [for (x=[-29, 29], y=[80.5, 129.5]) [x, y]];
module ebox2d() { offset(r=8) offset(delta=-8) polygon([[-25, 44], [25, 44], [75, 73], [75, 150], [-75, 150], [-75, 73]]); }
module ebox() {
    difference() {
        union() {
            translate([0, 0, ebox_z0]) difference() {
                linear_extrude(ebox_d) ebox2d();
                translate([0, 0, -1]) linear_extrude(ebox_d - ebox_wall + 1) offset(delta=-ebox_wall) ebox2d();
            }
            intersection() {
                translate([0, 0, ebox_z0]) linear_extrude(ebox_d) ebox2d();
                union() {
                    for (p=ebox_bolts) translate([p[0], p[1], -hub_t - 12]) cylinder(d=11, h=12);
                    for (p=lid_scr) translate([p[0], p[1], ebox_z0]) cylinder(d=8, h=ebox_d);
                    for (p=pi_holes) translate([p[0], p[1], -hub_t - ebox_wall - 5]) cylinder(d=6.5, h=5.01);
                }
            }
        }
        for (p=ebox_bolts) translate([p[0], p[1], -hub_t - 9]) cylinder(d=m4_insert, h=9.01);
        for (p=lid_scr)    translate([p[0], p[1], ebox_z0 - 0.01]) cylinder(d=m3_insert, h=7);
        for (p=pi_holes)   translate([p[0], p[1], -hub_t - ebox_wall - 5.01]) cylinder(d=3.6, h=4.5);  // M2.5 inserts
        // cable notches open at the lid edge (lay the cables in, the lid closes them)
        translate([-18, 30, ebox_z0 - 1]) cube([36, 20, 15]);                                   // from the lower arms
        for (s=[-1, 1]) translate([s*50, 58.5, ebox_z0 - 1]) rotate(s*31) translate([-15, -8, 0]) cube([30, 16, 15]);  // upper arms
        translate([-52, 140, ebox_z0 - 1]) cube([24, 20, 11]);                                  // USB lead out to the laptop / screen
        translate([40, 140, ebox_z0 + 18]) rotate([-90, 0, 0]) cylinder(d=12.2, h=20);          // 5.5 x 2.1 panel DC socket (24 V in)
    }
}
module ebox_lid() {      // lid-local: outer face at z = 0, lip towards +z (into the box)
    difference() {
        union() {
            linear_extrude(2.5) ebox2d();
            translate([0, 0, 2.5]) linear_extrude(3) difference() {
                offset(delta=-ebox_wall - 0.3) ebox2d(); offset(delta=-ebox_wall - 2.3) ebox2d(); }
        }
        for (p=lid_scr) translate([p[0], p[1], -1]) cylinder(d=m3_clear, h=10);
        for (i=[0:7]) translate([-45 + i*12.85 - 2, 85, -1]) cube([4, 42, 10]);                  // vents over the Pi
    }
}
module stand_mount() {
    color(c_leg) hub();
    // electronics box (ebox / ebox_lid) not fitted yet: its space at 12 o'clock and the 2 hub bolts are kept
    for (a=legs) rotate(a) { color(c_leg) arm(); color(c_leg) leg_fin(); }
}
module surround_model() { color([0.08,0.08,0.09]) difference() { cylinder(r=355, h=40, $fn=180); translate([0,0,-1]) cylinder(r=Rb + 1, h=42, $fn=180); } }

// ---------- assembly ----------
c_halo = [0.17, 0.17, 0.19];  c_leg = [0.12, 0.12, 0.13];  c_diff = [1.0, 0.95, 0.80];
legs = [30, 150, 210, 330];
function seg_leg_s(i) = (i % 2 == 0) ? 0 : (((i - 1) / 2) % 2 == 0 ? -1 : 1);
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
mount = "stand";    // stand | clamp
module assembly(show_board=true, show_surround=true) {
    if (show_board) board_model();
    if (show_surround && mount == "stand") surround_model();
    lift = (mount == "stand") ? ring_lift : 0;
    translate([0, 0, lift]) for (i=[0:segments-1]) rotate(i*seg_a) color(c_halo) segment(seg_leg_s(i));
    if (mount == "stand") stand_mount();
    else for (a=legs) rotate(a) { color(c_leg) leg(); color(c_leg) cam_cover(); }
    translate([0, 0, lift]) for (i=[0:segments-1]) rotate(i*seg_a + seg_a/2) color(c_diff) diffuser();
}
module front_down() { translate([0,0,zf]) rotate([180,0,0]) children(); }
module side_down()  { rotate([90,0,0]) children(); }

// ---- print orientation: every STL comes out ready to drop on the plate ----
if (part == "assembly")  assembly();
if (part == "seg_plain") front_down() segment(0);
if (part == "seg_leg_a") front_down() segment(-1);   // legs at 30 / 210 deg (2 and 8 o'clock)
if (part == "seg_leg_b") front_down() segment(1);    // legs at 150 / 330 deg (10 and 4 o'clock)
if (part == "diffuser")  diffuser();
if (part == "leg")       translate([0, 0, leg_w/2]) side_down() leg();   // +y side up: the tunnel roof bridges ~29 mm
if (part == "cam_cover") rotate([0, 90, 0]) translate([-(Rout + 1), 0, 0]) cam_cover();
if (part == "pad")       pad();
// stand mount parts
if (part == "hub")       translate([0, 0, hub_t]) hub();                       // flat, back face down
if (part == "arm")       rotate(45) translate([-(lap_r0 + post_r1)/2, 0, arm_d]) arm();   // back face down, diagonal on the bed
if (part == "leg_fin")   translate([0, 0, zbl - 0.2]) rotate([180, 0, 0]) leg_fin();   // upside down: pod top + fin top on the bed
if (part == "ebox")      translate([0, 0, -hub_t]) rotate([180, 0, 0]) ebox();     // floor on the bed
if (part == "ebox_lid")  ebox_lid();
if (part == "knob")      knob();
