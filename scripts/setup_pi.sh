#!/usr/bin/env bash
# Raspberry Pi / Debian setup for dartvision.
#
#   scripts/setup_pi.sh            install system packages, the .venv and the Python packages
#   scripts/setup_pi.sh service    start dartvision (play, no screen) on boot - after calibrating
#   scripts/setup_pi.sh remove     stop it starting on boot
#
# Safe to run again. Run it as your normal user (not with sudo); it asks for sudo when it needs it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/dartvision.service"

if [ "$(id -u)" = 0 ]; then
    echo "Run this as your normal user, not with sudo (it asks for sudo itself)." >&2
    exit 1
fi

install() {
    echo "== System packages"
    sudo apt-get update
    # libgl1 + libglib2.0-0: OpenCV needs them, and Pi OS Lite doesn't have them
    # espeak-ng: the caller's voice on the Pi itself
    sudo apt-get install -y git python3-venv python3-pip espeak-ng libgl1 libglib2.0-0

    echo "== Python packages ($VENV)"
    if [ ! -x "$VENV/bin/python" ]; then
        # system site packages: lets it use the Pi's own gpiozero for the 180 light
        python3 -m venv --system-site-packages "$VENV"
    fi
    "$VENV/bin/python" -m pip install -q -r "$ROOT/requirements.txt"
    "$VENV/bin/python" -c "import cv2; print('OpenCV', cv2.__version__, 'OK')"

    echo
    echo "Done. Next, with the cameras plugged in:"
    echo "  cd $ROOT && source .venv/bin/activate"
    echo "  python -m dartvision setup        # find the cameras"
    echo "  python -m dartvision calibrate    # needs a window (VNC or ssh -Y) until calibration is on the phone"
    echo "  scripts/setup_pi.sh service       # then start it on boot"
}

service() {
    if [ ! -x "$VENV/bin/python" ]; then
        echo "Run scripts/setup_pi.sh first (no .venv yet)." >&2
        exit 1
    fi
    if ! ls "$ROOT"/calib/*.json >/dev/null 2>&1; then
        echo "No camera is calibrated yet (nothing in calib/). Run  python -m dartvision calibrate  first," >&2
        echo "otherwise 'play' stops straight away and the service keeps restarting." >&2
        exit 1
    fi
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT" <<UNITEOF
[Unit]
Description=dartvision (web scoreboard on port 8080)

[Service]
WorkingDirectory=$ROOT
# give Wi-Fi a moment so the update-on-start can reach GitHub
ExecStartPre=/bin/sleep 15
ExecStart=$VENV/bin/python -m dartvision play --headless
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNITEOF
    systemctl --user daemon-reload
    systemctl --user enable dartvision
    systemctl --user restart dartvision
    # start at boot without anyone logging in
    sudo loginctl enable-linger "$USER"
    echo
    echo "dartvision now starts on boot. Phone: http://$(hostname).local:8080"
    echo "  log:        journalctl --user -u dartvision -f"
    echo "  stop/start: systemctl --user stop dartvision  /  systemctl --user start dartvision"
    echo "  (stop it before running calibrate or preview - only one program can use the cameras)"
}

remove() {
    systemctl --user disable --now dartvision 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload
    echo "dartvision no longer starts on boot."
}

case "${1:-install}" in
    install) install ;;
    service) service ;;
    remove)  remove ;;
    *) echo "usage: $0 [install|service|remove]" >&2; exit 2 ;;
esac
