# Hardware

## halo_v4 – light ring + 4 camera legs (3D printed, PLA)  ← current

`halo_v4/dart_halo_v4.scad` is the parametric source (set `part`, F6, export STL).
Every STL in `halo_v4/stl/` is **already in print orientation** – drop it on the plate as-is.

What changed from v3:
- The ring is **only the light**: no camera windows, so the LED strip and diffuser run all the way round.
- Segments join with a **45° scarf** (sloped overlap) and 2 M3 screws per joint, square to the slope –
  no splice plates. The slope lines the faces up and prints without supports.
- **Cameras live in the legs.** Each leg clamps the board edge (M6 + knob) and holds a camera 24 mm
  above the board face, so the whole thing moves with the board – wall or dartboard stand.

### What to print

| File | Qty | Plate | Supports | Notes |
|---|---|---|---|---|
| `seg_plain.stl` | 4 | front face down | none | 12, 3, 6, 9 o'clock |
| `seg_leg_a.stl` | 2 | front face down | none | leg at 2 / 8 o'clock |
| `seg_leg_b.stl` | 2 | front face down | none | leg at 4 / 10 o'clock |
| `leg.stl` | 4 | on its side (as saved) | none | camera + board clamp; the camera tunnel's top wall is a ~29 mm bridge – fine on a P2S, and there's 0.6 mm extra room so a little sag can't catch the camera board |
| `cam_cover.stl` | 4 | flat | none | plugs into the back of each leg, notch for the USB cable |
| `diffuser.stl` | 8 | standing on its edge | none, **add a brim** | translucent PLA/PETG |
| `knob.stl` | 4 | flat | none | M6 bolt head sits in it |
| `pad.stl` | 4 | flat | none | clamp pad – stick a 20 mm rubber bumper on it |

Settings (PLA, 0.4 nozzle): 0.2 mm layers, **4 walls**, 15–20 % gyroid. Segments are 247 mm long:
one per plate.

**Test print first:** 2× segments that meet (e.g. seg_plain + seg_leg_a) + 1× leg + 1× cover –
check the scarf joint pulls up flush, the camera board fits the leg and the view covers the board.

### Hardware
- 16× M3 heat-set inserts (press them in **square to the sloped joint face**)
- 8× M3×16 + 8× M3×10 cap screws (joints: the inner screw is the long one)
- 8× M4 heat-set inserts + 8× M4×12 cap screws (legs to ring, screwdriver in from under the leg)
- 4× M6×50 hex bolts + 4× M6 nuts (clamps), 4× 20 mm rubber bumpers
- 16× M2×5 self-tapping screws (camera boards)
- Cameras: 4× OV9732 720p 100° USB (32 × 32 mm board, 28 mm holes). **Measure yours:** `lens_len`
  (board front face to lens tip, default 12 mm) and the lens-holder width (`holder_w`, 24 mm) are
  parameters at the top of the .scad.
- LEDs: 24 V 10 mm COB strip, one continuous piece, ~1.65 m

### Stand mount (Winmau stand + any surround, no cutting) ← use this on a stand

The ring and segments are the same. Instead of the board-clamp legs, print:

| File | Qty | Plate | Supports | Notes |
|---|---|---|---|---|
| `hub.stl` | 1 | flat | none | goes between the stand's T-plate and the board (10 mm) |
| `arm.stl` | 4 | back face down, diagonal on the bed (as saved) | none | solid bar – prints as a closed box |
| `leg_fin.stl` | 4 | **upside down, as saved** | none | camera pod hidden under the ring + slim 18 mm fin over the surround |
| `cam_key.stl` | 4 | flat | none | sits on top of the camera board; the ring presses it down |

Print the stand parts with **3 walls, 10 % gyroid**: hub ~83 g, arms ~70 g each, fins ~56 g each –
about 590 g for the set. Fits surrounds up to **720 mm across and 40 mm thick** (`sur_r`, `sur_t`).

**Strength** (calculated for printed PLA, 50 N ≈ 5 kg leaning on the ring next to a fin): fins ≤ 3.6 MPa,
arms 8.6 MPa at the hub (layer bond ~15–20 MPa), hub bolts ~460 N each; a firm 25 N sideways nudge moves the
ring ~1 mm and it springs back.

**Assembly**
1. Hub on the T-plate. The board's 3 screws go through the T-plate **and** the hub into the board:
   use screws **10 mm longer** than the ones in the Winmau bag.
