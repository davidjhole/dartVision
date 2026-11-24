"""Scoreboard + remote control in a web browser (phone, iPad, TV), so the Pi can run with no screen.

The game loop puts its state here with publish(); the page polls /state and sends taps to /action,
which the game loop picks up with take_actions(). Standard library only.

Calibration from the page: set_calibrator() hands over an object (calibrate.WebCalibrator) that
serves /calib/cams, /calib/frame?cam=NAME (a JPEG), /calib/preview and /calib/save.
"""
import atexit
import json
import os
import queue
import socket
import threading
import time
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_state = {"v": 0, "data": {}}
BOOT = os.urandom(4).hex()          # changes every start: the page reloads itself when it sees a new one
_last_poll = {"t": 0.0}
_lock = threading.Lock()
_actions = queue.Queue()
_voice_seen = {"t": 0.0}     # last time a page with its voice switched on asked for the state
VOICE_TIMEOUT = 3.0
_calib = {"h": None}
_camsetup = {"h": None}


def set_calibrator(c):
    """Let the page calibrate the cameras (None turns it off)."""
    _calib["h"] = c


def set_camsetup(c):
    """Let the page set up the cameras (camsetup.CameraSetup; None turns it off). Its pictures are
    served at /setup/frame?index=N; the page's choices come in as setup_* actions."""
    _camsetup["h"] = c


def publish(data):
    """Share the latest state with the page. The version goes up whenever anything in it changed.

    data is copied (via JSON) before it's kept: the game loop hands over its own lists, such as the
    player list, and changes them in place later. Keeping a reference meant the stored copy changed
    too, so the comparison saw no difference, the version never went up and the phone never redrew
    (adding a player on the computer didn't show on the phone).
    """
    snap = json.loads(json.dumps(data))
    with _lock:
        if snap != _state["data"]:
            _state["data"] = snap
            _state["v"] += 1


def snapshot():
    """What /state serves right now."""
    with _lock:
        return {"v": _state["v"], "boot": BOOT, **_state["data"]}


def announce_stop(wait=1.5):
    """Tell open pages the program is closing (they show 'closed on the computer' instead of
    waiting for scores that will never come). Waits briefly so they get it, but only if a page has
    been polling recently, so quitting with no phone open isn't held up."""
    with _lock:
        _state["data"] = {"screen": "stopped"}
        _state["v"] += 1
    if server and time.monotonic() - _last_poll["t"] < 5:
        time.sleep(wait)


def voice_listening():
    """True while a phone / TV page with its voice switched on is open (it then does the talking)."""
    return time.monotonic() - _voice_seen["t"] < VOICE_TIMEOUT


def take_actions():
    out = []
    while True:
        try:
            out.append(_actions.get_nowait())
        except queue.Empty:
            return out


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/state"):
            _last_poll["t"] = time.monotonic()
            if "voice=1" in self.path:
                _voice_seen["t"] = time.monotonic()
            body = json.dumps(snapshot())
            self._send(200, body, "application/json")
        elif self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path.startswith("/calib/"):
            self._calib_get()
        elif self.path.startswith("/setup/frame"):
            c = _camsetup["h"]
            idx = parse_qs(urlparse(self.path).query).get("index", [""])[0]
            jpg = c.frame_jpeg(idx) if c else None
            if jpg is None:
                return self._send(404, "no picture", "text/plain")
            self._send(200, jpg, "image/jpeg")
        else:
            self._send(404, "not found", "text/plain")

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def _calib_get(self):
        c = _calib["h"]
        u = urlparse(self.path)
        if c is None:
            return self._json(404, {"ok": False, "error": "calibration isn't available"})
        if u.path == "/calib/cams":
            return self._json(200, c.cameras())
        if u.path == "/calib/frame":
            name = parse_qs(u.query).get("cam", [""])[0]
            jpg = c.frame_jpeg(name)
            if jpg is None:
                return self._send(503, "no picture from that camera", "text/plain")
            return self._send(200, jpg, "image/jpeg")
        self._send(404, "not found", "text/plain")

    def _calib_post(self, body):
        c = _calib["h"]
        if c is None:
            return self._json(404, {"ok": False, "error": "calibration isn't available"})
        try:
            if not isinstance(body, dict):
                raise ValueError("bad request")
            name, pts = str(body.get("cam", "")), body.get("points")
            tg = body.get("targets")
            if self.path == "/calib/preview":
                return self._json(200, c.preview(name, pts, tg))
            if self.path == "/calib/save":
                r = c.save(name, pts, tg)
                _actions.put({"type": "calibrated", "cam": name})     # the game loop reloads it
                return self._json(200, r)
        except ValueError as e:
            return self._json(400, {"ok": False, "error": str(e)})
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path not in ("/action", "/calib/preview", "/calib/save"):
            return self._send(404, "not found", "text/plain")
        n = int(self.headers.get("Content-Length", 0) or 0)
        if self.path.startswith("/calib/"):
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json(400, {"ok": False, "error": "bad request"})
            return self._calib_post(body)
        try:
            a = json.loads(self.rfile.read(n) or b"{}")
            if isinstance(a, dict) and isinstance(a.get("type"), str):
                _actions.put(a)
                return self._send(200, '{"ok":true}', "application/json")
        except ValueError:
            pass
        self._send(400, '{"ok":false}', "application/json")


server = None


def start(port=8080, host="0.0.0.0"):
    """Start the web server in the background. Returns the address to open, or None."""
    global server
    try:
        srv = ThreadingHTTPServer((host, port), _Handler)
    except OSError as e:
        print(f"web scoreboard not started (port {port}: {e})")
        return None
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    server = srv
    atexit.register(announce_stop)        # quit, Ctrl+C or a crash: pages are told it's closed
    return f"http://{local_ip()}:{srv.server_address[1]}"


def stop():
    global server
    if server:
        server.shutdown()
        server.server_close()
        server = None


PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>dartvision</title>
<style>
:root{--bg:#141618;--panel:#1d2023;--card:#292d31;--line:#33383d;--text:#f5f5f5;--muted:#9aa0a6;--dim:#5f656b;
--accent:#ffc800;--active:#e86e28;--good:#5ad25a;--bad:#e63c3c;--m0:#ffc800;--m1:#3ca0ff;--m2:#ff5ac8}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--text);font:16px/1.3 -apple-system,system-ui,Segoe UI,Roboto,sans-serif}
body{padding:max(12px,env(safe-area-inset-top)) 14px 14px;min-height:100vh}
button{font:inherit;color:inherit;border:0;border-radius:12px;background:var(--card);padding:12px 14px;cursor:pointer}
button:active{filter:brightness(1.3)}
.hidden{display:none!important}
h1{font-size:22px;margin:4px 0 14px;font-weight:800}
.sub{color:var(--muted);font-size:14px;margin:14px 0 6px}
.list button{display:block;width:100%;text-align:left;margin:6px 0;font-weight:700;font-size:18px;background:var(--panel)}
.list button.on{background:var(--card);box-shadow:inset 6px 0 0 var(--active)}
.row{display:flex;gap:8px;align-items:center}
.opt{display:flex;justify-content:space-between;align-items:center;background:var(--panel);border-radius:12px;padding:10px 14px;margin:6px 0}
.opt b{color:var(--accent)}
input{font:inherit;flex:1;padding:12px;border-radius:12px;border:1px solid var(--line);background:var(--panel);color:var(--text)}
.start{width:100%;margin-top:16px;background:var(--good);color:#111;font-weight:800;font-size:20px;padding:16px}
.wrap{display:grid;grid-template-columns:1fr;gap:14px;max-width:1400px;margin:auto}
@media(min-width:900px){.wrap{grid-template-columns:1.1fr 1fr}}
.title{color:var(--muted);font-size:15px}
.pcard{display:flex;justify-content:space-between;align-items:center;background:var(--panel);border-radius:16px;padding:12px 18px;margin:8px 0}
.pcard.on{background:var(--card);box-shadow:inset 8px 0 0 var(--active)}
.pname{font-weight:800;font-size:clamp(18px,3vw,30px)}
.psmall{color:var(--muted);font-size:14px}
.pbig{font-weight:900;font-size:clamp(40px,9vw,96px);letter-spacing:-1px}
.pcard.on .pbig{color:var(--accent)}
.dots span{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--dim);margin-right:5px}
.dots span.w{background:var(--good)}
.darts{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.dart{background:var(--panel);border-radius:14px;padding:14px 6px;text-align:center;border-top:6px solid transparent;min-height:92px}
.dart.has{background:var(--card)}
.dart .l{font-weight:900;font-size:clamp(24px,5vw,40px)}
.dart .p{color:var(--muted)}
.totalrow{display:flex;justify-content:space-between;align-items:baseline;margin:10px 2px}
.total{font-size:34px;font-weight:900}
.hint{color:var(--good);font-weight:800}
.bust{color:var(--bad);font-weight:800}
.status{color:var(--accent);font-size:15px;min-height:20px}
.ctl{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}
.board{width:100%;max-width:640px;margin:auto;display:block}
table.cr{width:100%;border-collapse:separate;border-spacing:0 5px}
table.cr td{background:var(--panel);text-align:center;padding:6px;font-size:22px;font-weight:800}
table.cr td.n{color:var(--text)} table.cr td.closed{color:var(--dim)}
.mk{color:var(--text)} .mk.c{color:var(--good)}
.overlay{position:fixed;inset:0;background:#000a;display:flex;align-items:center;justify-content:center;padding:16px;z-index:5}
.panel{background:var(--card);border-radius:18px;padding:18px;width:min(560px,100%);box-shadow:0 10px 40px #000}
.panel h2{margin:0 0 8px}
.panel button{background:#3a3f45}
.panel .mult button.on{background:var(--active)}
@media(min-width:1200px){body:not(.nozoom){zoom:1.25}}
body{padding-bottom:calc(52px + env(safe-area-inset-bottom))}
#info{position:fixed;left:0;right:0;bottom:0;z-index:4;display:flex;gap:10px;align-items:center;justify-content:space-between;
 background:#0e0f10;border-top:1px solid var(--line);padding:10px 14px calc(10px + env(safe-area-inset-bottom));font-size:13px;cursor:pointer}
#infot{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--muted)}
#info .lb{flex:none;background:var(--card);border-radius:8px;padding:4px 10px;color:var(--text)}
.lv-warn{color:var(--accent)!important} .lv-error{color:var(--bad)!important}
.logp{max-height:85vh;display:flex;flex-direction:column}
#logl{overflow:auto;font:12px/1.45 ui-monospace,Menlo,Consolas,monospace;background:#111;border-radius:10px;padding:10px;margin:8px 0;flex:1;min-height:200px}
#logl div{white-space:pre-wrap;word-break:break-word}
.kp{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;margin-top:10px}
.kp button{padding:14px 0;font-weight:800;font-size:19px}
.mult{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}
.mult button.on{background:var(--active)}
.banner{text-align:center}
.banner h2{font-size:34px}
.small{font-size:13px;color:var(--dim)}
#vbtn{position:fixed;top:max(8px,env(safe-area-inset-top));right:10px;z-index:4;font-size:14px;padding:8px 12px;background:var(--panel)}
#vbtn.on{background:var(--good);color:#111;font-weight:800}
.calbtn{width:100%;margin-top:10px;background:var(--panel)}
.warn{color:var(--accent);font-weight:700;margin:6px 0}
#cal{max-width:1100px;margin:auto}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.tabs button{background:var(--panel);font-weight:700}
.tabs button.on{background:var(--card);box-shadow:inset 0 -4px 0 var(--active)}
.calstep{display:flex;gap:10px;align-items:center;margin:6px 0 8px}
.calstep svg{width:150px;height:150px;flex:none;cursor:pointer}
#calmsg{font-weight:800;font-size:17px}
#calwrap{position:relative}
.calbox{width:100%;max-height:65vh;background:#000;border-radius:10px;overflow:auto;line-height:0;overscroll-behavior:contain}
#calinner{position:relative;width:100%;margin:0 auto}
.calbox img{width:100%;display:block;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}
#calsvg{position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:crosshair}
#loupe{position:absolute;top:8px;width:150px;height:150px;border:2px solid var(--accent);border-radius:50%;pointer-events:none;background:#000}
.good{color:var(--good)} .bad{color:var(--bad)}
#setup{max-width:1100px;margin:auto}
.scams{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin:10px 0}
.scam{background:var(--panel);border-radius:14px;padding:10px;border:2px solid transparent}
.scam.on{border-color:var(--good)}
.scam canvas{width:100%;display:block;background:#000;border-radius:8px;aspect-ratio:16/9}
.scam .row{justify-content:space-between;margin-top:8px}
.scam .nm{font-weight:800}
.scam label{display:flex;gap:8px;align-items:center;font-weight:800;font-size:17px}
.scam input[type=checkbox]{width:24px;height:24px}
#flash{position:fixed;inset:0;z-index:9;pointer-events:none;display:flex;align-items:center;justify-content:center;
font-weight:900;font-size:min(40vw,60vh);color:var(--accent);border:24px solid var(--accent);animation:fl .4s steps(2) infinite}
@keyframes fl{0%{background:#ffc80055;border-color:var(--accent);color:var(--accent)}50%{background:transparent;border-color:var(--bad);color:var(--bad)}}
</style></head><body>
<button id="vbtn" onclick="toggleVoice()">Voice off</button>
<div id="flash" class="hidden">180</div>
<div id="menu" class="hidden">
  <div class="row" style="padding-right:96px"><h1 style="flex:1">dartvision</h1><button onclick="openSettings()">&#9881; Settings</button></div>
  <div class="status" id="mstatus"></div>
  <div id="needset" class="hidden"><div class="panel" style="width:100%;margin:10px 0">
    <h2>Set up before playing</h2><div id="needmsg" class="title"></div>
    <button class="start" id="needbtn" style="background:var(--good);color:#111" onclick="needGo()"></button></div></div>
  <div id="menugame">
  <div class="sub">Game</div><div id="modes" class="list"></div>
  <div class="sub">Options</div><div id="opts"></div>
  <div class="sub">Players</div><div id="players"></div>
  <div class="row"><input id="pname" placeholder="Add a player" maxlength="14" autocomplete="off">
  <button onclick="addPlayer()">Add</button></div>
  <button class="start" onclick="act({type:'start'})">Start</button>
  </div>
</div>
<div id="settings" class="hidden">
  <div class="row" style="padding-right:96px"><h1 style="flex:1">Settings</h1><button onclick="closeSettings()">Back</button></div>
  <div class="sub">Cameras</div>
  <div id="camwarn" class="warn hidden">No cameras set up yet - tap Set up cameras</div>
  <div id="setnote" class="small"></div>
  <button id="setopen" class="calbtn hidden" onclick="act({type:'setup_open'})">Set up cameras</button>
  <div id="calwarn" class="warn hidden"></div>
  <button id="calopen" class="calbtn hidden" onclick="openCal()">Calibrate cameras</button>
  <div class="sub">Light</div>
  <button id="tflash" class="calbtn" style="font-weight:800;color:var(--accent)" onclick="act({type:'test_flash'})">Test 180 flash</button>
  <div class="sub">dartvision</div>
  <div class="opt"><span>Version</span><b id="ver" style="color:var(--text)"></b></div>
  <button class="calbtn" onclick="if(confirm('Restart dartvision? It checks for an update first, so give it a minute.'))act({type:'restart'})">Restart and update</button>
  <button id="rebootb" class="calbtn hidden" onclick="if(confirm('Reboot the whole computer? dartvision starts again by itself (and updates) in a minute or two.'))act({type:'reboot'})">Reboot the Pi</button>
  <div class="small" style="margin-top:6px">Both install a newer version from GitHub if there is one, then start again. The page reconnects by itself.</div>
</div>
<div id="setup" class="hidden">
  <div class="row" style="padding-right:96px"><h1 style="flex:1">Cameras</h1></div>
  <div class="status" id="setmsg"></div>
  <div class="small">Tick the cameras on the board and turn each one so the <b>board is at the bottom</b> of its
   picture (darts pointing up). Keep each camera in the same USB port afterwards - that's how it's recognised.</div>
  <div id="scams" class="scams"></div>
  <div class="ctl" style="grid-template-columns:repeat(3,1fr)">
    <button onclick="setScan()">Look again</button>
    <button onclick="act({type:'setup_cancel'})">Cancel</button>
    <button id="setsave" style="background:var(--good);color:#111;font-weight:800" onclick="setSave()">Save</button>
  </div>
</div>
<div id="cal" class="hidden">
  <div class="row" style="padding-right:96px"><h1 style="flex:1;white-space:nowrap">Calibrate</h1><button id="caldone" onclick="closeCal()">Done</button></div>
  <div id="caltabs" class="tabs"></div>
  <div class="calstep"><svg id="calguide" viewBox="-240 -240 480 480"></svg>
    <div><div id="calmsg"></div><div class="small" id="calsub"></div>
    <div class="small" style="margin-top:4px">Tap a dot on the little board to place that one next.</div></div></div>
  <div class="row" style="margin-bottom:6px"><button onclick="calZoom(-1)">&minus;</button><b id="calz">1x</b>
    <button onclick="calZoom(1)">+</button><span class="small">tap = place the next point &middot; drag a point = nudge it &middot; drag the picture = move around</span></div>
  <div id="calwrap"><div class="calbox" id="calbox"><div id="calinner"><img id="calimg" alt=""><svg id="calsvg"></svg></div></div>
    <canvas id="loupe" class="hidden" width="300" height="300"></canvas></div>
  <div class="ctl">
    <button onclick="calUndo()">Undo</button><button id="calskip" onclick="calSkipIt()">Can't see it</button>
    <button onclick="calPic()">New picture</button><button id="calsave" onclick="calSave()">Save</button>
  </div>
  <button class="calbtn" onclick="calReset()">Start this camera again</button>
  <div class="status" id="calstat"></div>
  <div class="small" id="calfoot"></div>
</div>
<div id="play" class="hidden"><div class="wrap">
  <div>
    <div class="title" id="gtitle"></div>
    <div id="pcards"></div>
    <div class="sub"><span id="who"></span> - this turn <span class="small">(tap a dart to correct it)</span></div>
    <div class="darts" id="darts"></div>
    <div class="totalrow"><div>turn <span class="total" id="total"></span></div><div id="hint"></div></div>
    <div class="status" id="status"></div>
    <div class="ctl">
      <button onclick="act({type:'undo'})">Undo</button>
      <button onclick="act({type:'miss'})">Miss</button>
      <button onclick="act({type:'darts_out'})">Darts out</button>
      <button onclick="if(confirm('Leave this game?'))act({type:'menu'})">Menu</button>
    </div>
  </div>
  <div><div id="table"></div><svg id="board" class="board" viewBox="-240 -240 480 480"></svg></div>
</div></div>
<div id="kpo" class="overlay hidden" onclick="if(event.target===this)closeKp()"><div class="panel">
  <h2 id="kpt">Dart</h2>
  <div class="mult"><button data-m="S" class="on">Single</button><button data-m="D">Double</button><button data-m="T">Treble</button></div>
  <div class="kp" id="kp"></div>
  <div class="kp"><button onclick="pick('SB')" style="grid-column:span 2">Outer bull</button>
  <button onclick="pick('DB')" style="grid-column:span 2">Bull</button><button onclick="pick('MISS')">Miss</button></div>
  <button style="width:100%;margin-top:10px" onclick="closeKp()">Cancel</button>
</div></div>
<div id="bano" class="overlay hidden"><div class="panel banner">
  <h2 id="bant"></h2><div id="banl" class="title"></div><br>
  <button class="start" id="banb" onclick="act({type:'next_leg'})"></button>
  <div class="small" style="margin-top:8px">a dart was wrong? close this and tap it</div>
  <button style="margin-top:8px" onclick="hideBanner=true;render()">Close</button>
</div></div>
<div id="lost" class="overlay hidden"><div class="panel banner">
  <h2 id="lostt">Lost connection</h2><div id="lostl" class="title"></div><br>
  <div class="small">This page reconnects by itself when dartvision is running again.</div>
</div></div>
<div id="info" onclick="toggleLog()"><span id="infot">connecting...</span><span class="lb">Log</span></div>
<div id="logo" class="overlay hidden" onclick="if(event.target===this)toggleLog()"><div class="panel logp">
  <h2>Log</h2><div class="small">what the computer printed, newest at the bottom</div><div id="logl"></div>
  <button onclick="toggleLog()">Close</button></div></div>
<script>
let voiceOn=false, lastCall=null, flashT=0;
try{voiceOn=localStorage.getItem('dv_voice')==='1'}catch(e){}
function updV(){$('vbtn').textContent=voiceOn?'Voice on':'Voice off';$('vbtn').classList.toggle('on',voiceOn)}
function speak(t){try{const u=new SpeechSynthesisUtterance(t);u.lang='en-GB';
 const v=speechSynthesis.getVoices().find(v=>v.lang==='en-GB');if(v)u.voice=v;speechSynthesis.speak(u)}catch(e){}}
function toggleVoice(){voiceOn=!voiceOn;try{localStorage.setItem('dv_voice',voiceOn?'1':'0')}catch(e){}
 if(voiceOn)speak('Voice on');else try{speechSynthesis.cancel()}catch(e){} updV();poll()}
function flash(){$('flash').classList.remove('hidden');clearTimeout(flashT);flashT=setTimeout(()=>$('flash').classList.add('hidden'),3000)}
function calls(s){const c=s.calls||[],top=c.length?c[c.length-1].n:0;
 if(lastCall===null||top<lastCall){lastCall=top;return}
 c.filter(x=>x.n>lastCall).forEach(x=>{if(voiceOn&&s.web_voice)speak(x.text);if(x.flash)flash()});lastCall=top}
let S={}, V=-1, kpDart=0, mult='S', hideBanner=false, lastLeg='';
const $=id=>document.getElementById(id);
const esc=t=>String(t).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function act(a){fetch('/action',{method:'POST',body:JSON.stringify(a)}).then(()=>setTimeout(poll,60))}
function addPlayer(){const n=$('pname').value.trim(); if(n){act({type:'add_player',name:n}); $('pname').value=''}}
$('pname').addEventListener('keydown',e=>{if(e.key==='Enter')addPlayer()});
document.querySelectorAll('.mult button').forEach(b=>b.onclick=()=>{mult=b.dataset.m;
  document.querySelectorAll('.mult button').forEach(x=>x.classList.toggle('on',x===b))});
(function(){let h='';for(let n=1;n<=20;n++)h+=`<button onclick="pick(mult+${n})">${n}</button>`;$('kp').innerHTML=h})();
function openKp(i){kpDart=i;$('kpt').textContent='Dart '+(i+1)+' was:';$('kpo').classList.remove('hidden')}
function closeKp(){$('kpo').classList.add('hidden')}
function pick(l){act({type:'set_dart',i:kpDart,label:l});closeKp()}
const SECT=[20,1,18,4,13,6,10,15,2,17,3,19,7,16,8,11,14,9,12,5];
function boardSVG(marks){const R=[6.35,15.9,99,107,162,170];let s='';
 const arc=(r0,r1,a0,a1,c)=>{const p=(r,a)=>[r*Math.sin(a),-r*Math.cos(a)];const[a,b]=p(r1,a0),[c2,d]=p(r1,a1),[e,f]=p(r0,a1),[g,h]=p(r0,a0);
  return `<path d="M${a} ${b}A${r1} ${r1} 0 0 1 ${c2} ${d}L${e} ${f}A${r0} ${r0} 0 0 0 ${g} ${h}Z" fill="${c}"/>`};
 s+='<circle r="226" fill="#1b1b1b"/>';
 for(let i=0;i<20;i++){const a0=(i*18-9)*Math.PI/180,a1=(i*18+9)*Math.PI/180,dark=i%2==0,
  bg=dark?'#141414':'#ead9b5',ring=dark?'#d83030':'#249447';
  s+=arc(R[1],R[2],a0,a1,bg)+arc(R[2],R[3],a0,a1,ring)+arc(R[3],R[4],a0,a1,bg)+arc(R[4],R[5],a0,a1,ring);
  const t=(i*18)*Math.PI/180;s+=`<text x="${196*Math.sin(t)}" y="${-196*Math.cos(t)+6}" fill="#bbb" font-size="17" text-anchor="middle">${SECT[i]}</text>`}
 s+=`<circle r="${R[1]}" fill="#249447"/><circle r="${R[0]}" fill="#d83030"/>`;
 const col=['var(--m0)','var(--m1)','var(--m2)'];
 (marks||[]).forEach(m=>{s+=`<circle cx="${m.x}" cy="${-m.y}" r="9" fill="${col[m.i%3]}" stroke="#111" stroke-width="2"/>`});
 return s}
let setOpen=false;
function openSettings(){setOpen=true;render();scrollTo(0,0)}
function closeSettings(){setOpen=false;render();scrollTo(0,0)}
function needGo(){if(S.no_cameras&&S.can_setup)act({type:'setup_open'});else if(S.can_calibrate)openCal();else openSettings()}
function render(){
 const setup=S.screen==='setup';$('setup').classList.toggle('hidden',!setup);
 if(setup){if(calOpen)closeCal();['menu','play','settings'].forEach(id=>$(id).classList.add('hidden'));renderSetup();return}
 if(S.screen==='calibrate'){['menu','play','settings'].forEach(id=>$(id).classList.add('hidden'));if(!calOpen)openCal();return}
 const menu=S.screen==='menu',sett=setOpen&&menu&&!calOpen;
 $('settings').classList.toggle('hidden',!sett);
 $('menu').classList.toggle('hidden',!menu||calOpen||sett);$('play').classList.toggle('hidden',menu||calOpen);
 const notReady=S.ready===false;$('needset').classList.toggle('hidden',!notReady);$('menugame').classList.toggle('hidden',notReady);
 $('needmsg').textContent=S.no_cameras?'No cameras are set up yet.':'Not calibrated yet: '+(S.uncalibrated||[]).join(', ')+'. Games unlock once every camera is calibrated.';
 $('needbtn').textContent=S.no_cameras&&S.can_setup?'Set up cameras':'Calibrate cameras';
 $('ver').textContent=S.version||'';$('rebootb').classList.toggle('hidden',!S.can_reboot);
 $('setopen').classList.toggle('hidden',!S.can_setup);$('camwarn').classList.toggle('hidden',!(S.can_setup&&S.no_cameras));$('setnote').textContent=S.setup_note||'';
 const unc=S.uncalibrated||[];$('calopen').classList.toggle('hidden',!S.can_calibrate);
 $('calwarn').classList.toggle('hidden',!unc.length);
 $('calwarn').textContent=unc.length?'Not calibrated yet: '+unc.join(', ')+' - games are locked until '+(unc.length>1?'they are':'it is'):'';
 if(menu){const M=S.menu;
  $('modes').innerHTML=M.modes.map((m,i)=>`<button class="${i==M.mode?'on':''}" onclick="act({type:'mode',i:${i}})">${esc(m)}</button>`).join('');
  $('opts').innerHTML=M.opts.map((o,i)=>`<div class="opt"><span>${o[0]}</span><span><button onclick="act({type:'opt',row:${i+1},step:-1})">&lsaquo;</button> <b>${o[1]}</b> <button onclick="act({type:'opt',row:${i+1},step:1})">&rsaquo;</button></span></div>`).join('');
  $('players').innerHTML=M.players.map((p,i)=>`<div class="opt"><b style="color:var(--text)">${esc(p)}</b><button onclick="act({type:'remove_player',i:${i}})">remove</button></div>`).join('');
  $('mstatus').textContent=S.note||'';
  $('kpo').classList.add('hidden');$('bano').classList.add('hidden');return}
 const G=S.game;$('gtitle').textContent=G.title;
 $('pcards').innerHTML=G.players.map(p=>`<div class="pcard ${p.active?'on':''}"><div><div class="pname">${esc(p.name)}</div><div class="psmall">${p.small}</div>
  ${G.legs_to_win>1?'<div class="dots">'+Array.from({length:G.legs_to_win},(_,k)=>`<span class="${k<p.legs?'w':''}"></span>`).join('')+'</div>':''}</div><div class="pbig">${p.big}</div></div>`).join('');
 $('who').textContent=G.player;
 const cols=['var(--m0)','var(--m1)','var(--m2)'];
 $('darts').innerHTML=[0,1,2].map(i=>{const d=G.turn[i];return `<div class="dart ${d?'has':''}" style="${d?'border-top-color:'+cols[i]:''}" onclick="${i<=G.turn.length?'openKp('+i+')':''}">
  <div class="l">${d?d[0]:'-'}</div><div class="p">${d?d[1]:''}</div></div>`}).join('');
 $('total').textContent=G.total;
 $('hint').innerHTML=G.bust?'<span class="bust">BUST - pull the darts</span>':(G.hint?`<span class="hint">${G.hint}</span>`:'');
 $('status').textContent=S.status||'';
 $('table').innerHTML=G.table?'<table class="cr">'+'<tr><td></td>'+G.players.map(p=>`<td style="font-size:15px;color:${p.active?'var(--accent)':'var(--muted)'}">${esc(p.name)}</td>`).join('')+'</tr>'+
  G.table.map(r=>`<tr><td class="${r[2]?'closed':'n'}">${r[0]}</td>`+r[1].map(m=>`<td class="mk ${m>=3?'c':''}">${['','/','X','&#9711;'][Math.min(m,3)]}</td>`).join('')+'</tr>').join('')+'</table>':'';
 $('board').innerHTML=boardSVG(G.marks);
 const won=G.leg_winner; if(won!==lastLeg){hideBanner=false;lastLeg=won}
 $('bano').classList.toggle('hidden',!won||hideBanner);
 if(won){$('bant').textContent=G.match_winner?`${won} wins!`:`${won} wins the leg`;
  $('banl').textContent=G.legs_to_win>1?'legs  '+G.players.map(p=>p.name+' '+p.legs).join('  -  '):'';
  $('banb').textContent=G.match_winner?'Back to the menu':'Next leg';}
}
let offline=false, logOpen=false, fails=0, boot=null, lastOk=Date.now();
function showLost(){const stopped=S.screen==='stopped', down=fails>=3;
 $('lost').classList.toggle('hidden',!(stopped||down));
 $('lostt').textContent=stopped?'dartvision was closed on the computer':'Lost connection to the computer';
 $('lostl').textContent=stopped?'':'last heard from it '+Math.round((Date.now()-lastOk)/1000)+' s ago - retrying...'}
function hhmm(t){const d=new Date(t*1000);return d.toTimeString().slice(0,8)}
function toggleLog(){logOpen=!logOpen;$('logo').classList.toggle('hidden',!logOpen);renderLog(true)}
function renderLog(scroll){
 const L=S.log||[], i=$('infot');
 if(offline){i.textContent="can't reach the computer - is dartvision running?";i.className='lv-error'}
 else{const e=L[L.length-1];
  if(!e){i.textContent='no messages';i.className=''}
  else{i.textContent=hhmm(e[0])+'  '+e[2];const fresh=Date.now()/1000-e[0]<60;i.className=e[1]!=='info'&&fresh?'lv-'+e[1]:''}}
 if(logOpen){const box=$('logl'),end=box.scrollTop+box.clientHeight>=box.scrollHeight-20;
  box.innerHTML=L.map(e=>`<div class="lv-${e[1]}">${hhmm(e[0])}  ${esc(e[2])}</div>`).join('')||'<div>nothing yet</div>';
  if(scroll||end)box.scrollTop=box.scrollHeight}}
async function poll(){try{const ac=new AbortController(),to=setTimeout(()=>ac.abort(),2500);
 const r=await fetch('/state'+(voiceOn?'?voice=1':''),{cache:'no-store',signal:ac.signal});clearTimeout(to);const s=await r.json();
 if(boot&&s.boot&&s.boot!==boot){location.reload();return}   // restarted (maybe updated): fresh page
 boot=s.boot||boot;fails=0;lastOk=Date.now();
 if(s.screen==='stopped'){S=s;V=s.v;offline=false;showLost();return}
 const was=offline;offline=false;if(s.v!==V){V=s.v;S=s;calls(s);render();renderLog()}else if(was)renderLog()}
 catch(e){fails++;if(fails>=3&&!offline){offline=true;renderLog()}}
 showLost()}
// ---------------------------------------------------------------- calibration
// calPts: [{t: target number, p: [x, y] in camera pixels}]. CAL.targets: 0 = bull, 1-20 = where each
// sector wire meets the outer edge of the double ring. CAL.default = the usual 5 to ask for.
let calOpen=false, CAL=null, calCam=null, calPts=[], calW=0, calH=0, calLines=null, calErr=null, calChecked=false,
 drag=null, calNext=null, calSkip=new Set();
const NUDGE=0.35;      // dragging moves a point slower than the finger, for fine adjustment
function calStat(t,c){$('calstat').textContent=t||'';$('calstat').className='status '+(c||'')}
function openCal(){calOpen=true;$('cal').classList.remove('hidden');
 // no page zoom while calibrating: some browsers (Safari) report tap positions and element positions
 // in different units under CSS zoom, so the point landed away from where you tapped
 document.body.classList.add('nozoom');
 ['menu','play','settings'].forEach(id=>$(id).classList.add('hidden'));
 const only=S.screen==='calibrate';$('caldone').classList.toggle('hidden',only);
 $('calfoot').textContent=only?'When every camera is done, stop calibrate on the computer (Ctrl+C) and start play.':'';
 loadCal(false)}
function closeCal(){calOpen=false;drag=null;document.body.classList.remove('nozoom');$('cal').classList.add('hidden');render()}
async function loadCal(keep){
 try{const r=await fetch('/calib/cams',{cache:'no-store'});if(!r.ok)throw 0;CAL=await r.json()}
 catch(e){calStat("Couldn't load the cameras from the computer",'bad');return}
 CAL.min=CAL.min||5;CAL.default=CAL.default||[0,1,2,3,4];
 const cams=CAL.cameras;if(!cams.length){calStat('No cameras','bad');return}
 if(!keep||!cams.some(c=>c.name===calCam)){const c=cams.find(c=>!c.saved)||cams[0];calCam=c.name;
  if(!keep)return selectCam(cams.indexOf(c))}
 calTabs()}
function calTabs(){$('caltabs').innerHTML=CAL.cameras.map((c,i)=>
 `<button class="${c.name===calCam?'on':''}" onclick="selectCam(${i})">${esc(c.name)}${c.saved?' &#10003;':''}</button>`).join('')}
function selectCam(i){const c=CAL.cameras[i];calCam=c.name;drag=null;calLines=null;calErr=null;calNext=null;calSkip=new Set();
 const same=c.points&&c.point_targets&&c.image_size&&c.size&&c.image_size[0]==c.size[0]&&c.image_size[1]==c.size[1];
 calPts=same?c.points.map((p,k)=>({t:c.point_targets[k],p:[p[0],p[1]]})):[];
 calStat(c.saved?'saved '+c.saved+(same?' - these are the saved points':''):'');calTabs();calPic(true)}
function calPic(first){const img=$('calimg');
 img.onload=()=>{calW=img.naturalWidth;calH=img.naturalHeight;$('calsvg').setAttribute('viewBox',`0 0 ${calW} ${calH}`);
  if(first){calZ=0;const n=calPts.length,c=n?[calPts.reduce((a,q)=>a+q.p[0],0)/n/calW,calPts.reduce((a,q)=>a+q.p[1],0)/n/calH]:[0.5,0.6];
   requestAnimationFrame(()=>calZoom(window.innerWidth<700?2:0,c))}else calZoom(0);
  calDraw();if(calPts.length>=CAL.min)calPreview()};
 img.onerror=()=>calStat('No picture from '+calCam+' - is it plugged in?','bad');
 img.src='/calib/frame?cam='+encodeURIComponent(calCam)+'&t='+Date.now()}
function calUsed(t){return calPts.some(q=>q.t===t)}
function calTarget(){   // the point to place next: one picked on the little board, else the next usual one
 if(calNext!==null&&!calUsed(calNext))return calNext;
 const d=CAL.default.find(t=>!calUsed(t)&&!calSkip.has(t));return d===undefined?null:d}
function calU(){const w=$('calsvg').getBoundingClientRect().width;return w?calW/w:1}   // image px per screen px
function calEdge(p){return p[0]<3||p[1]<3||p[0]>calW-3||p[1]>calH-3}
function calDraw(){if(!CAL)return;const u=calU(),n=calPts.length,T=CAL.targets,nx=calTarget();let s='';
 if(calLines&&n>=CAL.min)s+=calLines.map(l=>`<polyline points="${l.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#3cf03c" stroke-width="${1.5*u}"/>`).join('');
 calPts.forEach((q,i)=>{const p=q.p,on=drag&&drag.i===i,c=calEdge(p)?'#e63c3c':'#ffc800';
  s+=`<circle cx="${p[0]}" cy="${p[1]}" r="${(on?14:10)*u}" fill="none" stroke="${c}" stroke-width="${2*u}"/>`+
   `<circle cx="${p[0]}" cy="${p[1]}" r="${1.5*u}" fill="${c}"/>`+
   `<text x="${p[0]+12*u}" y="${p[1]-12*u}" fill="${c}" font-size="${16*u}" font-weight="800" stroke="#000" stroke-width="${3*u}" paint-order="stroke">${i+1}</text>`});
 $('calsvg').innerHTML=s;
 let g=boardSVG([]);
 T.forEach((t,i)=>{const k=calPts.findIndex(q=>q.t===i),x=t.mm[0],y=-t.mm[1];
  if(k>=0)g+=`<circle cx="${x}" cy="${y}" r="22" fill="#5ad25a" stroke="#000" stroke-width="4"/><text x="${x}" y="${y+9}" font-size="26" font-weight="900" text-anchor="middle" fill="#111">${k+1}</text>`;
  else if(i===nx)g+=`<circle cx="${x}" cy="${y}" r="26" fill="#ffc800" stroke="#000" stroke-width="5"/>`;
  else g+=`<circle cx="${x}" cy="${y}" r="${calSkip.has(i)?9:12}" fill="${calSkip.has(i)?'#555':'#9aa0a6'}" stroke="#000" stroke-width="3"/>`});
 $('calguide').innerHTML=g;
 const edge=calPts.findIndex(q=>calEdge(q.p));
 if(nx!==null&&n<CAL.default.length){$('calmsg').textContent=`Tap point ${n+1}: ${T[nx].name}`;
  $('calsub').textContent=nx===0?'The exact centre of the bull.':"Where that wire meets the outside of the double ring. Can't see it in the picture? Tap Can't see it, or pick a different wire point on the little board."}
 else if(n<CAL.min){$('calmsg').textContent=nx!==null?`Tap point ${n+1}: ${T[nx].name}`:`Pick another wire point on the little board (${CAL.min-n} more needed)`;
  $('calsub').textContent='Choose wire points you can see clearly, spread around the board.'}
 else{const q=calErr==null?'':!calChecked?'':calErr<2?'good':calErr<5?'ok':'check the points';
  $('calmsg').innerHTML=calErr==null?n+' points placed':calChecked?`Fit ${calErr} px <span class="${calErr<5?'good':'bad'}">${q}</span>`:'4 points: add a 5th to check the fit';
  $('calsub').textContent='Nudge points until the green wires sit exactly on the real wires, then Save. More points (tap one on the little board) give a better fit.'}
 if(edge>=0)$('calsub').innerHTML=`<span class="bad">Point ${edge+1} is on the edge of the picture: that spot is probably out of view. Undo it, tap Can't see it and pick another point.</span>`;
 $('calskip').disabled=nx===null;$('calsave').disabled=n<CAL.min}
function calPos(e){const r=$('calsvg').getBoundingClientRect();
 return [Math.min(calW,Math.max(0,(e.clientX-r.left)*calW/r.width)),Math.min(calH,Math.max(0,(e.clientY-r.top)*calH/r.height))]}
function calLoupe(){const c=$('loupe');if(!drag){c.classList.add('hidden');return}
 const p=calPts[drag.i].p,box=$('calbox').getBoundingClientRect(),r=$('calsvg').getBoundingClientRect();
 const left=r.left+(p[0]/calW)*r.width-box.left>box.width/2;c.style.left=left?'8px':'';c.style.right=left?'':'8px';
 const g=c.getContext('2d'),S2=c.width,src=36;   // 36 camera pixels across the loupe
 g.imageSmoothingEnabled=false;g.fillStyle='#000';g.fillRect(0,0,S2,S2);
 g.drawImage($('calimg'),p[0]-src/2,p[1]-src/2,src,src,0,0,S2,S2);
 g.strokeStyle='#ffc800';g.lineWidth=2;g.beginPath();g.moveTo(S2/2-30,S2/2);g.lineTo(S2/2+30,S2/2);g.moveTo(S2/2,S2/2-30);g.lineTo(S2/2,S2/2+30);g.stroke();
 c.classList.remove('hidden')}
const ZOOMS=[1,1.5,2,3,4];let calZ=0;
function calZoom(d,center){const bx=$('calbox'),inner=$('calinner'),w0=inner.offsetWidth||1,h0=inner.offsetHeight||1;
 const c=center||[(bx.scrollLeft+bx.clientWidth/2)/w0,(bx.scrollTop+bx.clientHeight/2)/h0];
 calZ=Math.max(0,Math.min(ZOOMS.length-1,calZ+d));
 // 1x = the whole picture fits on screen (it used to be cut off at the bottom on a wide screen)
 const maxH=parseFloat(getComputedStyle(bx).maxHeight)||window.innerHeight*0.65;
 const fit=calW&&calH?Math.min(bx.clientWidth,maxH*calW/calH):bx.clientWidth;
 inner.style.width=Math.round(fit*ZOOMS[calZ])+'px';$('calz').textContent=ZOOMS[calZ]+'x';
 bx.scrollLeft=c[0]*inner.offsetWidth-bx.clientWidth/2;bx.scrollTop=c[1]*inner.offsetHeight-bx.clientHeight/2;calDraw()}
let ptr=null;
(function(){const sv=$('calsvg'),bx=$('calbox');
 sv.addEventListener('pointerdown',e=>{if(!calW||ptr)return;const p=calPos(e),u=calU();let near=-1,bd=24*u;
  calPts.forEach((q,i)=>{const d=Math.hypot(q.p[0]-p[0],q.p[1]-p[1]);if(d<bd){bd=d;near=i}});
  ptr={id:e.pointerId,x:e.clientX,y:e.clientY,p,near,moved:false,sl:bx.scrollLeft,st:bx.scrollTop,o:near>=0?calPts[near].p.slice():null};
  try{sv.setPointerCapture(e.pointerId)}catch(_){}e.preventDefault()});
 sv.addEventListener('pointermove',e=>{if(!ptr||e.pointerId!==ptr.id)return;const dx=e.clientX-ptr.x,dy=e.clientY-ptr.y;
  if(!ptr.moved&&Math.hypot(dx,dy)>6){ptr.moved=true;if(ptr.near>=0){drag={i:ptr.near};calLoupe()}}
  if(!ptr.moved)return;
  if(drag){const u=calU();calPts[drag.i].p=[Math.min(calW,Math.max(0,ptr.o[0]+dx*u*NUDGE)),Math.min(calH,Math.max(0,ptr.o[1]+dy*u*NUDGE))];
   calLines=null;calDraw();calLoupe()}
  else{bx.scrollLeft=ptr.sl-dx;bx.scrollTop=ptr.st-dy}});
 const up=e=>{if(!ptr||e.pointerId!==ptr.id)return;const was=ptr;ptr=null;let changed=!!drag;
  if(!was.moved){const t=calTarget();if(t!==null){calPts.push({t,p:was.p});calNext=null;changed=true;calLines=null;calErr=null}}
  drag=null;calLoupe();calDraw();if(changed&&calPts.length>=CAL.min)calPreview()};
 sv.addEventListener('pointerup',up);sv.addEventListener('pointercancel',up);
 // the little board: tap a point on it to place that one next
 $('calguide').addEventListener('click',e=>{if(!CAL)return;const r=$('calguide').getBoundingClientRect();
  const x=(e.clientX-r.left)/r.width*480-240,y=-((e.clientY-r.top)/r.height*480-240);let best=-1,bd=45;
  CAL.targets.forEach((t,i)=>{const d=Math.hypot(t.mm[0]-x,t.mm[1]-y);if(d<bd){bd=d;best=i}});
  if(best<0||calUsed(best))return;calNext=best;calSkip.delete(best);calDraw()});
 window.addEventListener('resize',()=>{if(calOpen)calZoom(0)})})();
function calSkipIt(){const t=calTarget();if(t===null)return;calSkip.add(t);if(calNext===t)calNext=null;calDraw();
 if(calTarget()===null)calStat("Pick a wire point you can see on the little board - it doesn't matter which",'')}
async function calPost(path){const r=await fetch(path,{method:'POST',body:JSON.stringify({cam:calCam,points:calPts.map(q=>q.p),targets:calPts.map(q=>q.t)})});
 const j=await r.json().catch(()=>({}));if(!r.ok||!j.ok)throw new Error(j.error||'the computer said no');return j}
async function calPreview(){const cam=calCam,n=calPts.length;try{const j=await calPost('/calib/preview');
 if(cam===calCam&&calPts.length===n){calLines=j.lines;calErr=j.err;calChecked=!!j.checked;calDraw()}}catch(e){calStat(e.message,'bad')}}
function calUndo(){calPts.pop();calNext=null;calLines=null;calErr=null;calDraw();if(calPts.length>=CAL.min)calPreview()}
function calReset(){calPts=[];calNext=null;calSkip=new Set();calLines=null;calErr=null;calStat('');calDraw()}
async function calSave(){if(calPts.length<CAL.min)return;
 try{const j=await calPost('/calib/save');calStat(`Saved ${calCam}`+(j.err!=null&&calPts.length>CAL.min?` (fit ${j.err} px)`:''),'good');
  await loadCal(true);const next=CAL.cameras.findIndex(c=>!c.saved);
  if(next>=0)setTimeout(()=>{selectCam(next);calStat('Saved - now '+CAL.cameras[next].name,'good')},900);
  else calStat('All cameras calibrated'+(S.screen==='calibrate'?'':' - tap Done'),'good')}
 catch(e){calStat("Couldn't save: "+e.message,'bad')}}
// ---------------------------------------------------------------- camera setup
let SET={at:-1,cams:[]};
function setScan(){act({type:'setup_scan'})}
function renderSetup(){const st=S.setup||{};
 $('setmsg').textContent=st.message||'';$('setmsg').className='status '+(/^Not saved|No cameras/.test(st.message||'')?'bad':'');
 const busy=!!st.scanning;$('setsave').disabled=busy||!SET.cams.some(c=>c.use);
 if(st.scanned_at===SET.at&&!busy)return;
 if(busy){$('scams').innerHTML='';SET.at=-1;$('setsave').disabled=true;return}
 SET={at:st.scanned_at,cams:(st.cameras||[]).map(c=>({...c}))};
 $('scams').innerHTML=SET.cams.map((c,i)=>`<div class="scam" id="sc${i}"><canvas id="scv${i}" width="320" height="180"></canvas>
  <div class="row"><label><input type="checkbox" id="scu${i}" onchange="setUse(${i},this.checked)"> Use</label>
  <button onclick="setRot(${i})">Turn &#8635;</button></div>
  <div class="small"><span class="nm">${esc(c.cam||'new camera')}</span> &middot; ${esc(c.name)} &middot; ${c.width}x${c.height}${c.builtin?' &middot; this computer&#39;s own camera':''}</div></div>`).join('');
 SET.cams.forEach((c,i)=>{const im=new Image();im.onload=()=>{c.img=im;setDraw(i)};im.src='/setup/frame?index='+c.index+'&t='+st.scanned_at;setDraw(i)});
 $('setsave').disabled=!SET.cams.some(c=>c.use)}
function setDraw(i){const c=SET.cams[i],cv=$('scv'+i);if(!cv)return;const g=cv.getContext('2d');
 $('sc'+i).classList.toggle('on',!!c.use);$('scu'+i).checked=!!c.use;
 g.fillStyle='#000';g.fillRect(0,0,cv.width,cv.height);if(!c.img)return;
 const r=c.rotate%180!==0,iw=r?c.img.height:c.img.width,ih=r?c.img.width:c.img.height,k=Math.min(cv.width/iw,cv.height/ih);
 g.save();g.translate(cv.width/2,cv.height/2);g.rotate(c.rotate*Math.PI/180);
 g.drawImage(c.img,-c.img.width*k/2,-c.img.height*k/2,c.img.width*k,c.img.height*k);g.restore()}
function setUse(i,on){SET.cams[i].use=on;setDraw(i);$('setsave').disabled=!SET.cams.some(c=>c.use)}
function setRot(i){const c=SET.cams[i];c.rotate=(c.rotate+90)%360;setDraw(i)}
function setSave(){act({type:'setup_save',cams:SET.cams.map(c=>({index:c.index,use:!!c.use,rotate:c.rotate}))})}
updV();setInterval(poll,400);poll();
</script></body></html>"""
