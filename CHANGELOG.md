# Changelog

Newest first. The update checker shows the section for the version you're updating to.

## Unreleased
- Start menu: 501 / 301 / 701 (double in / out), Cricket, Around the clock, Count up; first-to-N legs;
  players typed in the window. A won leg stops the game and shows the result; results are saved to
  recordings/results.jsonl.
- Any dart of the turn can be corrected: click it or press 1 / 2 / 3. Cameras hidden while playing (V shows them).
- Pulling darts out one at a time no longer scores an extra dart (a removed dart is recognised because
  the board goes back to how it looked empty). A hand pulling darts doesn't pop up the 'what was it' box.
- R now means "darts are out": ends the turn, moves to the next player and resets.
- Detection rebuilt for low cameras (from the first real game): each camera now gives its line of
  sight through the dart (left-right position in the picture is precise, height isn't) and the lines
  are crossed. Darts that show as several pieces are joined up; blobs that aren't dart-shaped or don't
  reach the board (people moving behind it) are ignored; one camera on its own no longer scores a dart.
  On the recorded game the dart that had to be corrected to 5 now comes out as 5 by itself.
- Correcting a dart (C) opens a box in the game window - no more typing in the terminal. A dart that
  couldn't be read opens the box by itself.
- Score input ignores stray characters, e.g. the 'c' itself landing in the terminal.
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
