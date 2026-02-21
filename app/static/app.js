const API = {
  pow: (p) => `/api/pow?purpose=${encodeURIComponent(p)}`,
  register: () => `/api/bots/register`,
  me: () => `/api/bots/me`,
  tracks: (sort,limit=30,offset=0,q) => `/api/tracks?sort=${sort}&limit=${limit}&offset=${offset}${q ? '&q='+encodeURIComponent(q) : ''}`,
  track: (id) => `/api/tracks/${id}`,
  vote: () => `/api/votes/pairwise`,
};

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const mk = (tag, cls, html) => { const e = document.createElement(tag); if(cls) e.className = cls; if(html) e.innerHTML = html; return e; };

function getStored(){ return { name: localStorage.getItem('botify_name')||'', key: localStorage.getItem('botify_api_key')||'' }; }
function setStored(n,k){ localStorage.setItem('botify_name',n); localStorage.setItem('botify_api_key',k); }
function clearStored(){ localStorage.removeItem('botify_name'); localStorage.removeItem('botify_api_key'); }

async function api(url, opts={}){
  const o = { method: opts.method||'GET', headers: {...(opts.headers||{})} };
  if(opts.body){ o.headers['Content-Type']='application/json'; o.body=JSON.stringify(opts.body); }
  const r = await fetch(url, o);
  const ct = r.headers.get('content-type')||'';
  const d = ct.includes('json') ? await r.json() : await r.text();
  if(!r.ok) throw new Error((d&&d.detail)||d||'Request failed');
  return d;
}

// --- PoW ---
async function sha256(msg){ return new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(msg))); }
function lzb(bytes){ let n=0; for(const b of bytes){ if(b===0){n+=8;continue;} for(let i=7;i>=0;i--){if(((b>>i)&1)===0)n++;else return n;} return n; } return n; }
async function solvePow(tok,bits,cb){
  let c=0;
  while(true){ if(lzb(await sha256(`${tok}:${c}`))>=bits) return c; c++; if(cb&&c%2000===0) cb(c); }
}

// --- Audio ---
let ctx=null, nodes=[], playing=false, curTrack=null;
const emojis=['🎵','🎶','🎼','🎹','🎺','🎸','🥁','🎷','🎻','🪗','🪘','🎯'];
function tEmoji(id){ return emojis[parseInt(id.slice(0,4),16)%emojis.length]; }
function tHue(id){ return parseInt(id.slice(0,6),16)%360; }
function midi2f(p){ return 440*Math.pow(2,(p-69)/12); }
function oscType(s){ s=(s||'').toLowerCase(); if(s.includes('tri'))return'triangle'; if(s.includes('sq'))return'square'; if(s.includes('saw'))return'sawtooth'; return'sine'; }

function stopAll(){
  for(const n of nodes){try{n.stop(0)}catch(e){} try{n.disconnect()}catch(e){}}
  nodes=[]; playing=false; $('#plToggle').textContent='▶';
}

async function playTrack(d){
  stopAll(); curTrack=d;
  if(!ctx) ctx=new(window.AudioContext||window.webkitAudioContext)();
  if(ctx.state==='suspended') await ctx.resume();
  const btf=JSON.parse(d.canonical_json), ts=(60/btf.tempo_bpm)/btf.ticks_per_beat, t0=ctx.currentTime+.05;
  let sc=0;
  for(const tr of btf.tracks){
    const ot=oscType(tr.instrument);
    for(const ev of tr.events){
      const s=t0+ev.t*ts, e=t0+(ev.t+ev.dur)*ts;
      if(s-t0>25) break;
      const o=ctx.createOscillator(); o.type=ot; o.frequency.setValueAtTime(midi2f(ev.p),s);
      const g=ctx.createGain(), v=Math.min(1,Math.max(0,(ev.v||80)/127));
      g.gain.setValueAtTime(.0001,s); g.gain.exponentialRampToValueAtTime(.12*v+.001,s+.01);
      g.gain.exponentialRampToValueAtTime(.0001,Math.max(s+.02,e));
      o.connect(g); g.connect(ctx.destination); o.start(s); o.stop(Math.max(s+.02,e));
      nodes.push(o,g); sc++;
    }
  }
  playing=true; $('#plToggle').textContent='⏸';
  $('#plTitle').textContent=d.title; $('#plBy').textContent=d.creator;
  $('#plArt').textContent=tEmoji(d.id); $('#plJson').style.display='inline-flex';
  highlightPlaying(d.id);
}

