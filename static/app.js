/* REDFLAG — prototype front end */
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const api = async (url, body) => {
  try {
    const r = await fetch(url, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const d = await r.json().catch(() => ({}));
    if (!r.ok && !d.error && !d.message) d.error = `Request failed (${r.status})`;
    return d;
  } catch (e) { return {error:'Server not reachable — is app.py running?'}; }
};
const inr = n => '₹' + Math.round(Number(n)).toLocaleString('en-IN');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const kindOf = dec => dec === 'ALLOW' ? 'allow' : dec === 'BLOCK' ? 'block' : 'otp';
const label = dec => dec === 'OTP VERIFY' ? 'VERIFY' : dec === 'BLOCK' ? 'ON HOLD' : dec;
const COLORS = {allow:'#2F5D8C', otp:'#A97A2F', block:'#A3402E'};
const MONO = {family:'JetBrains Mono', size:10};

/* log-scale amount slider: 0..1000 → ₹10..₹5,00,000 */
const sliderToAmt = v => { const a = 10 * Math.pow(50000, v/1000); return a < 1000 ? Math.round(a/10)*10 : a < 10000 ? Math.round(a/100)*100 : Math.round(a/1000)*1000; };
const amtToSlider = a => Math.round(Math.log(Math.max(10, a)/10) / Math.log(50000) * 1000);

let users = [], selected = null, current = null, qrMeta = {is_qr:0, qr_mismatch:0};
let clock = 13, deviceMode = 'usual', otpTimer = null, charts = {}, story = null;

function toast(msg){ const t = $('toast'); t.textContent = msg; t.classList.add('on'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('on'), 2800); }
function mood(m){ window.RedflagJelly && RedflagJelly.setMood(m); }
function chart(key, canvas, cfg){ if (!window.Chart) return null; charts[key]?.destroy(); charts[key] = new Chart(canvas, cfg); return charts[key]; }

/* ---------------- sound + haptics ---------------- */
const Sound = {
  on: (() => { try { return localStorage.getItem('rf-sound') !== 'off'; } catch(e){ return true; } })(),
  ctx: null,
  tone(freq, start, dur, type = 'sine', vol = .08){
    const c = this.ctx, o = c.createOscillator(), g = c.createGain();
    o.type = type; o.frequency.value = freq; o.connect(g); g.connect(c.destination);
    const t = c.currentTime + start;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + .02); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.start(t); o.stop(t + dur + .05);
  },
  play(kind){
    if (kind === 'block' && navigator.vibrate) navigator.vibrate([70, 50, 70]);
    if (!this.on) return;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (kind === 'allow'){ this.tone(660, 0, .25); this.tone(990, .11, .35); }
      else if (kind === 'otp'){ this.tone(520, 0, .22, 'triangle'); this.tone(520, .2, .22, 'triangle'); }
      else if (kind === 'block'){ this.tone(180, 0, .45, 'sawtooth', .05); this.tone(140, .05, .5, 'sine', .08); }
      else if (kind === 'paid'){ this.tone(784, 0, .18); this.tone(988, .09, .18); this.tone(1319, .18, .4); }
      else if (kind === 'tick'){ this.tone(1200, 0, .05, 'sine', .025); }
    } catch(e){}
  },
  toggle(){ this.on = !this.on; try { localStorage.setItem('rf-sound', this.on ? 'on' : 'off'); } catch(e){} paintSound(); if (this.on) this.play('tick'); }
};
function paintSound(){ $('soundBtn').querySelector('span').textContent = Sound.on ? 'on' : 'off'; $('soundBtn').classList.toggle('off', !Sound.on); }
$('soundBtn').onclick = () => Sound.toggle(); paintSound();

