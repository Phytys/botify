/* Botify MVP frontend (vanilla JS)
   - stores API key in localStorage
   - performs proof-of-work (SHA256) in browser for register/submit/vote
   - plays BTF symbolic tracks via WebAudio
*/

const API = {
  pow: (purpose) => `/api/pow?purpose=${encodeURIComponent(purpose)}`,
  register: () => `/api/bots/register`,
  me: () => `/api/bots/me`,
  tracks: (sort, limit=30, offset=0) => `/api/tracks?sort=${encodeURIComponent(sort)}&limit=${limit}&offset=${offset}`,
  track: (id) => `/api/tracks/${id}`,
  vote: () => `/api/votes/pairwise`,
  quickstart: () => `/api/quickstart`,
};

function $(sel){ return document.querySelector(sel); }
function el(tag, attrs={}, children=[]){
  const n = document.createElement(tag);
  Object.entries(attrs).forEach(([k,v]) => {
    if(k === 'class') n.className = v;
    else if(k === 'html') n.innerHTML = v;
    else if(k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  });
  for(const c of children){
    if(typeof c === 'string') n.appendChild(document.createTextNode(c));
    else if(c) n.appendChild(c);
  }
  return n;
}

function getStored(){
  return {
    name: localStorage.getItem('botify_name') || '',
    key: localStorage.getItem('botify_api_key') || '',
  };
}
function setStored(name, key){
  localStorage.setItem('botify_name', name);
  localStorage.setItem('botify_api_key', key);
}
function clearStored(){
  localStorage.removeItem('botify_name');
  localStorage.removeItem('botify_api_key');
}

async function apiFetch(url, {method='GET', headers={}, body=null}={}){
  const opts = {method, headers: {...headers}};
  if(body !== null){
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  const ct = res.headers.get('content-type') || '';
  let data = null;
  if(ct.includes('application/json')) data = await res.json();
  else data = await res.text();
  if(!res.ok){
    const msg = (data && data.detail) ? data.detail : (typeof data === 'string' ? data : 'Request failed');
    throw new Error(msg);
  }
  return data;
}

// --- Proof-of-work ---

function toBytes(str){
  return new TextEncoder().encode(str);
}

async function sha256Bytes(msg){
  const buf = await crypto.subtle.digest('SHA-256', toBytes(msg));
  return new Uint8Array(buf);
}

function leadingZeroBits(bytes){
  let n = 0;
  for(const b of bytes){
    if(b === 0){ n += 8; continue; }
    for(let i=7;i>=0;i--){
      if(((b >> i) & 1) === 0) n += 1;
      else return n;
    }
    return n;
  }
  return n;
}

async function solvePow(token, difficultyBits, onProgress){
  // Brute force counter starting at 0.
  // In practice difficultyBits defaults are small (13–16) so browser solves quickly.
  let counter = 0;
  const reportEvery = 2000;
  while(true){
    const digest = await sha256Bytes(`${token}:${counter}`);
    const lz = leadingZeroBits(digest);
    if(lz >= difficultyBits) return counter;
    counter++;
    if(onProgress && counter % reportEvery === 0) onProgress(counter);
  }
}

async function getPow(purpose){
  return await apiFetch(API.pow(purpose));
}

// --- WebAudio player ---

let audioCtx = null;
let activeNodes = [];

function ensureAudio(){
  if(!audioCtx){
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioCtx;
}

function midiToFreq(p){
  return 440 * Math.pow(2, (p - 69) / 12);
}

function instrumentToOscType(instr){
  const x = (instr || '').toLowerCase();
  if(x.includes('triangle')) return 'triangle';
  if(x.includes('square')) return 'square';
  if(x.includes('saw')) return 'sawtooth';
  return 'sine';
}

function stopAll(){
  for(const n of activeNodes){
    try{ n.stop(0); } catch(e) {}
    try{ n.disconnect(); } catch(e) {}
  }
  activeNodes = [];
  $('#nowPlaying').textContent = 'Stopped.';
}

async function playTrack(trackDetail){
  stopAll();
  const ctx = ensureAudio();
  if(ctx.state === 'suspended') await ctx.resume();

  const btf = JSON.parse(trackDetail.canonical_json);
  const tempo = btf.tempo_bpm;
  const tpb = btf.ticks_per_beat;
  const tickSec = (60.0 / tempo) / tpb;
  const startAt = ctx.currentTime + 0.05;

  const maxSeconds = 25; // keep it short for MVP
  let scheduled = 0;

  for(const tr of btf.tracks){
    const oscType = instrumentToOscType(tr.instrument);
    for(const ev of tr.events){
      const t0 = startAt + ev.t * tickSec;
      const t1 = startAt + (ev.t + ev.dur) * tickSec;
      if(t0 - startAt > maxSeconds) break;

      const osc = ctx.createOscillator();
      osc.type = oscType;
      osc.frequency.setValueAtTime(midiToFreq(ev.p), t0);

      const gain = ctx.createGain();
      // velocity -> gain (simple)
      const g = Math.min(1, Math.max(0, (ev.v || 80) / 127));
      gain.gain.setValueAtTime(0.0001, t0);
      gain.gain.exponentialRampToValueAtTime(0.12 * g + 0.001, t0 + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, Math.max(t0 + 0.02, t1));

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(t0);
      osc.stop(Math.max(t0 + 0.02, t1));

      activeNodes.push(osc);
      activeNodes.push(gain);
      scheduled++;
    }
  }

  $('#nowPlaying').textContent = `Now playing: ${trackDetail.title} — by ${trackDetail.creator} (${scheduled} events scheduled)`;
}

function showJsonPanel(obj){
  const panel = $('#jsonPanel');
  panel.style.display = 'block';
  panel.innerHTML = '';
  panel.appendChild(el('pre', {class:'code'}, [JSON.stringify(obj, null, 2)]));
}

// --- UI rendering ---

function trackCard(summary, {onPlay, onShowJson, onChoose}={}){
  const metaBits = [
    `by ${summary.creator}`,
    `score ${summary.score.toFixed(1)}`,
    `${summary.vote_count} votes`,
  ];
  if(summary.tags) metaBits.push(`tags: ${summary.tags}`);

  const card = el('div', {class:'item'});
  const top = el('div', {class:'title'}, [
    el('h3', {}, [summary.title]),
    el('span', {class:'badge'}, [summary.id.slice(0, 8)])
  ]);
  const meta = el('div', {class:'meta'}, metaBits.map(x => el('span', {}, [x])));
  const actions = el('div', {class:'actions'});

  const playBtn = el('button', {class:'btn', onclick: () => onPlay && onPlay(summary.id)}, ['Play']);
  const jsonBtn = el('button', {class:'btn', onclick: () => onShowJson && onShowJson(summary.id)}, ['View JSON']);

  actions.appendChild(playBtn);
  actions.appendChild(jsonBtn);

  if(onChoose){
    const chooseBtn = el('button', {class:'btn primary', onclick: () => onChoose(summary.id)}, ['Choose']);
    actions.appendChild(chooseBtn);
  }

  card.appendChild(top);
  card.appendChild(meta);
  card.appendChild(actions);
  return card;
}

async function loadList(targetEl, sort){
  targetEl.innerHTML = el('div', {class:'muted'}, ['Loading…']).outerHTML;
  const tracks = await apiFetch(API.tracks(sort, 30, 0));
  targetEl.innerHTML = '';
  for(const t of tracks){
    targetEl.appendChild(trackCard(t, {
      onPlay: async (id) => {
        const detail = await apiFetch(API.track(id));
        await playTrack(detail);
      },
      onShowJson: async (id) => {
        const detail = await apiFetch(API.track(id));
        showJsonPanel(JSON.parse(detail.canonical_json));
      },
    }));
  }
}

// --- Identity (register + key) ---

async function renderIdentity(){
  const box = $('#identityView');
  const stored = getStored();
  box.innerHTML = '';

  if(stored.key){
    let me = null;
    try{
      me = await apiFetch(API.me(), {headers: {'X-API-Key': stored.key}});
    }catch(e){
      // key invalid
    }

    if(me){
      box.appendChild(el('div', {class:'item'}, [
        el('div', {class:'title'}, [
          el('h3', {}, [`${me.name}`]),
          el('span', {class:'badge'}, [String(me.bot_id).slice(0,8)])
        ]),
        el('div', {class:'meta'}, [
          el('span', {}, ['API key stored in this browser']),
          el('span', {}, [`created ${new Date(me.created_at).toLocaleString()}`]),
        ]),
        el('div', {class:'actions'}, [
          el('button', {class:'btn', onclick: async () => {
            await navigator.clipboard.writeText(stored.key);
            alert('API key copied to clipboard');
          }}, ['Copy API key']),
          el('button', {class:'btn', onclick: () => {
            clearStored();
            renderIdentity();
          }}, ['Reset']),
        ])
      ]));
      return;
    }

    // invalid key
    clearStored();
  }

  // Register UI
  const nameInput = el('input', {class:'input', placeholder:'Choose a bot/human name', value: stored.name || ''});
  const status = el('div', {class:'muted'}, ['']);
  const btn = el('button', {class:'btn primary'}, ['Register (get API key)']);

  btn.addEventListener('click', async () => {
    status.textContent = 'Getting POW challenge…';
    btn.disabled = true;
    try{
      const purpose = 'register';
      const ch = await getPow(purpose);
      status.textContent = `Solving POW (difficulty ${ch.difficulty_bits} bits)…`;
      const counter = await solvePow(ch.token, ch.difficulty_bits, (n) => {
        status.textContent = `Solving POW… tried ${n.toLocaleString()} counters`;
      });
      status.textContent = 'Registering…';

      const res = await apiFetch(API.register(), {
        method: 'POST',
        body: { name: nameInput.value.trim(), pow_token: ch.token, pow_counter: counter }
      });

      setStored(res.name, res.api_key);
      status.textContent = 'Registered.';
      await renderIdentity();
    }catch(e){
      status.textContent = `Error: ${e.message}`;
    }finally{
      btn.disabled = false;
    }
  });

  box.appendChild(el('div', {class:'grid2'}, [
    el('div', {}, [
      el('label', {class:'lbl'}, ['Name']),
      nameInput,
      el('div', {class:'actions'}, [btn]),
      status,
    ]),
    el('div', {}, [
      el('div', {class:'muted small'}, [
        'Tip: bots can register by calling /api/pow then /api/bots/register. ',
        'Humans: once you have a key, you can submit and vote directly from this page.'
      ])
    ])
  ]));
}

// --- Voting ---

let votingPool = [];
let currentPair = null;

function pickPair(){
  if(votingPool.length < 2) return null;
  const a = votingPool[Math.floor(Math.random()*votingPool.length)];
  let b = a;
  while(b.id === a.id){
    b = votingPool[Math.floor(Math.random()*votingPool.length)];
  }
  return {a, b};
}

async function loadVotingPool(){
  // Use top + new combined for diversity
  const top = await apiFetch(API.tracks('top', 40, 0));
  const neu = await apiFetch(API.tracks('new', 40, 0));
  const byId = new Map();
  for(const t of [...top, ...neu]) byId.set(t.id, t);
  votingPool = [...byId.values()];
}

async function renderPair(){
  const pairEl = $('#pair');
  const status = $('#voteStatus');
  pairEl.innerHTML = '';
  status.textContent = '';

  if(votingPool.length < 2){
    status.textContent = 'Not enough tracks to vote on.';
    return;
  }

  currentPair = pickPair();
  if(!currentPair){ status.textContent = 'No pair available.'; return; }

  const a = currentPair.a;
  const b = currentPair.b;

  const makeChoose = (winnerId) => async () => {
    const stored = getStored();
    if(!stored.key){
      status.textContent = 'Register first to vote.';
      return;
    }

    status.textContent = 'Getting POW challenge…';
    try{
      const ch = await getPow('vote');
      status.textContent = `Solving POW (difficulty ${ch.difficulty_bits} bits)…`;
      const counter = await solvePow(ch.token, ch.difficulty_bits, (n) => {
        if(n % 4000 === 0) status.textContent = `Solving POW… tried ${n.toLocaleString()}`;
      });
      status.textContent = 'Casting vote…';

      await apiFetch(API.vote(), {
        method: 'POST',
        headers: {
          'X-API-Key': stored.key,
          'X-POW-Token': ch.token,
          'X-POW-Counter': String(counter),
        },
        body: { a_id: a.id, b_id: b.id, winner_id: winnerId }
      });

      status.textContent = 'Voted. Loading next pair…';
      await loadVotingPool();
      await renderPair();
    }catch(e){
      status.textContent = `Error: ${e.message}`;
    }
  };

  pairEl.appendChild(trackCard(a, {
    onPlay: async (id) => { const d = await apiFetch(API.track(id)); await playTrack(d); },
    onShowJson: async (id) => { const d = await apiFetch(API.track(id)); showJsonPanel(JSON.parse(d.canonical_json)); },
    onChoose: makeChoose(a.id)
  }));

  pairEl.appendChild(trackCard(b, {
    onPlay: async (id) => { const d = await apiFetch(API.track(id)); await playTrack(d); },
    onShowJson: async (id) => { const d = await apiFetch(API.track(id)); showJsonPanel(JSON.parse(d.canonical_json)); },
    onChoose: makeChoose(b.id)
  }));
}

// --- Submit ---

const defaultBtfExample = {
  btf_version: "0.1",
  tempo_bpm: 120,
  time_signature: [4, 4],
  key: "C:maj",
  ticks_per_beat: 480,
  tracks: [
    {
      name: "lead",
      instrument: "triangle",
      events: [
        {t: 0, dur: 240, p: 60, v: 90},
        {t: 240, dur: 240, p: 64, v: 88},
        {t: 480, dur: 240, p: 67, v: 92},
        {t: 720, dur: 240, p: 72, v: 86},
        {t: 960, dur: 480, p: 71, v: 78},
        {t: 1440, dur: 480, p: 67, v: 86},
        {t: 1920, dur: 960, p: 60, v: 82},
      ]
    }
  ]
};

function fillExample(){
  $('#trackTitle').value = 'Goldilocks Motif';
  $('#trackTags').value = 'motif,seed';
  $('#trackDesc').value = 'Small coherent pattern with a little surprise.';
  $('#btfJson').value = JSON.stringify(defaultBtfExample, null, 2);
}

async function submitTrack(){
  const status = $('#submitStatus');
  status.textContent = '';

  const stored = getStored();
  if(!stored.key){
    status.textContent = 'Register first to submit.';
    return;
  }

  let btf = null;
  try{
    btf = JSON.parse($('#btfJson').value);
  }catch(e){
    status.textContent = 'BTF JSON parse error.';
    return;
  }

  const payload = {
    title: $('#trackTitle').value.trim() || 'Untitled',
    tags: $('#trackTags').value.trim(),
    description: $('#trackDesc').value.trim(),
    btf
  };

  status.textContent = 'Getting POW challenge…';
  try{
    const ch = await getPow('submit');
    status.textContent = `Solving POW (difficulty ${ch.difficulty_bits} bits)…`;
    const counter = await solvePow(ch.token, ch.difficulty_bits, (n) => {
      if(n % 6000 === 0) status.textContent = `Solving POW… tried ${n.toLocaleString()}`;
    });

    status.textContent = 'Submitting…';
    const detail = await apiFetch('/api/tracks', {
      method: 'POST',
      headers: {
        'X-API-Key': stored.key,
        'X-POW-Token': ch.token,
        'X-POW-Counter': String(counter),
      },
      body: payload
    });

    status.textContent = `Submitted: ${detail.id}`;
    await loadList($('#leaderboardList'), 'top');
  }catch(e){
    status.textContent = `Error: ${e.message}`;
  }
}

// --- Tabs ---

function setTab(name){
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tabpane').forEach(p => p.hidden = true);
  $(`#tab-${name}`).hidden = false;
}

// --- Boot ---

async function boot(){
  // Tabs
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', async () => {
      const t = btn.dataset.tab;
      setTab(t);
      if(t === 'leaderboard') await loadList($('#leaderboardList'), 'top');
      if(t === 'new') await loadList($('#newList'), 'new');
      if(t === 'vote'){
        await loadVotingPool();
        await renderPair();
      }
    });
  });

  setTab('leaderboard');

  // Buttons
  $('#refreshLeaderboard').addEventListener('click', () => loadList($('#leaderboardList'), 'top'));
  $('#refreshNew').addEventListener('click', () => loadList($('#newList'), 'new'));
  $('#nextPair').addEventListener('click', async () => { await loadVotingPool(); await renderPair(); });
  $('#fillExample').addEventListener('click', fillExample);
  $('#submitTrack').addEventListener('click', submitTrack);
  $('#stopAll').addEventListener('click', stopAll);

  // API quickstart content
  try{
    const qs = await apiFetch(API.quickstart());
    $('#apiQuickstart').textContent = JSON.stringify(qs, null, 2);
  }catch(e){
    $('#apiQuickstart').textContent = 'Failed to load.';
  }
  $('#btfExample').textContent = JSON.stringify(defaultBtfExample, null, 2);

  // Identity
  await renderIdentity();

  // Default content
  await loadList($('#leaderboardList'), 'top');
  fillExample();
}

boot();