2. Arms onto the **back** of the hub: 8× M4 × 30 countersunk from the front of the hub, nuts in the traps on
   the back of the arms (do this before the board goes on).
3. Camera: slide the camera board **down into the pod from the top** (lens towards the board centre), drop the
   `cam_key` on top of it, plug the USB lead in and lay it in the groove under the fin.
4. Fins to the ring on the bench (ring upside down): 8× M4 × 16 button head, up through the pod into the ring's
   inserts. The ring holds the keys (and so the cameras) in place.
5. Ring + fins onto the arm tips: 8× M4 × 16 from behind into the fins' inserts (2 per fin, one behind the other).

**Cables:** USB + LED wires run in the groove on the hidden underside of each fin, down its inside face, out of
the side just above the arm, then along the back of the arm (cable ties) to the middle.

**Electronics:** the space behind the board at 12 o'clock, between the two upper arms (about 150 × 105 × 36 mm),
is kept clear for an electronics box, and the hub already has its 2 mounting holes. `ebox` / `ebox_lid` in the
.scad are a first draft – not part of the print list yet.

**Extra hardware:** 8× M4 heat-set inserts (fins), 8× M4 × 30 countersunk + 8× M4 nuts (arms to hub),
8× M4 × 16 button head (fins to ring), 8× M4 × 16 cap (arms to fins), 3 longer wood screws for the board.

### Layout
600 mm across, 110 mm off the wall, fits a 451 mm bristle board. Legs + cameras at 2, 4, 8 and
10 o'clock (nothing above the 20 or below the 3). Lens 262 mm from the bull, 24 mm above the
board face, aimed at the bull. LED wires leave the ring next to a leg into the cable channel;
camera cables run along the open slot in the back of the ring.

---

## halo_v3 (previous version – cameras in pods inside the ring)

`dart_halo_v3.scad` is the parametric source (set `part`, F6, export STL).
Every STL in `stl/` is **already in print orientation** – drop it on the plate as-is
(don't use Bambu Studio's auto-orient).

### What to print

| File | Qty | Plate it goes on | Supports | Notes |
|---|---|---|---|---|
| `seg_plain.stl` | 4 | front face down | none | ring segments at 12, 3, 6, 9 o'clock |
| `seg_cam_a.stl` | 2 | front face down | none | camera + leg segments (45° and 225°) |
| `seg_cam_b.stl` | 2 | front face down | none | mirror version (135° and 315°) |
| `pod.stl` | 4 | front face down | **yes – tree, build plate only** | camera housing; supports only under the 2 tabs |
| `leg.stl` | 4 | on its side, pocket up | none | board clamps |
| `diffuser.stl` | 8 | standing on its edge | none, **add a brim** | translucent / natural PLA; slides in from a camera opening, a few dots of clear glue hold it |
| `splice.stl` | 8 | flat, counterbores up | none | joins the segments (back of ring); 6 mm thick, heads sit flush |
| `knob.stl` | 4 | flat | none | thumb knob for the M6 bolt |
| `pad.stl` | 4 | flat | none | clamp pad – stick a 20 mm rubber bumper on it |

Settings (PLA, 0.4 nozzle): 0.2 mm layers, **4 walls** (heat-set inserts need them), 15–20 % gyroid.
Diffusers: translucent PLA, 0.2 mm layers.

**Test print first:** 1× seg_cam_a + 1× pod + 1× diffuser (+ 1× leg) – check the camera fits, its view
covers the whole board and the LED strip sits nicely, before printing the rest.

### Hardware
- 40× M3 heat-set inserts, 32× M3×8 (splices), 8× M3×8 (pods)
- 8× M4 heat-set inserts, 8× M4×20 (legs)
- 4× M6×40 hex bolts + 4× M6 nuts (clamps), 4× 20 mm self-adhesive rubber bumpers
- 16× M2×5 self-tapping screws (camera boards)
- Cameras: OV9732 720p 100° USB modules (32 × 32 mm board, 28 mm holes)
- LEDs: 24 V 10 mm COB strip, 4000 K, ~1.6 m

### Layout
600 mm across, 110 mm off the wall, fits a 451 mm bristle board. Legs at 2, 4, 8 and 10 o'clock
(nothing above the 20 or below the 3); cameras on the diagonals. The ring's outer front edge is a
45° chamfer and the back is square, so segments print front-face-down with nothing floating.
The front plate and outer rim run unbroken past each camera; the pod slides in from behind.