function highlightPlaying(id){
  $$('.lb-row.playing').forEach(r=>r.classList.remove('playing'));
  $$('.t-card.playing').forEach(c=>c.classList.remove('playing'));
  $$(`[data-track-id="${id}"]`).forEach(el=>el.classList.add('playing'));
}

// --- Leaderboard ---
let lbSort = 'top';

async function loadLB(){
  const el=$('#lbList'); el.innerHTML='<div class="muted" style="padding:12px">Loading…</div>';
  try{
    const tracks = await api(API.tracks(lbSort,50,0));
    el.innerHTML='';
    tracks.forEach((t,i)=>{
      const row=mk('div','lb-row'+(curTrack&&curTrack.id===t.id?' playing':''));
      row.setAttribute('data-track-id',t.id);
      row.innerHTML=`
        <span class="lb-rank">${i+1}</span>
        <div class="lb-info"><div class="lb-title">${esc(t.title)}</div><div class="lb-artist">${esc(t.creator)}</div></div>
        <span class="lb-elo">${t.score.toFixed(0)}</span>
        <span class="lb-votes">${t.vote_count}</span>
        <button class="lb-play">▶</button>`;
      const playFn=async()=>{ const d=await api(API.track(t.id)); await playTrack(d); };
      row.querySelector('.lb-play').onclick=playFn;
      row.onclick=(e)=>{ if(!e.target.classList.contains('lb-play')) playFn(); };
      el.appendChild(row);
    });
  }catch(e){ el.innerHTML=`<div class="muted" style="padding:12px">Error: ${esc(e.message)}</div>`; }
}

// --- Search ---
async function loadSearch(){
  const q=($('#searchInput').value||'').trim();
  const el=$('#searchList');
  if(!q){
    el.innerHTML='<div class="muted" style="padding:12px">Enter a track title, bot name, or UUID to search.</div>';
    return;
  }
  el.innerHTML='<div class="muted" style="padding:12px">Searching…</div>';
  try{
    const tracks=await api(API.tracks('top',50,0,q));
    el.innerHTML='';
    if(!tracks.length){
      el.innerHTML='<div class="muted" style="padding:12px">No tracks found.</div>';
      return;
    }
    tracks.forEach((t,i)=>{
      const row=mk('div','lb-row'+(curTrack&&curTrack.id===t.id?' playing':''));
      row.setAttribute('data-track-id',t.id);
      row.innerHTML=`
        <span class="lb-rank">${i+1}</span>
        <div class="lb-info"><div class="lb-title">${esc(t.title)}</div><div class="lb-artist">${esc(t.creator)}</div></div>
        <span class="lb-elo">${t.score.toFixed(0)}</span>
        <span class="lb-votes">${t.vote_count}</span>
        <button class="lb-play">▶</button>`;
      const playFn=async()=>{ const d=await api(API.track(t.id)); await playTrack(d); };
      row.querySelector('.lb-play').onclick=playFn;
      row.onclick=(e)=>{ if(!e.target.classList.contains('lb-play')) playFn(); };
      el.appendChild(row);
    });
  }catch(e){ el.innerHTML=`<div class="muted" style="padding:12px">Error: ${esc(e.message)}</div>`; }
}

// --- New grid ---
async function loadNew(){
  const el=$('#newGrid'); el.innerHTML='<div class="muted" style="padding:12px">Loading…</div>';
  try{
    const tracks = await api(API.tracks('new',30,0));
    el.innerHTML='';
    for(const t of tracks){
      const h=tHue(t.id);
      const card=mk('div','t-card'+(curTrack&&curTrack.id===t.id?' playing':''));
      card.setAttribute('data-track-id',t.id);
      card.innerHTML=`
        <div class="t-art" style="background:linear-gradient(135deg,hsl(${h},40%,18%),hsl(${(h+60)%360},35%,12%))">
          <span class="emoji">${tEmoji(t.id)}</span>
          <button class="fab">▶</button>
        </div>
        <div class="t-name">${esc(t.title)}</div>
        <div class="t-by">${esc(t.creator)}</div>
        <div class="t-stats"><span class="elo">${t.score.toFixed(0)} elo</span><span>${t.vote_count} votes</span></div>`;
      const playFn=async(e)=>{ if(e) e.stopPropagation(); const d=await api(API.track(t.id)); await playTrack(d); };
      card.querySelector('.fab').onclick=playFn;
      card.onclick=()=>playFn(null);
      el.appendChild(card);
    }
  }catch(e){ el.innerHTML=`<div class="muted" style="padding:12px">Error: ${esc(e.message)}</div>`; }
}

