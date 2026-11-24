# dartvision v0.1 – DIY automatic dart scoring

Runs on **Windows, Linux (incl. Raspberry Pi) and macOS**. Python + OpenCV.

## 1. Install (once)

**Easiest: with git** (makes updating a one-liner):
```
git clone https://github.com/davidjhole/dartVision.git
cd dartVision
```
(or download the ZIP from the GitHub Releases page and unzip it)


1. Install **Python 3.10 or newer** – python.org (Windows/Mac), or `sudo apt install python3-pip python3-venv` on Linux / Pi.
2. Open a terminal in this folder and run:

```
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
```
*Mac:* the first time a camera opens, allow camera access for Terminal (System Settings → Privacy & Security → Camera).

**Raspberry Pi (no screen needed):** flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager
(in its settings: hostname `dartvision`, your user, Wi-Fi, and *Enable SSH*), `ssh` in, then instead of the steps above:
```
sudo apt update && sudo apt install -y git
git clone https://github.com/davidjhole/dartVision.git
cd dartVision
scripts/setup_pi.sh
```
That's it. It installs what the Pi needs (including `libgl1`, which OpenCV needs and Lite leaves out), makes the
`.venv`, installs the Python packages and starts dartvision, now and on every boot, with no screen. Then, on a phone
or PC on the same Wi-Fi, open **`http://dartvision.local:8080`**, tap **Settings**, then **Set up cameras** (2. below),
then **Calibrate cameras** (3. below; easier on a PC). Nothing else is needed on the Pi.
Games stay locked until every camera is calibrated. **Settings** also shows the version and has
**Restart and update** and **Reboot the Pi** (both install a newer version from GitHub first, if there is one).
- Log: `journalctl --user -u dartvision -f`. Stop / start: `systemctl --user stop dartvision` / `start`
  (stop it before running `setup`, `calibrate` or `preview` in a terminal: only one program can use the cameras).
- `scripts/setup_pi.sh remove` stops it starting on boot.

If `opencv-python` won't install, use `sudo apt install python3-opencv` and run `scripts/setup_pi.sh` again.

## 2. Cameras

Plug the cameras into **at least two different USB ports** (or a powered USB 3 hub).

**From a phone, iPad or PC:** with `play` running, tap **Set up cameras** in the menu. It shows a picture
from every camera it finds: tick the ones on the board, tap **Turn** until the board is at the bottom of each
picture, and **Save**. They're used straight away. (Turning a camera that was calibrated sets its old
calibration aside, so calibrate it again.) **Or in a terminal:**

```
python -m dartvision setup              # finds cameras, writes config.yaml
python -m dartvision setup --skip 0     # same, but leave out index 0
python -m dartvision preview            # live view of every camera
```
On macOS and Linux / Raspberry Pi, `setup` shows each camera's name, leaves out the computer's own
camera (FaceTime etc.) by itself, and remembers each camera by the **USB port** it's plugged into.
So if the computer renumbers the cameras (after unplugging one, switching a hub port off or a
restart) each one is still found - just keep every camera in the same port.
A camera that stops sending pictures shows **NO PICTURE** in preview and is reopened automatically.
Edit `config.yaml` to rename cameras or set `rotate: 180` if a camera is upside down.
**Each camera picture must have the board at the bottom and the room above it** (dart flights point up).
Set `exposure:` to a number once lighting is final, so the picture doesn't change brightness by itself.

## 3. Calibrate (each camera, ~1 minute)

**From a phone, iPad or PC (no screen or VNC needed on the Pi).** Start dartvision as usual:
```
python -m dartvision play
```
open the address it prints (e.g. `http://192.168.1.40:8080`) in a browser on the same Wi-Fi, tap
**Settings**, then **Calibrate cameras**. (Only want to calibrate? `python -m dartvision calibrate --web`
serves just the calibration page; on a Pi with no screen `calibrate` does that by itself.)

