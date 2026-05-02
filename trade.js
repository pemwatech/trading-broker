let symbols = [];
let current = null;
let prices = [];
let balance = 0;
const openTrades = new Map();

async function refreshMe(){
  const r = await fetch('/api/me'); if(!r.ok){ location.href='/login'; return; }
  const d = await r.json();
  balance = d.account.balance;
  document.getElementById('bal').textContent = balance.toFixed(2);
}

async function loadSymbols(){
  const r = await fetch('/api/symbols'); symbols = await r.json();
  const wrap = document.getElementById('symbols');
  wrap.innerHTML = symbols.map(s =>
    `<div class="symbol-pill" data-id="${s.id}">${s.id} · ${s.price.toFixed(2)}</div>`).join('');
  wrap.querySelectorAll('.symbol-pill').forEach(el=>{
    el.addEventListener('click', ()=> selectSymbol(el.dataset.id));
  });
  const params = new URLSearchParams(location.search);
  selectSymbol(params.get('symbol') || symbols[0].id);
}

function selectSymbol(id){
  current = id; prices = [];
  document.querySelectorAll('.symbol-pill').forEach(el=>
    el.classList.toggle('active', el.dataset.id===id));
}

async function tickLoop(){
  if(current){
    const r = await fetch(`/api/tick/${current}`); const d = await r.json();
    prices.push(d.price); if(prices.length>120) prices.shift();
    document.getElementById('price').textContent = d.price.toFixed(4);
    drawChart();
  }
  setTimeout(tickLoop, 1000);
}

function drawChart(){
  if(prices.length<2) return;
  const w=600,h=320,pad=10;
  const min=Math.min(...prices), max=Math.max(...prices), span=(max-min)||1;
  const pts = prices.map((p,i)=>{
    const x = pad + (i/(prices.length-1))*(w-2*pad);
    const y = h-pad - ((p-min)/span)*(h-2*pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  document.getElementById('chartPath').setAttribute('d','M'+pts.join(' L'));
}

async function placeTrade(direction){
  const stake = Number(document.getElementById('stake').value);
  const duration = Number(document.getElementById('duration').value);
  const a = document.getElementById('tradeAlert');
  const r = await fetch('/api/trade',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({symbol:current,direction,stake,duration})});
  const d = await r.json();
  if(!r.ok){ a.innerHTML = `<div class="alert err">${d.error}</div>`; return; }
  a.innerHTML = `<div class="alert info">Trade #${d.trade_id} opened @ ${d.entry_price} — settles in ${d.settles_in}s</div>`;
  await refreshMe();
  openTrades.set(d.trade_id, {symbol:current, direction, stake, settle:Date.now()+duration*1000});
  renderOpen();
  setTimeout(()=>settle(d.trade_id), duration*1000 + 200);
}

async function settle(id){
  const r = await fetch(`/api/trade/${id}/settle`,{method:'POST'});
  const d = await r.json();
  openTrades.delete(id); renderOpen();
  await refreshMe();
  const t = d.trade;
  const cls = t.result==='win'?'ok':'err';
  document.getElementById('tradeAlert').innerHTML =
    `<div class="alert ${cls}">Trade #${id} <b>${t.result.toUpperCase()}</b> — exit ${t.exit_price}, payout ${t.payout.toFixed(2)} KES</div>`;
}

function renderOpen(){
  const el = document.getElementById('openTrades');
  if(!openTrades.size){ el.textContent = 'None'; return; }
  el.innerHTML = [...openTrades.entries()].map(([id,t])=>{
    const left = Math.max(0, Math.round((t.settle-Date.now())/1000));
    return `<div>#${id} ${t.symbol} ${t.direction==='rise'?'▲':'▼'} ${t.stake} KES · ${left}s</div>`;
  }).join('');
}
setInterval(renderOpen, 1000);

document.getElementById('btnRise').addEventListener('click', ()=>placeTrade('rise'));
document.getElementById('btnFall').addEventListener('click', ()=>placeTrade('fall'));

refreshMe(); loadSymbols(); tickLoop();