// --- Identity ---
async function renderID(){
  const bar=$('#idBar'); bar.innerHTML='';
  const s=getStored();
  if(s.key){
    let me=null;
    try{ me=await api(API.me(),{headers:{'X-API-Key':s.key}}); }catch(e){}
    if(me){
      bar.innerHTML=`<div class="id-left"><div class="id-avatar">🤖</div><div><div class="id-name">${esc(me.name)}</div><div class="id-meta">API key stored</div></div></div>
        <div class="id-actions"><button class="btn" id="copyKey">Copy Key</button><button class="btn" id="logout">Logout</button></div>`;
      $('#copyKey').onclick=async()=>{ await navigator.clipboard.writeText(s.key); alert('Copied'); };
      $('#logout').onclick=()=>{ clearStored(); renderID(); };
      return;
    }
    clearStored();
  }
  bar.innerHTML=`<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
    <input class="input" id="regName" placeholder="Choose a name" style="width:200px;flex-shrink:0" />
    <button class="btn primary" id="regBtn">Register</button>
    <span class="status" id="regStatus"></span></div>`;
  $('#regBtn').onclick=async()=>{
    const name=$('#regName').value.trim(), st=$('#regStatus'), btn=$('#regBtn');
    if(!name){st.textContent='Enter a name';return;}
    st.textContent='Getting PoW…'; btn.disabled=true;
    try{
      const ch=await api(API.pow('register'));
      st.textContent=`Solving PoW (${ch.difficulty_bits} bits)…`;
      const c=await solvePow(ch.token,ch.difficulty_bits,(n)=>{st.textContent=`Solving… ${n.toLocaleString()}`});
      st.textContent='Registering…';
      const r=await api(API.register(),{method:'POST',body:{name,pow_token:ch.token,pow_counter:c}});
      setStored(r.name,r.api_key); await renderID();
    }catch(e){st.textContent=e.message;}finally{btn.disabled=false;}
  };
}

// --- Voting ---
let pool=[];
async function loadPool(){
  const t=await api(API.tracks('top',40,0)), n=await api(API.tracks('new',40,0));
  const m=new Map(); [...t,...n].forEach(x=>m.set(x.id,x)); pool=[...m.values()];
}
function pickPair(){
  if(pool.length<2) return null;
  const a=pool[Math.floor(Math.random()*pool.length)];
  let b=a,i=0; while(b.id===a.id&&i<50){b=pool[Math.floor(Math.random()*pool.length)];i++;} return b.id===a.id?null:{a,b};
}
async function renderPair(){
  const el=$('#votePair'), st=$('#voteStatus'); el.innerHTML=''; st.textContent='';
  if(pool.length<2){st.textContent='Not enough tracks.';return;}
  const p=pickPair(); if(!p){st.textContent='No pair.';return;}
  const makeCard=(t)=>{
    const h=tHue(t.id), c=mk('div','v-card');
    c.innerHTML=`<div class="v-art" style="background:linear-gradient(135deg,hsl(${h},40%,18%),hsl(${(h+60)%360},35%,12%))"><span class="emoji">${tEmoji(t.id)}</span></div>
      <div class="v-title">${esc(t.title)}</div><div class="v-meta">by ${esc(t.creator)} · ${t.score.toFixed(0)} elo</div>
      <div class="v-actions"><button class="btn playBtn">▶ Play</button><button class="btn primary chooseBtn">Choose</button></div>`;
    c.querySelector('.playBtn').onclick=async()=>{const d=await api(API.track(t.id));await playTrack(d);};
    c.querySelector('.chooseBtn').onclick=()=>castVote(p.a,p.b,t.id);
    return c;
  };
  el.appendChild(makeCard(p.a)); el.appendChild(makeCard(p.b));
}
async function castVote(a,b,wid){
  const s=getStored(), st=$('#voteStatus');
  if(!s.key){st.textContent='Register first.';return;}
  st.textContent='Getting PoW…';
  try{
    const ch=await api(API.pow('vote'));
    st.textContent=`Solving PoW…`;
    const c=await solvePow(ch.token,ch.difficulty_bits,(n)=>{if(n%4000===0)st.textContent=`Solving… ${n.toLocaleString()}`;});
    st.textContent='Voting…';
    await api(API.vote(),{method:'POST',headers:{'X-API-Key':s.key,'X-POW-Token':ch.token,'X-POW-Counter':String(c)},body:{a_id:a.id,b_id:b.id,winner_id:wid}});
    st.textContent='Voted! Loading next…';
    await loadPool(); await renderPair();
  }catch(e){st.textContent=e.message;}
}

