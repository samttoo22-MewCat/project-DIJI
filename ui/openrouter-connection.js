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
  const bazaar = document.querySelector('#connect-bazaarlink');
  const bazaarStatus = document.querySelector('#bazaarlink-status');
  const priority = document.querySelector('#provider-priority');
  const priorityStatus = document.querySelector('#provider-priority-status');
  async function loadPriority() {
    try {
      const response = await fetch('/api/connections/priority', {cache:'no-store'});
      if (response.status === 401) { bazaarStatus.textContent = '請先登入 DIJI 再連接。'; return; }
      if (!response.ok) throw new Error();
      const data = await response.json();
      priority.value = data.priority[0];
      bazaar.disabled = data.connected.includes('bazaarlink');
      bazaar.textContent = bazaar.disabled ? '已連接您的 BazaarLink' : '連接您的 BazaarLink';
      bazaarStatus.textContent = bazaar.disabled ? '使用您自己的 BazaarLink 額度。' : '授權後即可使用。';
    } catch { priorityStatus.textContent = '無法載入額度順序，請重新開啟此頁。'; }
  }
  bazaar.addEventListener('click', () => {
    if (requireLogin()) window.location.assign('/api/connections/bazaarlink/start');
  });
  document.querySelector('#save-provider-priority').addEventListener('click', async () => {
    if (!requireLogin()) return;
    const order = priority.value === 'bazaarlink' ? ['bazaarlink','openrouter'] : ['openrouter','bazaarlink'];
    try {
      const response = await fetch('/api/connections/priority', {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(order)});
      if (!response.ok) throw new Error();
      priorityStatus.textContent = '已儲存，下一次模型請求開始套用。';
    } catch { priorityStatus.textContent = '儲存失敗，請稍後再試。'; }
  });
  loadPriority();
  if (new URLSearchParams(window.location.search).get('openrouter') === 'connected') {
    document.querySelector('.rail-button[data-view="connections"]').click();
  }
})();
