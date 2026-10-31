(() => {
  const connect = document.querySelector('#connect-openrouter');
  const status = document.querySelector('#openrouter-connection-status');
  const refresh = document.querySelector('#refresh-openrouter');
  const total = document.querySelector('#openrouter-total');
  const daily = document.querySelector('#openrouter-daily');
  const money = value => typeof value === 'number' ? `$${value.toFixed(4)}` : '—';
  async function load() {
    refresh.disabled = true;
    try {
      const response = await fetch('/api/connections/openrouter', {cache:'no-store'});
      if (!response.ok) throw new Error();
      const data = await response.json();
      connect.textContent = data.connected ? '已連接您的 OpenRouter' : '連接您的 OpenRouter';
      connect.disabled = data.connected;
      status.textContent = data.error || (data.connected ? '模型請求使用您自己的 OpenRouter 額度。' : '登入 DIJI 後，授權連接您自己的模型額度。');
      total.textContent = money(data.usage);
      daily.textContent = data.connected ? `今日使用：${money(data.usage_daily)} USD · OpenRouter 用量可能稍有延遲` : '連接後顯示用量';
    } catch { status.textContent = '無法讀取連接狀態，請稍後更新。'; }
    finally { refresh.disabled = false; }
  }
  connect.addEventListener('click', () => {
    if (!requireLogin()) return;
    window.location.assign('/api/connections/openrouter/start');
  });
  refresh.addEventListener('click', load);
  document.querySelectorAll('[data-auth-logout]').forEach(button => button.addEventListener('click', () => {
    connect.disabled = false;
    connect.textContent = '連接您的 OpenRouter';
    total.textContent = '—'; daily.textContent = '連接後顯示用量'; status.textContent = '';
  }));
  setInterval(() => { if (!document.hidden) load(); }, 60000);
  load();
  if (new URLSearchParams(window.location.search).get('openrouter') === 'connected') {
    document.querySelector('.rail-button[data-view="connections"]').click();
  }
})();