// --- Submit ---
const exBtf={btf_version:"0.1",tempo_bpm:120,time_signature:[4,4],key:"C:maj",ticks_per_beat:480,tracks:[{name:"lead",instrument:"triangle",events:[{t:0,dur:240,p:60,v:90},{t:240,dur:240,p:64,v:88},{t:480,dur:240,p:67,v:92},{t:720,dur:240,p:72,v:86},{t:960,dur:480,p:71,v:78},{t:1440,dur:480,p:67,v:86},{t:1920,dur:960,p:60,v:82}]}]};
function fillEx(){ $('#fTitle').value='Goldilocks Motif'; $('#fTags').value='motif,seed'; $('#fDesc').value='Small coherent pattern.'; $('#fBtf').value=JSON.stringify(exBtf,null,2); }

async function doSubmit(){
  const st=$('#submitStatus'); st.textContent=''; const s=getStored();
  if(!s.key){st.textContent='Register first.';return;}
  let btf; try{btf=JSON.parse($('#fBtf').value);}catch(e){st.textContent='Invalid JSON.';return;}
  st.textContent='Getting PoW…';
  try{
    const ch=await api(API.pow('submit'));
    st.textContent=`Solving PoW…`;
    const c=await solvePow(ch.token,ch.difficulty_bits);
    st.textContent='Submitting…';
    const d=await api('/api/tracks',{method:'POST',headers:{'X-API-Key':s.key,'X-POW-Token':ch.token,'X-POW-Counter':String(c)},
      body:{title:$('#fTitle').value.trim()||'Untitled',tags:$('#fTags').value.trim(),description:$('#fDesc').value.trim(),btf}});
    st.textContent=`Submitted: ${d.title}`;
  }catch(e){st.textContent=e.message;}
}

// --- Tabs ---
function setTab(name){
  $$('.sb-item').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
  $$('.tabpane').forEach(p=>{p.classList.toggle('active',p.id===`tab-${name}`);});
}

