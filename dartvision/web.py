"""Scoreboard + remote control in a web browser (phone, iPad, TV), so the Pi can run with no screen.

The game loop puts its state here with publish(); the page polls /state and sends taps to /action,
which the game loop picks up with take_actions(). Standard library only.
"""
import json
import queue
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_state = {"v": 0, "data": {}}
_lock = threading.Lock()
_actions = queue.Queue()
_voice_seen = {"t": 0.0}     # last time a page with its voice switched on asked for the state
VOICE_TIMEOUT = 3.0


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
        return {"v": _state["v"], **_state["data"]}


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
            if "voice=1" in self.path:
                _voice_seen["t"] = time.monotonic()
            body = json.dumps(snapshot())
            self._send(200, body, "application/json")
        elif self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/action":
            return self._send(404, "not found", "text/plain")
        n = int(self.headers.get("Content-Length", 0) or 0)
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
@media(min-width:1200px){body{zoom:1.25}}
.kp{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;margin-top:10px}
.kp button{padding:14px 0;font-weight:800;font-size:19px}
.mult{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}
.mult button.on{background:var(--active)}
.banner{text-align:center}
.banner h2{font-size:34px}
.small{font-size:13px;color:var(--dim)}
#vbtn{position:fixed;top:max(8px,env(safe-area-inset-top));right:10px;z-index:4;font-size:14px;padding:8px 12px;background:var(--panel)}
#vbtn.on{background:var(--good);color:#111;font-weight:800}
#flash{position:fixed;inset:0;z-index:9;pointer-events:none;display:flex;align-items:center;justify-content:center;
font-weight:900;font-size:min(40vw,60vh);color:var(--accent);border:24px solid var(--accent);animation:fl .4s steps(2) infinite}
@keyframes fl{0%{background:#ffc80055;border-color:var(--accent);color:var(--accent)}50%{background:transparent;border-color:var(--bad);color:var(--bad)}}
</style></head><body>
<button id="vbtn" onclick="toggleVoice()">Voice off</button>
<div id="flash" class="hidden">180</div>
<div id="menu" class="hidden">
  <h1>dartvision</h1>
  <div class="status" id="mstatus"></div>
  <div class="sub">Game</div><div id="modes" class="list"></div>
  <div class="sub">Options</div><div id="opts"></div>
  <div class="sub">Players</div><div id="players"></div>
  <div class="row"><input id="pname" placeholder="Add a player" maxlength="14" autocomplete="off">
  <button onclick="addPlayer()">Add</button></div>
  <button class="start" onclick="act({type:'start'})">Start</button>
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
function render(){
 const menu=S.screen==='menu';$('menu').classList.toggle('hidden',!menu);$('play').classList.toggle('hidden',menu);
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
async function poll(){try{const r=await fetch('/state'+(voiceOn?'?voice=1':''),{cache:'no-store'});const s=await r.json();
 if(s.v!==V){V=s.v;S=s;calls(s);render()}}catch(e){}}
updV();setInterval(poll,400);poll();
</script></body></html>"""