For each camera, tap on its picture: **1** the bull centre, then where a wire meets the
**outer edge of the double ring**: normally **2** between 20 and 1, **3** between 6 and 10, **4** between 3 and 19,
**5** between 11 and 14. The little board shows which point is next (yellow) and which are done (green, numbered).
- **A point isn't in the picture?** (common with a low camera that sees the board side-on) Tap **Can't see it**,
  or tap any other wire point on the little board and place that one instead. Any 4 work; 5 or more
  are better (the 5th lets it check the fit), and spread out round the board is best.
  Don't put a point on the edge of the picture as a guess: it bends the whole fit (it's shown red).
- **+ / −** zoom the picture (it starts at 2x on a phone; 1x shows the whole picture); drag it to move around.
- **Drag a point** to nudge it: it moves slower than your finger, and a magnifier shows the exact spot.
- Once 4 are placed, green wires are drawn over the picture (with the fit error from 5 points). Nudge points until
  the green wires sit exactly on the real wires, then **Save**; it moves on to the next camera.
- **New picture** takes a fresh still from the camera, **Undo** removes the last point.

It's used straight away – no restart – and the menu warns while a camera isn't calibrated yet.
The picture is a still, so it doesn't matter if someone walks past while you're tapping.

**On the computer itself (with a screen):** `python -m dartvision calibrate` opens a window instead:
click the same 5 points, the box top-right is a magnifier, drag points to adjust, **S** saves and moves
on to the next camera (**N** skips one, **F** freezes the image).

Redo this whenever a camera or the board moves.

## 4. Play

```
python -m dartvision play
```
A menu opens: pick the game (**501 / 301 / 701, Cricket, Around the clock, Count up**), the number of
legs, double in / out, and type the players' names (Enter adds one). Enter starts.

Throw – each dart is scored automatically and shown on the board picture. Pulling the darts out moves
to the next player. When someone wins a leg it stops and shows the result; pull the darts out (or press
Enter) for the next leg. Every leg and match is saved to `recordings/results.jsonl`.