/* ---------------- routing ---------------- */
const SCREENS = ['users','pay','analyzing','result','attack','history'];
function go(id, push = true){
  if (id === 'pay' && !selected) id = 'users';
  if ((id === 'result' || id === 'analyzing') && !current) id = selected ? 'pay' : 'users';
  document.querySelectorAll('.screen').forEach(s => s.classList.toggle('active', s.id === id));
  document.querySelectorAll('[data-nav]').forEach(a => a.classList.toggle('on', a.dataset.nav === id || (a.dataset.nav === 'users' && ['pay','analyzing','result'].includes(id))));
  if (push) history.replaceState(null, '', '#' + id);
  if (id === 'history') loadHistory();
  if (id === 'attack') initAttack();
  if (id !== 'result') mood('calm');
  scrollTo({top:0, behavior:'smooth'});
}
document.addEventListener('click', e => { const g = e.target.closest('[data-go]'); if (g){ e.preventDefault(); go(g.dataset.go); } });
document.querySelectorAll('[data-nav]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); go(a.dataset.nav); }));
addEventListener('hashchange', () => { const h = location.hash.slice(1); if (SCREENS.includes(h)) go(h, false); });

/* segmented controls: one handler for every [data-seg] group */
const segHandlers = {};
function setSeg(name, v){
  document.querySelectorAll(`[data-seg="${name}"] button`).forEach(b => b.classList.toggle('on', b.dataset.v === String(v)));
  segHandlers[name]?.(String(v));
}
document.querySelectorAll('[data-seg]').forEach(s => s.querySelectorAll('button').forEach(b => b.addEventListener('click', () => setSeg(s.dataset.seg, b.dataset.v))));
const segVal = name => document.querySelector(`[data-seg="${name}"] button.on`)?.dataset.v;

/* ---------------- 01 users ---------------- */
async function loadUsers(){
  users = await api('/users');
  if (!Array.isArray(users)){ $('userGrid').innerHTML = `<p class="formError">${esc(users.error)}</p>`; users = []; return; }
  $('userGrid').innerHTML = users.map(u => `
    <button class="glass user" data-id="${esc(u.upi_id)}">
      <div class="avatar">${esc(u.name[0])}</div>
      <b>${esc(u.name)}</b><small>${esc(u.upi_id)}</small>
      <div class="meta"><span>${esc(u.role)}</span><span>avg ${inr(u.typical_amount)}</span></div>
    </button>`).join('');
  $('userGrid').insertAdjacentHTML('beforeend', `<button class="glass user addUser" id="addUserBtn" type="button"><div class="plus">+</div><b>New user</b><small>Create an account and pay</small></button>`);
  $('userGrid').querySelectorAll('.user:not(.addUser)').forEach(b => b.onclick = () => choose(b.dataset.id));
  $('addUserBtn').onclick = () => { $('newUserForm').classList.remove('hidden'); $('nuName').focus(); $('newUserForm').scrollIntoView({behavior:'smooth', block:'center'}); };
  const opts = users.map(u => `<option value="${esc(u.upi_id)}">${esc(u.name)} · ${esc(u.role)}</option>`).join('');
  $('histUser').innerHTML = opts; $('atkVictim').innerHTML = opts;
}
$('nuCancel').onclick = () => { $('newUserForm').classList.add('hidden'); $('nuError').textContent = ''; };
$('newUserForm').onsubmit = async e => {
  e.preventDefault();
  const d = await api('/users', {name:$('nuName').value, role:$('nuRole').value});
  if (d.error) return $('nuError').textContent = d.error;
  $('newUserForm').reset(); $('newUserForm').classList.add('hidden'); $('nuError').textContent = '';
  await loadUsers(); toast(`Account created: ${d.upi_id}`); choose(d.upi_id);
};
function choose(id){
  selected = users.find(u => u.upi_id === id);
  if (!selected) return;
  $('profile').innerHTML = `<div class="avatar">${esc(selected.name[0])}</div>
    <div><b>${esc(selected.name)}</b><small>${esc(selected.upi_id)}</small></div>
    <div class="dev"><small>usual device</small><br><small class="mono">${esc(selected.usual_device)}</small></div>`;
  $('sigProfile').textContent = `${selected.role} · avg ${inr(selected.typical_amount)}`;
  $('receiver').value = ''; $('amount').value = ''; $('note').value = ''; $('formError').textContent = '';
  setSeg('clock', '13'); setSeg('device', 'usual'); tab('upi'); resetQr();
  const base = +selected.typical_amount;
  $('quick').innerHTML = [base*0.2, base, base*3, base*10].map(v => Math.max(10, Math.round(v/10)*10))
    .map(v => `<button type="button" data-v="${v}">${inr(v)}</button>`).join('');
  $('quick').querySelectorAll('button').forEach(b => b.onclick = () => { $('amount').value = b.dataset.v; });
  $('histUser').value = selected.upi_id;
  loadPayees(); $('pairCard').classList.add('hidden'); showPair();
  go('pay');
}
async function loadPayees(){
  const [hist, rec] = await Promise.all([api('/history/' + encodeURIComponent(selected.upi_id)), api('/recommend/' + encodeURIComponent(selected.upi_id))]);
  const rows = Array.isArray(hist) ? hist.slice(0, 10) : [];
  const today = new Date().toISOString().slice(0, 10);
  $('recentPayees').innerHTML = rows.length ? rows.map(x => `<button type="button" class="recentRow" data-id="${esc(x.receiver_id)}" data-a="${x.amount}">
      <span class="rName">${esc(x.receiver_id.replace('.demo@okshield', ''))}<small>${esc(x.receiver_id)}</small></span>
      <span class="rAmt">${inr(x.amount)}<small>${x.location === 'Demo' || (x.timestamp || '').startsWith(today) ? 'today' : esc((x.timestamp || '').slice(0, 10))}</small></span></button>`).join('')
    : '<p class="muted">No payments yet — your completed payments will show up here.</p>';
  $('recentPayees').querySelectorAll('.recentRow').forEach(b => b.onclick = () => { $('receiver').value = b.dataset.id; $('amount').value = b.dataset.a; resetQr(); tab('upi'); showPair(); });
  if (rows.some(x => x.location === 'Demo')) tab('recent');
  $('suggest').innerHTML = (Array.isArray(rec) ? rec : []).map(r => `<button type="button" class="sugg" data-id="${esc(r.receiver_id)}" data-a="${r.average_amount}">
      <span>${esc(r.name)}</span><small>${r.times_paid}× · ~${inr(r.average_amount)}</small></button>`).join('') || '<p class="muted">—</p>';
  $('suggest').querySelectorAll('.sugg').forEach(b => b.onclick = () => { $('receiver').value = b.dataset.id; $('amount').value = b.dataset.a; resetQr(); tab('upi'); showPair(); });
}

/* ---------------- 02 pay form ---------------- */
function tab(v){
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x.dataset.tab === v));
  ['upi','recent','qr'].forEach(x => $(x + 'Tab').classList.toggle('hidden', x !== v));
}
document.querySelectorAll('.tab').forEach(x => x.onclick = () => tab(x.dataset.tab));
segHandlers.clock = v => { clock = +v; $('clockLabel').textContent = String(clock).padStart(2,'0') + ':00'; };
segHandlers.device = v => { deviceMode = v; $('sigDevice').textContent = v === 'usual' ? 'Usual phone' : 'Unrecognised phone'; };
$('receiver').addEventListener('input', resetQr);
let pairTimer = null;
$('receiver').addEventListener('input', () => { clearTimeout(pairTimer); pairTimer = setTimeout(showPair, 250); });
async function showPair(){
  if (!selected) return;
  const r = $('receiver').value.trim();
  const d = await api(`/pair_stats?sender=${encodeURIComponent(selected.upi_id)}&receiver=${encodeURIComponent(r)}`);
  if (d.error) return;
  $('limitLine').innerHTML = `Daily UPI limit: <b>${inr(d.left_today)}</b> of ${inr(d.daily_limit)} left today`;
  $('limitLine').classList.toggle('low', d.left_today < d.daily_limit * 0.25);
  if (!/^[\w.\-]+@okshield$/i.test(r)){ $('pairCard').classList.add('hidden'); return; }
  const who = d.receiver ? esc(d.receiver.name) : esc(r);
  const tag = d.receiver ? (d.receiver.is_flagged ? '<span class="pTag bad">flagged account</span>' : d.receiver.account_age_days < 40 ? `<span class="pTag warn">new account · ${Math.round(d.receiver.account_age_days)} days</span>` : '') : '<span class="pTag warn">unknown UPI ID</span>';
  $('pairCard').innerHTML = d.times ? `
      <div class="pHead"><b>${who}</b>${tag}</div>
      <div class="pStats"><div><small>Avg payment</small><b>${inr(d.avg)}</b></div><div><small>Times paid</small><b>${d.times}</b></div><div><small>Largest</small><b>${inr(d.max)}</b></div></div>
      <small class="muted">Last paid ${esc((d.last || '').slice(0,10))} · total ${inr(d.total)}</small>` : `
      <div class="pHead"><b>${who}</b>${tag}</div>
      <small class="muted">First payment from ${esc(selected.name)} to this receiver — no average yet.</small>`;
  $('pairCard').classList.remove('hidden');
}
function resetQr(){
  qrMeta = {is_qr:0, qr_mismatch:0};
  $('qrState').textContent = 'PNG or JPG · we check it before you pay';
  $('qrTab').querySelector('.drop').className = 'drop'; $('qr').value = ''; $('qrWarn').classList.add('hidden');
  $('qrOk').classList.add('hidden'); $('qrPick').querySelectorAll('.qrItem').forEach(x => x.classList.remove('on'));
}

