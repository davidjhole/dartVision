# Hardware

## halo_v3 – camera + LED light ring (3D printed, PLA)

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
| `splice.stl` | 8 | flat | none | joins the segments (back of ring) |
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