Wrong dart? **Click it** (or press **1**, **2**, **3**, or **C** for the last one) and type what it was
(`T20`, `D16`, `5`, `SB`, `DB`, `MISS`). Other keys: **U** undo last dart, **M** add a miss (bounce-out),
**R** darts are out (if it didn't notice), **N** next player, **V** show the cameras, **Q** back to the menu.

### Phone / iPad / TV scoreboard (and running a Pi with no screen)
`play` also starts a web page; the address is printed when it starts (e.g. `http://192.168.1.40:8080`).
Open it on any phone, iPad or TV browser on the same Wi-Fi: it shows the scores and the board, and
you can set up the game, tap a dart to correct it, undo, add a miss and say the darts are out.
On a Pi with no screen it runs like that automatically (or use `play --headless`), and cameras are
set up and calibrated from the same page (**Settings**), so a headless Pi never needs VNC.
`--port 8090` changes the port, `--no-web` turns it off.

### The caller (voice) and 180 flash
After each turn the score is called out like a darts caller: "One hundred and eighty!", "No score",
"Bust", "Dave, you require 40", "Game shot, and the leg!". It speaks on the computer running
dartvision (on a Pi plugged into the TV with HDMI, it comes out of the TV; on a Pi / Linux install a
voice once with `sudo apt install espeak-ng`). To hear it from a **phone, iPad or TV browser** instead,
tap **Voice off** (on the start and game screens, and in Settings) so it says **Voice on** (the tap is needed so the
browser allows sound). While a page has its voice on, the computer stays quiet so you don't hear it twice.
Choose with `voice: output:` in `config.yaml`: `auto` (that), `computer`, `web` or `both`; `enabled: false` turns it off.

A **180** flashes the screen and the web page. It can flash the light too, set in `lights:` in
`config.yaml`:
- **Pi + MOSFET** (dimmable): `type: gpio`, `pin: 18` (the Pi pin wired to the MOSFET's input),
  `brightness: 0.8` for the normal level. Needs `pip install gpiozero` (already on Raspberry Pi OS).
- **Smart plug / Wi-Fi controller** (Shelly, Tasmota, WLED...): `type: http`, `on_url:` and `off_url:`.
- **Anything else**: `type: command`, `on_cmd:` and `off_cmd:`.

To try it without throwing a 180, press **Test 180 flash** (on the window's start screen, or in **Settings** on the web page):
it flashes the light, the screen and the page and calls "One hundred and eighty!".

## 5. Improve accuracy with your own throws

Every throw is saved in `recordings/session_.../` (before/after picture from every camera),
and **labelled automatically while you play**: a dart you correct with **C** is saved with the
right score, a dart you **U**ndo is saved as a false detection, and any dart you didn't correct
by the time the darts are pulled is taken as correct. So normal play builds the test set.

```
python -m dartvision label  recordings/session_XXXX    # optional: review/label throws by hand
python -m dartvision replay recordings/session_XXXX    # re-run detection, prints accuracy %
```
Change detection settings (`detection:` in `config.yaml`) or the code, then `replay` again –
no need to throw again. This is how we'll tune it.

## 6. Updates

**Automatic, on `play` (git installs).** Before the cameras open, `play` fetches `main` from GitHub.
If there's anything new it fast-forwards, installs packages if `requirements.txt` changed, and
restarts itself on the new code - no keyboard needed, so it works on a Pi with no screen.
It's careful:
- offline or GitHub slow (a few seconds): starts the version that's there
- your own code changes, another branch, or local commits: leaves it alone and says why
- only at start-up, never in the middle of a game
- the new code is test-started first; if that fails, or it crashes before the game is running,
  it goes back to the previous version and won't try that commit again until something newer is pushed
  (if the previous version crashes as well, the update wasn't to blame and it's tried again next time)
- the phone page shows "updated to ..." after an update

Turn it off with `update: auto: false` in `config.yaml` (e.g. on the computer you change the code on).

On start-up (`play`, `preview`, `calibrate`) dartvision quietly checks GitHub for a newer version
(the latest release if there is one, otherwise the version number on the `main` branch).
If there is one, the scoreboard says so and you're offered the update when you quit. Or any time:
```
python -m dartvision update
```
Installed with git → it does a `git pull`; installed from a ZIP → it downloads the new version.
What changed is listed in `CHANGELOG.md`.
`config.yaml`, `calib/` and `recordings/` are never touched. Set `update: repo:` in `config.yaml`.

## How it works (v0.1)
1. **Calibration** – 5 clicks per camera give a homography: camera pixels ↔ millimetres on the board.
2. **Event detection** – watches for movement, waits until everything is still, compares with the previous still picture.
3. **Per camera** – the new dart is the biggest changed blob; a line is fitted along it and mapped onto the board.
4. **Fusion** – the dart lines from all cameras are crossed; the crossing point is the tip (works even if the point itself is hidden or low-contrast). Bad cameras are voted out.
5. **Scoring** – position → segment/ring using regulation board dimensions.

## Test without hardware
`pip install pytest` then `python -m pytest tests` runs the quick tests: game rules (x01, cricket,
around the clock, count up, legs, corrections), the start menu, and the web scoreboard / remote
(a real local server, including the computer and phone staying in step). They run on every push.

`python tests/test_pipeline.py` renders synthetic camera views from the halo's camera positions
and checks calibration, detection and scoring (currently ~97 % exact on 150 random darts, misses are all < 1 mm from a wire).

## Known limits / next steps
- No lens-distortion correction yet (100° lenses bend lines a little near the edges) – next step: a checkerboard calibration per camera.
- Darts hidden behind earlier darts are the hardest case – recordings will show how often.
- Scoreboard is a simple OpenCV window; a proper full-screen web scoreboard for the TV comes next.