async function scanQrFile(file, autoContinue){
  const drop = $('qrTab').querySelector('.drop'); $('qrState').textContent = 'Reading QR…'; $('qrOk').classList.add('hidden');
  const f = new FormData(); f.append('image', file);
  let d; try { d = await (await fetch('/scan_qr', {method:'POST', body:f})).json(); } catch(err){ d = {error:'Could not reach the server'}; }
  if (d.error){ $('qrState').textContent = d.error; drop.className = 'drop bad'; return; }
  drop.className = 'drop ' + (d.suspicious ? 'bad' : 'good');
  $('qrState').textContent = d.suspicious ? `⚠ ${d.warning}` : `✓ Verified payee: ${d.name}`;
  if (d.receiver) $('receiver').value = d.receiver;
  if (d.amount) $('amount').value = d.amount;
  if (d.receiver) showPair();
  qrMeta = {is_qr:1, qr_mismatch:d.qr_mismatch || 0, suspicious:d.suspicious, warning:d.warning, name:d.name, registered:d.registered_name, receiver:d.receiver};
  if (d.suspicious) return showQrWarn();
  // genuine QR: tell the user it is safe, then carry on with the payment
  $('qrOkText').textContent = `${d.name} · ${d.receiver} — safe to continue payment`;
  $('qrOk').classList.remove('hidden'); Sound.play('allow');
  toast(`QR verified — ${d.name} is safe to pay`);
  if (!autoContinue) return;
  if (!(+$('amount').value > 0)){ $('amount').value = Math.max(10, Math.round(+selected.typical_amount/10)*10); }
  await sleep(1400);
  if (qrMeta.receiver === d.receiver && !qrMeta.suspicious) $('payForm').requestSubmit();
}
$('qr').onchange = e => { const file = e.target.files[0]; if (file) scanQrFile(file, true); };
async function loadQrOptions(){
  const list = await api('/qr_options');
  if (!Array.isArray(list) || !list.length){ $('qrPick').innerHTML = ''; return; }
  $('qrPick').innerHTML = list.map(q => `<button type="button" class="qrItem" data-file="${esc(q.file)}" title="${esc(q.label)}">
      <img src="/static/qr/${esc(q.file)}" alt="QR code: ${esc(q.label)}" loading="lazy"><span>${esc(q.label)}</span></button>`).join('');
  $('qrPick').querySelectorAll('.qrItem').forEach(b => b.onclick = async () => {
    $('qrPick').querySelectorAll('.qrItem').forEach(x => x.classList.toggle('on', x === b));
    const blob = await fetch('/static/qr/' + b.dataset.file).then(r => r.blob());
    scanQrFile(new File([blob], b.dataset.file, {type: blob.type || 'image/png'}), true);
  });
}
function showQrWarn(){
  Sound.play('otp');
  $('qrWarnText').textContent = qrMeta.warning + '. Scammers paste their own QR over a shop\'s code so your money goes to them.';
  $('qrCompare').innerHTML = qrMeta.receiver ? `
      <div><small>QR says</small><b>${esc(qrMeta.name || '—')}</b></div>
      <div><small>UPI ID belongs to</small><b>${esc(qrMeta.registered || 'Unknown account')}</b></div>
      <div class="full"><small>Money would go to</small><b class="mono">${esc(qrMeta.receiver)}</b></div>` :
    `<div class="full"><small>Payload</small><b>Not a valid UPI payment code</b></div>`;
  $('qrAnyway').classList.toggle('hidden', !qrMeta.receiver);
  $('qrWarn').classList.remove('hidden');
}
$('qrCancel').onclick = () => { $('receiver').value = ''; $('amount').value = ''; resetQr(); toast('Payment cancelled — good call'); };
$('qrAnyway').onclick = () => { $('qrWarn').classList.add('hidden'); qrMeta.acknowledged = true; $('payForm').requestSubmit(); };

$('payForm').onsubmit = e => {
  e.preventDefault();
  const receiver = $('receiver').value.trim(), amount = +$('amount').value;
  if (!/^[\w.\-]+@okshield$/i.test(receiver)) return $('formError').textContent = 'Enter a demo receiver ending in @okshield (or pick one from Recent).';
  if (!(amount > 0)) return $('formError').textContent = 'Enter an amount above ₹0.';
  if (qrMeta.suspicious && !qrMeta.acknowledged) return showQrWarn();
  $('formError').textContent = '';
  start({sender_id:selected.upi_id, receiver_id:receiver, amount, demo_hour:clock,
         device_id: deviceMode === 'usual' ? selected.usual_device : 'unknown-phone-' + Math.floor(Math.random()*9000+1000),
         is_qr:qrMeta.is_qr, qr_mismatch:qrMeta.qr_mismatch});
};

