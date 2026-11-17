"""Flash the board light (the halo's LED strip) on a 180.

The strip is a plain one-colour 24 V strip, so "flashing" means switching its power off and on
a few times. How that's done depends on what it's plugged into; pick one in config.yaml:

    lights:
      type: none            # none | http | command | gpio
      # http: a smart plug / Wi-Fi controller (Shelly, Tasmota, WLED, Home Assistant webhook...)
      on_url:  http://192.168.1.50/relay/0?turn=on
      off_url: http://192.168.1.50/relay/0?turn=off
      # command: any program or script that switches it
      on_cmd:  ""
      off_cmd: ""
      # gpio: a Raspberry Pi pin driving a MOSFET module, dimmable (PWM; needs gpiozero)
      pin: 18
      active_high: true
      brightness: 1.0       # normal level, 0.0 - 1.0 (gpio only)
      pwm_hz: 1000
      # the flash
      flashes: 6            # off/on blinks
      interval: 0.25        # seconds per half-blink

During a flash it blinks between off and full brightness, then goes back to its normal level. Flashing runs in the background.
"""
import shlex
import subprocess
import threading
import time
import urllib.request

DEFAULT = {"type": "none", "on_url": "", "off_url": "", "on_cmd": "", "off_cmd": "",
           "pin": 18, "active_high": True, "brightness": 1.0, "pwm_hz": 1000, "flashes": 6, "interval": 0.25}


class Lights:
    def __init__(self, cfg=None, switch=None, sleep=time.sleep):
        self.cfg = {**DEFAULT, **(cfg or {})}
        self.sleep = sleep
        self._busy = threading.Lock()
        self.switch = switch or self._make_switch()

    @property
    def level(self):
        """Normal brightness, 0 - 1."""
        try:
            return max(0.0, min(1.0, float(self.cfg["brightness"])))
        except (TypeError, ValueError):
            return 1.0

    def set_level(self, level):
        """Dim / brighten (gpio). Out of a flash only."""
        self.cfg["brightness"] = level
        if self.switch and not self._busy.locked():
            try:
                self.switch(self.level)
            except Exception:  # noqa
                pass

    @property
    def enabled(self):
        return self.switch is not None

    def _make_switch(self):
        c, t = self.cfg, str(self.cfg["type"]).lower()
        if t == "http" and c["on_url"] and c["off_url"]:
            def sw(level):
                urllib.request.urlopen(c["on_url"] if level > 0 else c["off_url"], timeout=2).read()
            return sw
        if t == "command" and c["on_cmd"] and c["off_cmd"]:
            def sw(level):
                subprocess.run(shlex.split(c["on_cmd"] if level > 0 else c["off_cmd"]), timeout=5,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return sw
        if t == "gpio":
            try:
                from gpiozero import PWMOutputDevice
                dev = PWMOutputDevice(int(c["pin"]), active_high=bool(c["active_high"]),
                                      initial_value=self.level, frequency=int(c["pwm_hz"]))
            except Exception as e:  # noqa - not a Pi, or gpiozero missing
                print(f"lights: GPIO pin {c['pin']} not available ({e}) - no light flashing")
                return None

            def sw(level):
                dev.value = max(0.0, min(1.0, float(level)))
            return sw
        if t not in ("none", "off", ""):
            print(f"lights: type '{t}' needs more settings in config.yaml - no light flashing")
        return None

    def flash_now(self):
        """Blink, then back to the normal level. Returns False if already flashing or no light set up."""
        if not self.switch or not self._busy.acquire(blocking=False):
            return False
        try:
            for _ in range(int(self.cfg["flashes"])):
                for level in (0.0, 1.0):
                    try:
                        self.switch(level)
                    except Exception:  # noqa - a light that doesn't answer never stops the game
                        pass
                    self.sleep(float(self.cfg["interval"]))
        finally:
            try:
                self.switch(self.level)
            except Exception:  # noqa
                pass
            self._busy.release()
        return True

    def flash(self):
        """Blink in the background."""
        if self.switch:
            threading.Thread(target=self.flash_now, daemon=True).start()
