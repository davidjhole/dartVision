# dartvision v0.1 – DIY automatic dart scoring

Runs on **Windows, Linux (incl. Raspberry Pi) and macOS**. Python + OpenCV.

## 1. Install (once)

**Easiest: with git** (makes updating a one-liner):
```
git clone https://github.com/davidjhole/dartVision.git
cd dartvision
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
*Raspberry Pi:* if `opencv-python` won't install, use `sudo apt install python3-opencv` and create the venv with `--system-site-packages`.

## 2. Cameras

Plug the cameras into **at least two different USB ports** (or a powered USB 3 hub). Then:

```
python -m dartvision setup              # finds cameras, writes config.yaml
python -m dartvision setup --skip 0     # same, but leave out index 0 (e.g. the laptop webcam)
python -m dartvision preview            # live view of every camera
```
Edit `config.yaml` to rename cameras or set `rotate: 180` if a camera is upside down.
**Each camera picture must have the board at the bottom and the room above it** (dart flights point up).
Set `exposure:` to a number once lighting is final, so the picture doesn't change brightness by itself.

## 3. Calibrate (each camera, ~1 minute)

```
python -m dartvision calibrate
```
Click, in order: **1** the bull centre, then where a wire meets the **outer edge of the double ring**:
**2** between 20 and 1, **3** between 6 and 10, **4** between 3 and 19, **5** between 11 and 14.
The little board top-left shows which point is next, and the box top-right is a magnifier.
When all 5 are placed a green wire overlay appears – drag points until it sits exactly on the
real wires, then **S** to save and **N** for the next camera. (`F` freezes the image.)
Redo this whenever a camera or the board moves.

## 4. Play

```
python -m dartvision play Dave Sam              # 501, double out
python -m dartvision play Dave --start 301
```
Throw – each dart is scored automatically. Pulling the darts out moves to the next player.
Keys: **C** correct the last dart (type e.g. `T20`, `D16`, `5`, `SB`, `DB`, `MISS` in the terminal),
**U** undo, **M** add a miss (bounce-out), **N** next player, **R** re-baseline, **Q** quit.

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
`python tests/test_pipeline.py` renders synthetic camera views from the halo's camera positions
and checks calibration, detection and scoring (currently ~97 % exact on 150 random darts, misses are all < 1 mm from a wire).

## Known limits / next steps
- No lens-distortion correction yet (100° lenses bend lines a little near the edges) – next step: a checkerboard calibration per camera.
- Darts hidden behind earlier darts are the hardest case – recordings will show how often.
- Scoreboard is a simple OpenCV window; a proper full-screen web scoreboard for the TV comes next.