/* ---------------- 03 analysing → 04 result ---------------- */
async function scan(promise){
  go('analyzing');
  const items = [...$('checks').children]; items.forEach(li => li.classList.remove('done'));
  const anim = (async () => { for (const li of items){ await sleep(260); li.classList.add('done'); Sound.play('tick'); } })();
  const [d] = await Promise.all([promise, anim, sleep(1500)]);
  return d;
}
async function start(payload, opts = {}){
  current = {body:payload};
  const d = await scan(api('/predict', payload));
  if (d.error){ toast(d.error); current = null; go(selected ? 'pay' : 'users'); if (d.limit){ $('formError').textContent = d.error; showPair(); } return; }
  current = {...d, body:payload, scenario:opts.scenario};
  result(current, true);
  return current;
}

function result(d, fresh = false){
  go('result');
  const k = kindOf(d.decision);
  if (fresh || d._last !== k) Sound.play(k);
  d._last = k;
  mood(k === 'block' ? 'danger' : k === 'otp' ? 'alert' : 'calm');
  $('resultCard').className = 'glass resultCard ' + k;
  $('paidMark').classList.toggle('hidden', !d.paid);
  $('resultType').textContent = d.paid ? 'Payment complete' : k === 'allow' ? 'Low risk · approved' : k === 'otp' ? 'Medium risk · step-up check' : 'High risk · payment on hold';
  $('resultTitle').textContent = d.paid ? 'Paid' : k === 'allow' ? 'Allowed' : k === 'otp' ? 'Verify' : 'On hold';
  const who = users.find(u => u.upi_id === d.body.sender_id);
  $('resultAmount').innerHTML = `${inr(d.body.amount)} from <b>${esc(who ? who.name : d.body.sender_id)}</b> to <b>${esc(d.body.receiver_id)}</b>`;
  $('riskFill').style.width = '0'; $('riskFill').style.background = COLORS[k];
  setTimeout(() => $('riskFill').style.width = Math.max(2, d.risk_score*100) + '%', 60);
  $('riskNum').textContent = `${Math.round(d.risk_score*100)} / 100 · ${d.latency_ms} ms`;
  $('reasons').innerHTML = d.reasons.map(r => `<span>${esc(r)}</span>`).join('');
  $('otpPanel').classList.toggle('hidden', k !== 'otp');
  $('confirm').classList.toggle('hidden', k !== 'allow' || !!d.paid);
  $('bank').classList.toggle('hidden', k !== 'block');
  $('stepUp').classList.toggle('hidden', k !== 'block' || !!d.steppedUp || !!d.burst);
  $('stepNote').classList.toggle('hidden', k !== 'block' || !!d.steppedUp || !!d.burst);
  $('stepUp').disabled = false;
  $('burstPanel').classList.toggle('hidden', !d.burst);
  $('confirm').disabled = false; $('bank').disabled = false;
  if (k === 'otp') otpFlow(d);
  if (d.burst) drawBurst(d.burst);
  renderDetails(d); renderWhy(d); renderUsual(d); initWhatIf(d);
}
const pct = v => v == null ? '—' : Math.round(v*100) + '%';
const yn = v => v == null ? '—' : v ? 'Yes' : 'No';
function renderDetails(d){
  const f = d.features || {};
  const rows = [['Random forest', pct(d.components?.rf)], ['Anomaly (autoencoder)', pct(d.components?.anomaly)], ['Model blend 70/30', pct(d.components?.model)],
    ['Final risk', pct(d.risk_score)],
    ['Payments last 1 h / 24 h', `${f.txn_count_1h ?? '—'} / ${f.txn_count_24h ?? '—'}`], ['Amount vs usual', f.amount_ratio != null ? f.amount_ratio + '×' : '—'],
    ['New receiver', yn(f.is_new_receiver)], ['New device', yn(f.is_new_device)], ['Night-time', yn(f.is_odd_hour)],
    ['Receiver risk score', f.receiver_risk_score], ['Receiver account age', f.receiver_account_age_days != null ? f.receiver_account_age_days + ' days' : '—'],
    ['QR payment / mismatch', `${yn(f.is_qr_payment)} / ${yn(f.qr_mismatch)}`], ['Demo clock', `${String(d.body.demo_hour).padStart(2,'0')}:00`], ['Device', d.body.device_id]];
  if (f.floor_applied) rows.push(['Receiver risk floor', 'Applied — raised the score above the model']);
  if (f.velocity_guard) rows.push(['Velocity guard', 'Triggered — forced block']);
  if (f.qr_stepup) rows.push(['QR step-up', 'Triggered — forced verification']);
  $('engineDetails').innerHTML = `<div class="kv">${rows.map(([a,b]) => `<span>${a}</span><b>${esc(b)}</b>`).join('')}</div>`;
}

/* why bars */
function fmtFeature(key, v){
  if (['is_odd_hour','is_qr_payment','qr_mismatch','is_new_receiver','is_new_device'].includes(key)) return v ? 'yes' : 'no';
  if (key === 'amount') return inr(v);
  if (key.startsWith('amount_')) return (+v).toFixed(1) + '×';
  if (key === 'time_since_last_min') return v >= 9999 ? 'none recent' : v < 60 ? Math.round(v) + ' min' : (v/60).toFixed(1) + ' h';
  if (key === 'receiver_account_age_days') return Math.round(v) + ' days';
  if (key === 'hour') return String(Math.round(v)).padStart(2,'0') + ':00';
  return String(+(+v).toFixed(2));
}
function renderWhy(d){
  const ex = d.explain || [];
  if (!ex.length){ $('whyBars').innerHTML = '<p class="muted">Every signal looks like a typical genuine payment.</p>'; return; }
  const max = Math.max(.15, ...ex.map(e => Math.abs(e.impact)));
  $('whyBars').innerHTML = ex.map(e => {
    const w = Math.abs(e.impact)/max*50, up = e.impact > 0;
    return `<div class="whyRow"><div class="whyLabel"><b>${esc(e.label)}</b><small>${esc(fmtFeature(e.feature, e.value))} · typical ${esc(fmtFeature(e.feature, e.typical))}</small></div>
      <div class="whyBar"><i class="${up ? 'up' : 'down'}" style="${up ? 'left:50%' : 'right:50%'};width:${w}%"></i><em></em></div>
      <span class="whyNum ${up ? 'c-block' : 'c-allow'}">${up ? '+' : '−'}${Math.round(Math.abs(e.impact)*100)}</span></div>`;
  }).join('');
}

