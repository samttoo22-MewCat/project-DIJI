/* Presentation only: account access, provider routing and model calls stay in app.js. */
(() => {
  const pages = {
    home: ['DIJI', '讓角色與故事，繼續發生。'],
    chat: ['對話', '每一句話，都接著你們的故事。'],
    characters: ['角色庫', '尋找下一位故事的同行者。'],
    'create-character': ['建立角色', '從靈感到人設，寫下你的想像。'],
    memory: ['記憶', '回看對話留下的重要片刻。'],
    jailbreak: ['越獄工作台', '整理與編輯模型對應的越獄。'],
    connections: ['模型連線', '自己的額度，自己的選擇。'],
    settings: ['設定', '管理你的帳號與使用偏好。'],
  };
  function updateHeading(name) {
    const [title, subtitle] = pages[name] || pages.home;
    document.querySelector('#workspace-title').textContent = title;
    document.querySelector('#workspace-subtitle').textContent = subtitle;
    document.querySelectorAll('.rail-button[data-view]').forEach(button => {
      if (button.dataset.view === name) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
  }
  window.addEventListener('diji-screen-changed', event => updateHeading(event.detail.name));
  updateHeading(document.querySelector('.screen.active')?.dataset.screen || 'home');

  // Content stays visible without JS or IntersectionObserver; reveal is progressive enhancement.
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        if (!reducedMotion.matches && typeof entry.target.animate === 'function') {
          entry.target.animate([
            {opacity: 0.65, transform: 'translateY(12px)'},
            {opacity: 1, transform: 'translateY(0)'},
          ], {duration: 280, easing: 'ease-out'});
        }
        observer.unobserve(entry.target);
      });
    }, {root: document.querySelector('.home-screen'), threshold: 0.12});
    document.querySelectorAll('.home-about, .home-principles').forEach(element => observer.observe(element));
    reducedMotion.addEventListener('change', () => {
      if (reducedMotion.matches) {
        document.querySelectorAll('.home-about, .home-principles').forEach(element => {
          if (typeof element.getAnimations === 'function') element.getAnimations().forEach(animation => animation.cancel());
        });
      }
    });
  }
})();
