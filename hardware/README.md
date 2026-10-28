# Hardware

## halo_v3 – camera + LED light ring (3D printed, PLA)
- `dart_halo_v3.scad` – parametric OpenSCAD source (set `part`, F6, export STL)
- `stl/` – print-ready parts: 4× seg_plain, 2× seg_cam_a, 2× seg_cam_b, 4× pod, 4× leg,
  8× diffuser (translucent PLA), 8× splice, 4× knob, 4× pad (+ 20 mm stick-on rubber bumper)
- Fits a 451 mm bristle board; 600 mm across, 110 mm off the wall
- Cameras: OV9732 720p 100° USB modules (32 × 32 mm board, 28 mm holes)
- LEDs: 24 V 10 mm COB strip, 4000 K, ~1.6 m
- Hardware: M3 + M4 heat-set inserts, M3×8 / M4×20 screws, 4× M6×40 + nuts, M2×5 self-tappers

Legs sit at 2, 4, 8 and 10 o'clock (nothing above the 20); cameras on the diagonals.