/* compared to usual */
async function renderUsual(d){
  const p = await api('/profile/' + encodeURIComponent(d.body.sender_id));
  if (p.error || !p.recent){ $('usualNote').textContent = ''; return; }
  const k = kindOf(d.decision), amts = p.recent.map(r => r.amount), all = [...amts, +d.body.amount];
  const logScale = Math.max(...all) / Math.max(1, Math.min(...all)) > 40;
  chart('usual', $('usualCanvas'), {type:'bar',
    data:{labels:[...p.recent.map(r => r.timestamp.slice(5,10)), 'Now'],
      datasets:[{data:all, backgroundColor:[...amts.map(() => 'rgba(47,93,140,.28)'), COLORS[k]], borderRadius:3, barPercentage:.85, categoryPercentage:.9},
                {type:'line', data:all.map(() => p.median), borderColor:'rgba(28,38,51,.55)', borderDash:[4,4], borderWidth:1, pointRadius:0}]},
    options:{maintainAspectRatio:false, plugins:{legend:{display:false}, tooltip:{callbacks:{label:c => c.datasetIndex ? 'Median ' + inr(c.raw) : inr(c.raw)}}},
      scales:{x:{ticks:{display:false}, grid:{display:false}},
              y:{type:logScale ? 'logarithmic' : 'linear', ticks:{color:'#6B7480', font:MONO, maxTicksLimit:5, callback:v => '₹' + (v >= 1000 ? Math.round(v/1000) + 'k' : v)}, grid:{color:'rgba(28,38,51,.07)'}}}}});
  const ratio = d.body.amount / p.median;
  const who = users.find(u => u.upi_id === d.body.sender_id)?.name || 'This sender';
  $('usualNote').textContent = `${who}'s last ${amts.length} genuine payments (blue) vs this one. ` +
    (ratio >= 1.5 ? `It's ${ratio.toFixed(1)}× the median of ${inr(p.median)}.` : ratio <= .67 ? `It's below the median of ${inr(p.median)}.` : `It's right around the median of ${inr(p.median)}.`) +
    (logScale ? ' (log scale)' : '');
}

/* what-if */
let wiTimer = null, wiBody = null;
function initWhatIf(d){
  const u = users.find(x => x.upi_id === d.body.sender_id);
  wiBody = {...d.body, token:d.token};
  $('wiAmt').value = amtToSlider(d.body.amount);
  $('wiAmtLabel').textContent = inr(d.body.amount);
  setSegSilent('wiClock', +d.body.demo_hour < 6 ? '3' : '13');
  setSegSilent('wiDevice', u && d.body.device_id === u.usual_device ? 'usual' : 'new');
  paintWhatIf(d.risk_score, d.decision, d.reasons[0]);
}
function setSegSilent(name, v){ document.querySelectorAll(`[data-seg="${name}"] button`).forEach(b => b.classList.toggle('on', b.dataset.v === v)); }
function paintWhatIf(risk, dec, why){
  const k = kindOf(dec);
  $('wiDecision').textContent = label(dec); $('wiDecision').className = 'wiDecision c-' + k;
  $('wiFill').style.width = Math.max(2, risk*100) + '%'; $('wiFill').style.background = COLORS[k];
  $('wiRisk').textContent = Math.round(risk*100); $('wiReason').textContent = why || '';
}
function whatIfChanged(){
  if (!wiBody) return;
  const amt = sliderToAmt(+$('wiAmt').value); $('wiAmtLabel').textContent = inr(amt);
  const u = users.find(x => x.upi_id === wiBody.sender_id);
  const body = {...wiBody, amount:amt, demo_hour:+(segVal('wiClock') || 13),
    device_id: segVal('wiDevice') === 'usual' && u ? u.usual_device : (wiBody.device_id !== u?.usual_device ? wiBody.device_id : 'unknown-phone-wi')};
  clearTimeout(wiTimer);
  wiTimer = setTimeout(async () => { const r = await api('/whatif', body); if (!r.error) paintWhatIf(r.risk_score, r.decision, r.reasons[0]); }, 110);
}
$('wiAmt').addEventListener('input', whatIfChanged);
segHandlers.wiClock = whatIfChanged; segHandlers.wiDevice = whatIfChanged;

