# Changelog

Newest first. The update checker shows the section for the version you're updating to.

## Unreleased
- Cameras are remembered by their USB port (macOS: AVFoundation id, Linux: /dev/v4l/by-path), so
  renumbering no longer swaps cameras or picks up the laptop webcam. `setup` shows camera names and
  skips the computer's own camera. macOS needs `pip install -r requirements.txt` again (pyobjc).
- Cameras that stop sending pictures (e.g. a USB hub that browns out) are now noticed and reopened
  automatically instead of freezing silently. Preview shows each camera's real frame rate, and
  "NO PICTURE - reconnecting" while one is stalled.
- Halo v4 hardware: light-only ring with 45° scarf joints (no splice plates), cameras moved into the
  4 legs (2, 4, 8, 10 o'clock, 24 mm above the board face). Synthetic tests now use the v4 camera
  positions (99.3 % exact on 150 darts).

## v0.1.1
- Update checker works without GitHub releases: it reads the version number from the code on `main`
  and downloads the `main` branch, so every pushed fix can be installed with `python -m dartvision update`.

## v0.1.0
- First prototype: camera setup and preview, click calibration, multi-camera dart detection
  (dart-axis line crossing), 501 scoring, throw recording with automatic labelling,
  replay accuracy reports, update checker, synthetic tests, halo v3 3D-print files.
