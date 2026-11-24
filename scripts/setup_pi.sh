#!/usr/bin/env bash
# Raspberry Pi / Debian setup for dartvision.
#
#   scripts/setup_pi.sh            everything: system packages, the .venv, the Python packages, and
#                                  start dartvision on boot (no screen) - then set up the cameras
#                                  and calibrate from the phone / PC page
#   scripts/setup_pi.sh service    only (re)install the start-on-boot service
#   scripts/setup_pi.sh remove     stop it starting on boot
#   scripts/setup_pi.sh log        follow dartvision's log (add: | grep timing:  for the speed lines)
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
}

journal() {
    # Pi OS keeps the system log in memory only, and then there's no per-user log at all:
    # "journalctl --user" says "No journal files were found". Keep it on disk (capped at 100 MB).
    if [ ! -f /etc/systemd/journald.conf.d/dartvision.conf ]; then
        echo "== Keeping the log on disk (so  journalctl --user -u dartvision  works)"
        sudo mkdir -p /etc/systemd/journald.conf.d /var/log/journal
        printf '[Journal]\nStorage=persistent\nSystemMaxUse=100M\n' |
            sudo tee /etc/systemd/journald.conf.d/dartvision.conf >/dev/null
        sudo systemd-tmpfiles --create --prefix /var/log/journal
        sudo systemctl restart systemd-journald
    fi
}

log() {
    # works whether or not the log is kept on disk
    exec sudo journalctl _SYSTEMD_USER_UNIT=dartvision.service -f -n 50
}

service() {
    if [ ! -x "$VENV/bin/python" ]; then
        echo "Run scripts/setup_pi.sh first (no .venv yet)." >&2
        exit 1
    fi
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT" <<UNITEOF
[Unit]
Description=dartvision (web scoreboard on port 8080)

[Service]
WorkingDirectory=$ROOT
# print lines straight to the log (otherwise Python holds them back in a buffer)
Environment=PYTHONUNBUFFERED=1
# give Wi-Fi a moment so the update-on-start can reach GitHub
ExecStartPre=/bin/sleep 15
ExecStart=$VENV/bin/python -m dartvision play --headless
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNITEOF
    journal
    systemctl --user daemon-reload
    systemctl --user enable dartvision
    systemctl --user restart dartvision
    # start at boot without anyone logging in
    sudo loginctl enable-linger "$USER"
    echo
    echo "dartvision is running and starts on boot."
    echo "Open  http://$(hostname).local:8080  on a phone or PC on the same Wi-Fi, then:"
    echo "  Set up cameras  -> tick the cameras, turn them board-down, Save"
    echo "  Calibrate cameras -> 5 points on each camera (easier on a PC), Save"
    echo "  log:        scripts/setup_pi.sh log     (speed of each dart: scripts/setup_pi.sh log | grep timing:)"
    echo "  stop/start: systemctl --user stop dartvision  /  systemctl --user start dartvision"
    echo "  (stop it before running  python -m dartvision calibrate / preview / setup  in a terminal -"
    echo "   only one program can use the cameras)"
}

remove() {
    systemctl --user disable --now dartvision 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload
    echo "dartvision no longer starts on boot."
}

case "${1:-install}" in
    install) install; service ;;
    service) service ;;
    remove)  remove ;;
    log)     log ;;
    *) echo "usage: $0 [install|service|remove|log]" >&2; exit 2 ;;
esac