/* OTP */
function otpFlow(d){
  $('sms').querySelector('p').textContent = d.simulated_sms;
  $('otpError').textContent = '';
  $('otpInputs').innerHTML = Array.from({length:6}, () => '<input maxlength="1" inputmode="numeric" autocomplete="one-time-code">').join('');
  const boxes = [...$('otpInputs').querySelectorAll('input')];
  boxes.forEach((b, i) => {
    b.oninput = () => { b.value = b.value.replace(/\D/g,''); if (b.value && boxes[i+1]) boxes[i+1].focus(); if (boxes.every(x => x.value)) $('verify').focus(); };
    b.onkeydown = e => { if (e.key === 'Backspace' && !b.value && boxes[i-1]) boxes[i-1].focus(); if (e.key === 'Enter') $('verify').click(); };
    b.onpaste = e => { const t = (e.clipboardData.getData('text').match(/\d/g) || []).slice(0,6); if (t.length){ e.preventDefault(); t.forEach((c,j) => boxes[j] && (boxes[j].value = c)); boxes[Math.min(t.length,5)].focus(); } };
  });
  if (!story) setTimeout(() => boxes[0].focus({preventScroll:true}), 300);
  let left = d.otp_ttl || 60; clearInterval(otpTimer);
  const tick = () => { $('timer').textContent = left > 0 ? `Code expires in 00:${String(left).padStart(2,'0')} · 3 attempts` : 'Code expired — verifying now will block the payment'; left--; };
  tick(); otpTimer = setInterval(() => { tick(); if (left < -1) clearInterval(otpTimer); }, 1000);
}
async function verifyOtp(){
  const otp = [...$('otpInputs').querySelectorAll('input')].map(x => x.value).join('');
  if (otp.length < 6) return $('otpError').textContent = 'Enter all 6 digits.';
  $('verify').disabled = true;
  const d = await api('/verify_otp', {token:current.token, otp});
  $('verify').disabled = false;
  if (d.ok){ clearInterval(otpTimer); current.decision = 'ALLOW'; current.reasons = ['Identity confirmed with a one-time code', ...current.reasons]; result(current); toast('Code verified — you can complete the payment'); }
  else if (d.decision === 'BLOCK'){ clearInterval(otpTimer); current.decision = 'BLOCK'; current.reasons = [d.message, ...current.reasons]; result(current); }
  else { $('otpError').textContent = d.message; [...$('otpInputs').querySelectorAll('input')].forEach(x => x.value = ''); $('otpInputs').querySelector('input').focus(); }
}
$('verify').onclick = verifyOtp;
async function autoOtp(){
  const code = (current?.simulated_sms?.match(/\d{6}/) || [])[0]; if (!code) return;
  const boxes = [...$('otpInputs').querySelectorAll('input')];
  for (let i = 0; i < 6; i++){ boxes[i].value = code[i]; Sound.play('tick'); await sleep(140); }
  await sleep(300); await verifyOtp();
}
async function completePayment(){
  $('confirm').disabled = true;
  const d = await api('/confirm', {token:current.token});
  if (d.error){ toast(d.error); $('confirm').disabled = false; return; }
  current.paid = true; result(current); Sound.play('paid');
  if (selected) loadPayees();
  toast(`${inr(current.body.amount)} sent to ${current.body.receiver_id}`);
}
$('confirm').onclick = completePayment;
$('stepUp').onclick = async () => {
  $('stepUp').disabled = true;
  const d = await api('/step_up', {token:current.token});
  if (d.error){ toast(d.error); $('stepUp').disabled = false; return; }
  current.decision = 'OTP VERIFY'; current.steppedUp = true;
  current.simulated_sms = d.simulated_sms; current.otp_ttl = d.otp_ttl;
  current.reasons = ['Payment was on hold — owner chose to continue, verifying with a one-time code', ...current.reasons];
  result(current); toast('Code sent to your registered phone');
};
$('bank').onclick = () => { $('bank').disabled = true; toast(`Reported (simulated) · ref RF-${Date.now().toString(36).toUpperCase().slice(-6)}`); };
$('again').onclick = () => { const s = current?.body?.sender_id; current = null; if (s && users.find(u => u.upi_id === s)) choose(s); else go('users'); };

/* ---------------- scenarios + story ---------------- */
const ORDER = ['normal','unusual','social','spike','takeover','burst'];
const EXPECT = {normal:'allow', unusual:'otp', social:'otp', spike:'block', takeover:'block', burst:'block'};
const STORY = {
  normal:  'Vennela buys lunch at the campus canteen — her usual amount, her usual phone, lunchtime. Nothing stands out, so it goes straight through.',
  unusual: 'College fees: ₹18,000, far above anything she normally pays. Odd but genuine — so instead of blocking, REDFLAG texts her a one-time code. She enters it and pays.',
  social:  'A caller posing as "Refund Support" talks her into sending ₹2,500. The receiver is watch-listed and only weeks old, so the payment is paused for a code check.',
  spike:   '₹95,000 to a gift-voucher account created four days ago — about 300× her normal. Put on hold.',
  takeover:'Someone with her password tries ₹90,000 at 2 AM from a phone she has never used. Put on hold.',
  burst:   'A scammer fires five quick ₹500 payments. The first ones are challenged; once the pattern is clear, the velocity guard blocks the rest.'
};
let scenarioData = {};
async function loadScenarios(){
  scenarioData = await api('/scenarios');
  const entries = ORDER.filter(k => scenarioData[k]).map(k => [k, scenarioData[k]]);
  $('scenarioGrid').innerHTML = entries.map(([k, v], i) => `
    <button class="glass scn" data-s="${k}"><span class="n">${String(i+1).padStart(2,'0')}</span>
      <b>${esc(v.title)}</b><small>${esc(v.story)}</small>
      <span class="exp c-${EXPECT[k]}">Expected · ${EXPECT[k] === 'otp' ? 'verify' : EXPECT[k]}</span></button>`).join('') + `
    <a class="glass scn" href="/demo-qr" target="_blank" style="text-decoration:none"><span class="n">${String(entries.length+1).padStart(2,'0')}</span>
      <b>Tampered QR</b><small>Download a tampered code from the gallery, then upload it under Pay → Scan QR.</small>
      <span class="exp c-block">Expected · flagged before paying ↗</span></a>`;
  $('scenarioGrid').querySelectorAll('button.scn').forEach(b => b.onclick = () => runScenario(b.dataset.s));
}
async function runScenario(name){
  const p = scenarioData[name]; if (!p) return;
  if (!users.length) await loadUsers();
  selected = users.find(u => u.upi_id === p.sender_id) || selected;
  await api('/admin/reset_live', {sender_id:p.sender_id});        // isolate this run
  const payload = {sender_id:p.sender_id, receiver_id:p.receiver_id, amount:p.amount, device_id:p.device_id, demo_hour:p.demo_hour, demo:1};
  if (name !== 'burst') return start(payload, {scenario:name});
  current = {body:payload};
  const steps = [];
  const d = await scan((async () => {
    let last;
    for (let i = 0; i < 5; i++){ last = await api('/predict', payload); if (last.error) break; steps.push({risk:last.risk_score, decision:last.decision}); }
    return last;
  })());
  if (d.error){ toast(d.error); return; }
  current = {...d, body:payload, burst:steps, scenario:name};
  result(current, true);
}
function drawBurst(steps){
  $('burstSteps').innerHTML = steps.map((s, i) => `<span class="bg-${kindOf(s.decision)}">#${i+1} ${label(s.decision)}</span>`).join('');
  chart('burst', $('burstCanvas'), {type:'line',
    data:{labels:steps.map((_, i) => '#' + (i+1)), datasets:[{data:steps.map(s => Math.round(s.risk*100)), borderColor:'#1C2633', borderWidth:2, tension:.35, fill:false,
      pointRadius:5, pointBackgroundColor:steps.map(s => COLORS[kindOf(s.decision)]), pointBorderColor:'#F1ECE3'}]},
    options:{maintainAspectRatio:false, plugins:{legend:{display:false}}, animation:{duration:900},
      scales:{y:{min:0, max:100, ticks:{color:'#6B7480', font:MONO}, grid:{color:'rgba(28,38,51,.08)'}}, x:{ticks:{color:'#6B7480', font:MONO}, grid:{display:false}}}}});
}
async function playStory(){
  if (story) return;
  const run = story = {};
  $('story').classList.remove('hidden');
  for (let i = 0; i < ORDER.length; i++){
    if (story !== run) return;
    const name = ORDER[i], s = scenarioData[name];
    $('storyStep').textContent = `${i+1}/${ORDER.length}`; $('storyTitle').textContent = s.title; $('storyText').textContent = STORY[name];
    $('storyProg').style.width = (i/ORDER.length*100) + '%';
    await runScenario(name);
    if (story !== run) return;
    if (name === 'unusual' && current?.decision === 'OTP VERIFY'){
      await sleep(2200); if (story !== run) return; await autoOtp();
      await sleep(900); if (story !== run) return; if (current.decision === 'ALLOW') await completePayment();
    }
    await sleep(name === 'burst' ? 7000 : 5200);
  }
  if (story !== run) return;
  $('storyProg').style.width = '100%'; story = null;
  await sleep(500); $('story').classList.add('hidden'); toast('That\'s the story — here\'s what the engine decided'); go('dashboard');
}

