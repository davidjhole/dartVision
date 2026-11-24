# Changelog

Newest first. The update checker shows the section for the version you're updating to.

## Unreleased
- **Test 180 flash** button on the start screen (window and web page): flashes the light, screen and
  phone and calls the 180, so the light can be checked without throwing one.
- Messages on screen: an info line along the bottom of the window and the phone page shows the
  latest message (warnings yellow, errors red). Tab or a click on it (the Log button on the phone)
  opens the full log - everything that's printed in the terminal, plus errors from background
  threads. A phone tap that hits an error is logged instead of stopping the game.
- Phone page knows when the computer goes away: "dartvision was closed on the computer" on a
  normal quit / Ctrl+C, "Lost connection - retrying" if it crashes or the Wi-Fi drops. It reconnects
  by itself and reloads when dartvision starts again (so it picks up an updated page too).
- Updates itself on `play` start (git installs): fetches main, fast-forwards only when it's safe
  (no local changes, same branch, online), installs new requirements, restarts; goes back to the
  previous version if the new one won't start. `update: auto: false` turns it off. The quit-time
  "install?" question no longer hangs or crashes when there's no keyboard (headless).
- Darts caller: scores are called out loud after each turn ("One hundred and eighty!", "No score",
  "Bust", "Game shot, and the leg!", "Dave, you require 40"). Speaks on the computer (Mac `say`,
  Linux / Pi `espeak-ng`, Windows' own voice; through a Pi's HDMI that's the TV), or on the phone /
  iPad / TV web page: tap **Voice off** at the top right to turn it on there. `voice:` in config.yaml.
- A 180 flashes the screen and the web page, and can flash the halo light (`lights:` in config.yaml:
  a Pi pin driving a MOSFET with dimming, a smart plug / Wi-Fi controller URL, or any command).
- Phone / web page now updates when players or options are changed on the computer (a player added
  in the window didn't show on the phone until something else changed).
- Automated tests (`python -m pytest tests`) for the game rules, start menu and web remote; run in
  GitHub Actions along with the detection and STL checks (the STL check was failing in Actions
  because trimesh's helper packages weren't installed).
- Web scoreboard + remote (phone / iPad / TV): menu, scores, board, tap-to-correct keypad, undo /
  miss / darts out. `play --headless` (automatic on a Pi with no screen) runs with no window.
- No false "no picture" for the first camera while the others are still opening; macOS matmul warnings hidden.
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
