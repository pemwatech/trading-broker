async function load(){
  const r = await fetch('/api/me'); if(!r.ok){ location.href='/login'; return; }
  const d = await r.json();
  const stats = document.getElementById('stats');
  stats.innerHTML = `
    <div class="stat"><div class="label">Balance</div>
      <div class="value">${d.account.balance.toFixed(2)} <span class="muted" style="font-size:14px">${d.account.currency}</span></div></div>
    <div class="stat"><div class="label">Account type</div>
      <div class="value" style="text-transform:capitalize">${d.account.account_type}</div></div>
    <div class="stat"><div class="label">KYC status</div>
      <div class="value">
        <span class="badge ${d.kyc_status==='approved'?'ok':d.kyc_status==='pending'?'warn':'muted'}">${d.kyc_status.replace('_',' ')}</span>
      </div></div>
    <div class="stat"><div class="label">Total trades</div>
      <div class="value">${d.trades.length}</div></div>`;

  const tx = document.getElementById('tx');
  tx.innerHTML = d.transactions.length ? `<table class="table"><thead><tr>
    <th>Date</th><th>Type</th><th>Method</th><th class="text-right">Amount</th></tr></thead><tbody>
    ${d.transactions.map(t=>`<tr>
      <td>${t.created_at.slice(0,16)}</td>
      <td><span class="badge ${t.type==='deposit'?'ok':t.type==='trade'?'muted':'warn'}">${t.type}</span></td>
      <td class="muted">${t.method||'-'}</td>
      <td class="text-right ${t.amount>=0?'success':'danger'}" style="font-family:var(--font-mono)">${t.amount>=0?'+':''}${t.amount.toFixed(2)}</td>
    </tr>`).join('')}</tbody></table>` : '<p class="muted">No transactions yet.</p>';

  const tr = document.getElementById('trades');
  tr.innerHTML = d.trades.length ? `<table class="table"><thead><tr>
    <th>Symbol</th><th>Dir</th><th>Stake</th><th>Result</th></tr></thead><tbody>
    ${d.trades.map(t=>`<tr>
      <td>${t.symbol}</td>
      <td>${t.direction==='rise'?'▲':'▼'}</td>
      <td style="font-family:var(--font-mono)">${t.stake.toFixed(2)}</td>
      <td><span class="badge ${t.result==='win'?'ok':t.result==='lose'?'bad':'warn'}">${t.result}</span></td>
    </tr>`).join('')}</tbody></table>` : '<p class="muted">No trades yet.</p>';
}
load();