/* ---------------- attack mode ---------------- */
let atk = {stolen:0, stopped:0, count:0, victim:null};
segHandlers.atkClock = () => {}; segHandlers.atkDevice = () => {};
function initAttack(){
  if (!atk.victim){ atk.victim = $('atkVictim').value; }
  $('atkAmtLabel').textContent = inr(sliderToAmt(+$('atkAmt').value));
}
$('atkAmt').addEventListener('input', () => $('atkAmtLabel').textContent = inr(sliderToAmt(+$('atkAmt').value)));
$('atkVictim').onchange = () => resetAttack(true);
async function resetAttack(silent){
  atk = {stolen:0, stopped:0, count:0, victim:$('atkVictim').value};
  await api('/admin/reset_live', {sender_id:atk.victim});
  paintAttack(); $('atkLog').innerHTML = '<p class="muted">Your attempts will show up here.</p>';
  if (!silent) toast('Attack reset');
}
$('atkReset').onclick = () => resetAttack(false);
function paintAttack(){ $('atkStolen').textContent = inr(atk.stolen); $('atkStopped').textContent = inr(atk.stopped); $('atkCount').textContent = atk.count; }
$('atkGo').onclick = async () => {
  const victim = users.find(u => u.upi_id === $('atkVictim').value); if (!victim) return;
  if (atk.victim !== victim.upi_id) await resetAttack(true);
  let target = $('atkTarget').value;
  if (target === '__fav__'){ const rec = await api('/recommend/' + encodeURIComponent(victim.upi_id)); target = rec?.[0]?.receiver_id || 'chaiwala.demo@okshield'; }
  const amount = sliderToAmt(+$('atkAmt').value);
  const body = {sender_id:victim.upi_id, receiver_id:target, amount, demo_hour:+segVal('atkClock'),
                device_id: segVal('atkDevice') === 'usual' ? victim.usual_device : 'attacker-phone-7731', demo:1};
  $('atkGo').disabled = true;
  const d = await api('/predict', body);
  $('atkGo').disabled = false;
  if (d.error) return toast(d.error);
  const k = kindOf(d.decision); atk.count++;
  let outcome;
  if (k === 'allow'){ await api('/confirm', {token:d.token}); atk.stolen += amount; outcome = 'Money gone'; Sound.play('block'); mood('danger'); }
  else { atk.stopped += amount; outcome = k === 'otp' ? 'OTP sent to victim — you can\'t pass it'  : 'Put on hold'; Sound.play(k === 'otp' ? 'otp' : 'allow'); mood(k === 'otp' ? 'alert' : 'calm'); }
  paintAttack();
  if (atk.count === 1) $('atkLog').innerHTML = '';
  $('atkLog').insertAdjacentHTML('afterbegin', `<div class="feedrow"><span class="tag bg-${k}">${label(d.decision)}</span>
    <div>${inr(amount)} → ${esc(target)}<small>${esc(outcome)} · ${esc(d.reasons[0])}</small></div><span class="amt2">${Math.round(d.risk_score*100)}</span></div>`);
  if (k === 'allow') toast(`${inr(amount)} got through — try to find what made it look normal`);
};

/* ---------------- history ---------------- */
$('histUser').onchange = loadHistory;
async function loadHistory(){
  const id = $('histUser').value || selected?.upi_id || users[0]?.upi_id; if (!id) return;
  $('histUser').value = id;
  const u = users.find(x => x.upi_id === id);
  $('histTitle').textContent = (u ? u.name : 'Account') + "'s history";
  const d = await api('/activity/' + encodeURIComponent(id));
  if (d.error) return toast(d.error);
  const t = d.totals || {}, tried = d.attempts || [];
  const blocked = tried.filter(a => a.decision === 'BLOCK').length;
  $('histKpis').innerHTML = [[t.n || 0, 'Recorded payments', ''], [inr(t.a || 0), 'Average payment', ''], [t.f || 0, 'Known fraud in history', 'c-block'], [`${tried.length} / ${blocked}`, 'Demo tries / on hold', 'c-otp']]
    .map(([v,l,c]) => `<div class="glass"><b class="${c}">${v}</b><small>${l}</small></div>`).join('');
  $('histAttempts').innerHTML = tried.length ? tried.map(a => `<div class="feedrow"><span class="tag bg-${kindOf(a.decision)}">${label(a.decision)}${a.confirmed && a.decision !== 'BLOCK' ? ' ✓' : ''}</span>
      <div>${esc(a.name)}<small>${esc(a.reasons)}</small></div><span class="amt2">${inr(a.amount)}</span>
      <time>${new Date(a.created_at*1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</time></div>`).join('')
    : '<p class="muted">Nothing tried yet for this account.</p>';
  $('histPayments').innerHTML = (d.payments || []).map(p => {
    const tag = p.is_fraud ? '<span class="tag bg-block">FRAUD</span>' : p.location === 'Demo' ? '<span class="tag bg-allow">DEMO</span>' : '<span class="tag ghostTag">PAID</span>';
    return `<div class="feedrow">${tag}<div>${esc(p.name)}<small>${esc(p.timestamp.slice(0,16))} · ${esc(p.device_id)}</small></div><span class="amt2">${inr(p.amount)}</span><time></time></div>`;
  }).join('') || '<p class="muted">No payments.</p>';
}