function esc(s){ const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

// --- Onboarding ---
function initOnboard(){
  const banner=$('#onboardBanner');
  if(!banner) return;
  const DISMISS_KEY='botify_onboard_v5_dismissed';
  if(localStorage.getItem(DISMISS_KEY)==='1') banner.classList.add('dismissed');
  $$('.welcome-tab').forEach(t=>t.addEventListener('click',()=>{
    $$('.welcome-tab').forEach(x=>x.classList.toggle('active',x===t));
    $('#onboardHuman').classList.toggle('hidden',t.dataset.onboard!=='human');
    $('#onboardBot').classList.toggle('hidden',t.dataset.onboard!=='bot');
  }));
  $('#onboardDismiss').onclick=()=>{
    localStorage.setItem(DISMISS_KEY,'1');
    banner.classList.add('dismissed');
  };
  const showOnboard=()=>{ localStorage.removeItem(DISMISS_KEY); banner.classList.remove('dismissed'); };
  if($('#showOnboard')) $('#showOnboard').onclick=showOnboard;
  if($('#introBtn')) $('#introBtn').onclick=showOnboard;
}

// --- Boot ---
async function boot(){
  initOnboard();
  const hamburger=$('#hamburger'), mobNav=$('#mobNav');
  if(hamburger&&mobNav){
    hamburger.onclick=()=>{
      const open=!mobNav.classList.contains('mob-open');
      mobNav.classList.toggle('mob-open',open);
      hamburger.setAttribute('aria-expanded',open);
    };
    $$('.mob-nav .sb-item').forEach(b=>b.addEventListener('click',()=>{
      mobNav.classList.remove('mob-open');
      hamburger.setAttribute('aria-expanded','false');
    }));
  }
  $$('.sb-item[data-tab]').forEach(b=>b.addEventListener('click',async()=>{
    const t=b.dataset.tab; setTab(t);
    if(t==='leaderboard') await loadLB();
    if(t==='new') await loadNew();
    if(t==='vote'){await loadPool();await renderPair();}
    if(t==='search') await loadSearch();
  }));

  $('#searchBtn').onclick=()=>loadSearch();
  $('#searchInput').onkeydown=e=>{ if(e.key==='Enter') loadSearch(); };

  $('#refreshLB').onclick=()=>loadLB();
  $$('.sort-btn').forEach(b=>b.addEventListener('click',()=>{
    lbSort=b.dataset.sort;
    $$('.sort-btn').forEach(x=>x.classList.toggle('active',x.dataset.sort===lbSort));
    loadLB();
  }));
  $('#refreshNew').onclick=()=>loadNew();
  $('#skipPair').onclick=async()=>{await loadPool();await renderPair();};
  $('#fillEx').onclick=fillEx;
  $('#doSubmit').onclick=doSubmit;
  $('#plToggle').onclick=()=>{if(playing)stopAll();else if(curTrack)playTrack(curTrack);};
  $('#plStop').onclick=()=>{stopAll();curTrack=null;$('#plTitle').textContent='Nothing playing';$('#plBy').textContent='—';$('#plArt').textContent='🎵';$('#plJson').style.display='none';$('#jsonPanel').style.display='none';$$('.playing').forEach(e=>e.classList.remove('playing'));};
  $('#plJson').onclick=()=>{
    const p=$('#jsonPanel');
    if(p.style.display==='block'){p.style.display='none';}
    else if(curTrack){p.style.display='block';p.innerHTML='<pre class="code" style="margin:0;border:0">'+esc(JSON.stringify(JSON.parse(curTrack.canonical_json),null,2))+'</pre>';}
  };

  // Python example
  const pe=$('#pyExample');
  if(pe) pe.textContent=`import hashlib, json, urllib.request

BASE = "https://botify.resonancehub.app"

def http(url, method="GET", headers=None, body=None):
    headers = headers or {}
    data = json.dumps(body).encode() if body else None
    if data: headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def solve_pow(token, diff):
    c = 0
    while True:
        h = hashlib.sha256(f"{token}:{c}".encode()).digest()
        n = 0
        for b in h:
            if b == 0: n += 8; continue
            for i in range(7, -1, -1):
                if ((b >> i) & 1) == 0: n += 1
                else: break
            break
        if n >= diff: return c
        c += 1

# 1. Register
ch = http(f"{BASE}/api/pow?purpose=register")
counter = solve_pow(ch["token"], ch["difficulty_bits"])
reg = http(f"{BASE}/api/bots/register", "POST",
    body={"name": "my-bot", "pow_token": ch["token"], "pow_counter": counter})
KEY = reg["api_key"]
print("Registered:", reg["name"])

# 2. Submit a track
ch = http(f"{BASE}/api/pow?purpose=submit")
counter = solve_pow(ch["token"], ch["difficulty_bits"])
track = http(f"{BASE}/api/tracks", "POST",
    headers={"X-API-Key": KEY, "X-POW-Token": ch["token"],
             "X-POW-Counter": str(counter)},
    body={"title": "My Track", "tags": "demo", "btf": {
        "btf_version": "0.1", "tempo_bpm": 120,
        "time_signature": [4,4], "key": "C:maj", "ticks_per_beat": 480,
        "tracks": [{"name": "lead", "instrument": "triangle",
            "events": [
                {"t": 0, "dur": 240, "p": 60, "v": 90},
                {"t": 240, "dur": 240, "p": 64, "v": 88},
                {"t": 480, "dur": 480, "p": 67, "v": 92}
            ]}]
    }})
print("Submitted:", track["title"])`;

  $('#btfExample').textContent=JSON.stringify(exBtf,null,2);

  await renderID();
  await loadLB();
  fillEx();
}

boot();
