# Changelog

Newest first. The update checker shows the section for the version you're updating to.

## Unreleased
- **The Pi's health in the log.** Every 10 minutes, and straight away when something changes, a
  `health:` line gives the CPU temperature, whether the Pi is slowing itself down or getting too little
  power (`vcgencmd get_throttled` in plain words, e.g. `0x80000` = "since boot: hit the soft temperature
  limit"), CPU speed and use (and how much of it is dartvision), load, memory, free disk and the fan.
- **A more useful log screen** (Settings > Show log): a health card at the top, filters (All, Problems,
  Timing, Health, Other) with counts, the whole log (3000 lines kept, was 300), and **Copy for sharing**
  and **Download**: one text report with the version, computer, settings, health history, a dart-speed
  summary and the log. Settings shows a one-line health summary too.
- The yellow "updated to ..." line is gone from the start screen; it's under the version in Settings
  (and in the log).
- **Much less work (and heat) while waiting for a dart.** Only every other camera picture is decoded
  while waiting for a throw, and one in five on the menu. Every picture is used again as soon as
  something moves. The main loop no longer copies all the camera pictures when none of them is new,
  and the phone page's state is refreshed 10 times a second, not 200.
- **Faster again on a Pi:** finding a dart is about 2.5x quicker and a pull-out about 4x. The
  cameras are worked on side by side, each change picture is made once and reused, and only the part
  of the picture around the board is used.
- **The settle wait counts real frames:** a frame now means a new picture from *every* camera, not just
  from any one of them. With 4 cameras the wait had been about a quarter of what it should be, so a
  dart could be looked at before every camera had a still picture of it (reads as "couldn't read that one").
- The `timing:` line gives the reason when a camera couldn't find the dart, and the loop time is the
  typical value, no longer pushed up by the slow pass that did the detection.
- **Pi log fixed:** `journalctl --user -u dartvision` said "No journal files were found" because Pi OS keeps
  its log in memory only. `setup_pi.sh` now keeps the log on disk (capped at 100 MB), and the service
  prints each line straight away. A new `scripts/setup_pi.sh log` shows the log. On a Pi that's already
  set up, run `scripts/setup_pi.sh service` once.
- **Quicker scores on a Raspberry Pi.** The pictures of each throw are saved in the background (eight
  PNGs per dart were holding the score up for a couple of seconds on a Pi), finding the dart is about
  3x faster, and the motion check only shrinks each frame instead of blurring it at full size.
  espeak stays running between calls (`voice: warm: false` to start it each time), and the phone page
  checks for new calls every 0.25 s.
- **Pulling the darts out ends the turn again** when pulling them nudges the board or a camera a pixel or
  the light shifts: it now checks that each dart's own spot looks empty again, not the whole picture.
- **`timing:` lines in the log** for every dart and pull-out: how long the dart was moving, the settle
  wait, finding it in each camera, saving, the main loop and the cameras' real frame rate; and when the
  score is called, how long after the dart landed and whether the Pi or the phone said it.
- Phone / PC calibration fixes: on a wide screen in Safari the point landed away from where you clicked
  (the page's 1.25x zoom upset the position maths) - the page isn't zoomed while calibrating now. 1x
  zoom shows the whole picture (it was cut off at the bottom). A wire point that's out of the
  camera's view can be swapped for any other: **Can't see it**, or tap a point on the little board;
  4 points minimum, more for a better fit. Points on the very edge of the picture are flagged.
- The **Voice** button no longer floats over every screen: it sits on the start and game screens and in Settings.
- The phone page's messages bar is gone: the latest message and the full **Log** are in **Settings**.
- **Settings** screen on the web page: set up cameras, calibrate, test the 180 flash, the version,
  **Restart and update** and **Reboot the Pi**. The start screen only has the game.
- Games are locked until every camera is set up and calibrated (web page and window).
- **Raspberry Pi in one command:** flash Pi OS Lite, `ssh` in, install git, clone, run `scripts/setup_pi.sh`.
  It installs everything (including `libgl1`, which OpenCV needs on Lite) and starts dartvision on boot with
  no screen; the rest is done from the phone / PC page.
- **Set up cameras** from the phone / PC page (what `python -m dartvision setup` does): a picture from every
  camera found, tick the ones to use, turn them board-down, Save - used straight away. `play` now starts
  with no cameras at all, so a brand-new install can be set up from the page.
- Linux: only USB cameras are looked for (a Raspberry Pi 5's own camera / video devices are skipped).
- README: `cd dartVision` (the folder name is case-sensitive on Linux / Pi).
- Calibrate from the phone / iPad / PC web page: **Calibrate cameras** in the menu shows each
  camera's picture; tap the 5 points, zoom in and nudge them with a magnifier, see the wire overlay
  and fit error, Save. It's used straight away without restarting, so a Pi with no screen no longer
  needs VNC. `calibrate --web` (automatic with no screen) serves only the calibration page. `play`
  now starts even when no camera is calibrated yet, so you can calibrate from the phone.
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