/* ---------------- how it works ---------------- */
async function loadHow(){
  const m = await api('/admin/model');
  if (!m.rows || !m.rows.length){ $('howNote').textContent = m.note || 'No report yet — run evaluate.py.'; return; }
  const best = m.rows.find(r => r.System.includes('OTP')) || m.rows[m.rows.length-1];
  $('howKpis').innerHTML = [[p1(best.Precision), 'Precision', 'c-allow'], [p1(best.Recall), 'Fraud caught', 'c-allow'], [best['False blocks'], 'Genuine payments blocked', 'c-otp'], [best['Missed fraud'], 'Fraud missed', 'c-block']]
    .map(([v,l,c]) => `<div class="glass"><b class="${c}">${v}</b><small>${l}</small></div>`).join('');
  $('howTable').innerHTML = modelTable(m.rows);
  $('howNote').textContent = `Tested on the most recent 20% of transactions, which the model never saw in training · report generated ${m.generated}.`;
  $('howMix').innerHTML = m.mix.length ? `<table><tr><th>Decision</th><th>Fraud</th><th>Genuine</th></tr>${m.mix.map(r => `<tr><td>${esc(label(r.decision))}</td><td>${r.fraud}</td><td>${r.genuine}</td></tr>`).join('')}</table>
    <p class="muted">The verify tier catches fraud the model isn't sure about while letting genuine-but-odd payments through after a code.</p>` : '<p class="muted">Run evaluate.py to see this.</p>';
  $('howCharts').innerHTML = m.charts.map(c => `<figure><img src="/reports/${c}?t=${Date.now()}" alt="${c === 'roc.png' ? 'ROC curve' : 'Precision–recall curve'}"><figcaption>${c === 'roc.png' ? 'ROC curve — how well risk separates fraud from genuine' : 'Precision vs recall at every threshold'}</figcaption></figure>`).join('');
}
const p1 = v => (v*100).toFixed(1) + '%';
const modelTable = rows => `<table><tr><th>System</th><th>Precision</th><th>Recall</th><th>F1</th><th>False +</th><th>Missed</th></tr>${
  rows.map(r => `<tr class="${r.System.includes('OTP') ? 'best' : ''}"><td>${esc(r.System)}</td><td>${p1(r.Precision)}</td><td>${p1(r.Recall)}</td><td>${(+r.F1).toFixed(3)}</td><td>${r['False blocks']}</td><td>${r['Missed fraud']}</td></tr>`).join('')}</table>`;

/* ---------------- dashboard ---------------- */
async function dash(){
  const [d, m] = await Promise.all([api('/admin/stats'), api('/admin/model')]);
  if (d.error) return toast(d.error);
  const c = d.counts || {}, total = (c.ALLOW||0) + (c['OTP VERIFY']||0) + (c.BLOCK||0);
  $('kpis').innerHTML = [[c.ALLOW||0,'Allowed','c-allow'], [c['OTP VERIFY']||0,'Verified / pending','c-otp'], [c.BLOCK||0,'On hold','c-block'], [(d.avg_latency_ms||0) + ' ms','Avg scoring time','']]
    .map(([v,l,cl]) => `<div class="glass"><b class="${cl}">${v}</b><small>${l}</small></div>`).join('');
  $('donutEmpty').classList.toggle('hidden', total > 0);
  $('donut').style.display = total ? '' : 'none';
  if (total) chart('donut', $('donut'), {type:'doughnut',
    data:{labels:['Allow','Verify','On hold'], datasets:[{data:[c.ALLOW||0, c['OTP VERIFY']||0, c.BLOCK||0], backgroundColor:[COLORS.allow, COLORS.otp, COLORS.block], borderColor:'#EEE9E0', borderWidth:3}]},
    options:{cutout:'68%', plugins:{legend:{position:'bottom', labels:{color:'#1C2633', font:MONO, boxWidth:10}}}}});
  if (m.rows && m.rows.length){
    $('modelTable').innerHTML = modelTable(m.rows);
    $('modelNote').textContent = `Most recent 20% of ${d.dataset ? d.dataset.transactions.toLocaleString('en-IN') : ''} transactions, never seen in training · generated ${m.generated}`;
  } else { $('modelTable').innerHTML = ''; $('modelNote').textContent = m.note || 'No report yet.'; }
  $('feed').innerHTML = d.feed.length ? d.feed.map(x => {
    const k = kindOf(x.decision), who = users.find(u => u.upi_id === x.sender_id);
    return `<div class="feedrow"><span class="tag bg-${k}">${label(x.decision)}</span>
      <div>${esc(who ? who.name : x.sender_id)} → ${esc(x.receiver_id)}<small>${esc(x.reasons)}</small></div>
      <span class="amt2">${inr(x.amount)}</span><time>${new Date(x.created_at*1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</time></div>`; }).join('')
    : '<p class="muted">Nothing yet — every payment you try shows up here.</p>';
}

/* ---------------- boot ---------------- */
(async () => {
  await Promise.all([loadUsers(), loadQrOptions()]);
  const h = location.hash.slice(1);
  go(SCREENS.includes(h) ? h : 'users', false);
})();
