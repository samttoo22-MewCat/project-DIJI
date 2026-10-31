(() => {
  const connect = document.querySelector('#connect-openrouter');
  const status = document.querySelector('#openrouter-connection-status');
  const refresh = document.querySelector('#refresh-openrouter');
  const total = document.querySelector('#openrouter-total');
  const daily = document.querySelector('#openrouter-daily');
  const resume = document.createElement('button');
  resume.type = 'button'; resume.className = 'primary-button resume-task'; resume.hidden = true;
  document.querySelector('.connections-heading').append(resume);
  let hasConnection = false;
  function updateResume() {
    const task = pendingTask();
    resume.hidden = !hasConnection || !task;
    resume.textContent = task === 'create-character' ? '繼續建立角色' : '繼續選角與對話';
  }
  resume.addEventListener('click', resumePendingTask);
  window.addEventListener('diji-task-changed', updateResume);
  function addDisconnect(provider, connectButton) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'ghost-button provider-disconnect';
    button.textContent = '撤銷連接'; button.hidden = true;
    connectButton.after(button);
    const note = document.createElement('p');
    note.className = 'connection-note'; note.hidden = true;
    const management = provider === 'openrouter' ? 'https://openrouter.ai/settings/keys' : 'https://bazaarlink.ai/keys';
    note.append('撤銷會清除 DIJI 保存的授權，已開始的請求不會取消。若要讓供應商金鑰失效，請至 ');
    const link = document.createElement('a'); link.href = management; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = '金鑰管理頁';
    note.append(link, ' 撤銷金鑰。'); button.after(note);
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const response = await fetch(`/api/connections/${provider}`, {method:'DELETE'});
        if (!response.ok) throw new Error();
        await Promise.all([load(), loadPriority()]);
        await refreshChatProviderState();
        showToast('已撤銷連接，DIJI 不再保存此模型商的授權。');
      } catch { showToast('撤銷失敗，請稍後再試。'); }
      finally { button.disabled = false; }
    });
    return connected => { button.hidden = !connected; note.hidden = !connected; };
  }
  const updateRouterDisconnect = addDisconnect('openrouter', connect);
  const money = value => typeof value === 'number' ? `$${value.toFixed(4)}` : '—';
  async function load() {
    if (!workspaceAvailable) return;
    refresh.disabled = true;
    try {
      const response = await fetch('/api/connections/openrouter', {cache:'no-store'});
      if (!response.ok) throw new Error();
      const data = await response.json();
      connect.textContent = data.connected ? '已連接您的 OpenRouter' : '連接您的 OpenRouter';
      connect.disabled = data.connected;
      updateRouterDisconnect(data.connected);
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
    updateRouterDisconnect(false);
    updateBazaarDisconnect(false);
    connect.disabled = false;
    connect.textContent = '連接您的 OpenRouter';
    total.textContent = '—'; daily.textContent = '連接後顯示用量'; status.textContent = '';
  }));
  setInterval(() => { if (!document.hidden) load(); }, 60000);
  window.addEventListener('diji-workspace-ready', load);
  const bazaar = document.querySelector('#connect-bazaarlink');
  const updateBazaarDisconnect = addDisconnect('bazaarlink', bazaar);
  const bazaarStatus = document.querySelector('#bazaarlink-status');
  const priority = document.querySelector('#provider-priority');
  const priorityStatus = document.querySelector('#provider-priority-status');
  async function loadPriority() {
    if (!workspaceAvailable) return;
    try {
      const response = await fetch('/api/connections/priority', {cache:'no-store'});
      if (response.status === 401) { bazaarStatus.textContent = '請先登入 DIJI 再連接。'; return; }
      if (!response.ok) throw new Error();
      const data = await response.json();
      priority.value = data.priority[0];
      hasConnection = data.connected.length > 0;
      updateResume();
      updateHomeJourney();
      bazaar.disabled = data.connected.includes('bazaarlink');
      updateBazaarDisconnect(bazaar.disabled);
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
  window.addEventListener('diji-workspace-ready', loadPriority);
  let usageLoading = false;
  async function loadBazaarUsage() {
    if (!workspaceAvailable) return;
    if (usageLoading) return;
    usageLoading = true;
    const refreshUsage = document.querySelector('#refresh-bazaarlink-usage');
    refreshUsage.disabled = true;
    refreshUsage.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch('/api/connections/bazaarlink/usage', {cache:'no-store'});
      if (!response.ok) throw new Error();
      const data = await response.json();
      const amount = value => value === null ? '—' : `$${Number(value).toFixed(6)}`;
      document.querySelector('#bazaarlink-total').textContent = amount(data.total);
      document.querySelector('#bazaarlink-last').textContent = `最近一次模型請求：${amount(data.last)} USD`;
      document.querySelector('#bazaarlink-usage-note').textContent = data.requests ? `已記錄 ${data.requests} 次請求；從啟用紀錄後累計，不含其他應用程式。` : '尚無費用紀錄；從啟用紀錄後開始累計，不含其他應用程式。';
    } catch {
      document.querySelector('#bazaarlink-usage-note').textContent = '無法讀取費用紀錄，請登入或稍後更新。';
    } finally { usageLoading = false; refreshUsage.disabled = false; refreshUsage.setAttribute('aria-busy', 'false'); }
  }
  document.querySelector('#refresh-bazaarlink-usage').addEventListener('click', loadBazaarUsage);
  setInterval(() => {
    if (!document.hidden && document.querySelector('[data-screen="connections"]').classList.contains('active')) loadBazaarUsage();
  }, 3000);
  document.querySelectorAll('[data-view="connections"]').forEach(button => button.addEventListener('click', loadBazaarUsage));
  window.addEventListener('diji-workspace-ready', loadBazaarUsage);
  if (new URLSearchParams(window.location.search).get('openrouter') === 'connected') {
    document.querySelector('.rail-button[data-view="connections"]').click();
    const clean = new URL(window.location.href);
    clean.searchParams.delete('openrouter');
    history.replaceState(null, '', clean.pathname + clean.search + '#connections');
  }
})();
