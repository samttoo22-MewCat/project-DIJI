(() => {
  const installButtons = [...document.querySelectorAll("[data-pwa-install]")];
  const guide = document.querySelector("#pwa-install-guide");
  const guideTitle = document.querySelector("[data-pwa-guide-title]");
  const guideIntro = document.querySelector("[data-pwa-guide-intro]");
  const iosGuide = document.querySelector("[data-pwa-guide-ios]");
  const browserGuide = document.querySelector("[data-pwa-guide-browser]");
  let deferredInstallPrompt = null;
  let appInstalled = false;

  const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  const isAppleMobile = () => /iphone|ipad|ipod/i.test(window.navigator.userAgent);

  function setInstallButtons(label, visible, disabled = false) {
    installButtons.forEach((button) => {
      button.hidden = !visible;
      button.textContent = label;
      button.disabled = disabled;
    });
  }

  function closeGuide() {
    if (guide.open) guide.close();
  }

  function openGuide(mode = isAppleMobile() ? "ios" : "browser") {
    const isIosGuide = mode === "ios";
    guideTitle.textContent = isIosGuide ? "加入 iPhone 或 iPad 主畫面" : "從瀏覽器選單完成安裝";
    guideIntro.textContent = isIosGuide
      ? "Safari 目前不會顯示自動安裝視窗；依下列步驟加入後，DIJI 會以獨立 App 方式開啟。"
      : "瀏覽器沒有顯示或完成系統安裝視窗時，可直接依下列步驟完成安裝。";
    iosGuide.hidden = !isIosGuide;
    browserGuide.hidden = isIosGuide;
    if (!guide.open) guide.showModal();
  }

  async function install() {
    if (deferredInstallPrompt) {
      setInstallButtons("正在開啟安裝…", true, true);
      try {
        await deferredInstallPrompt.prompt();
        const result = await deferredInstallPrompt.userChoice;
        deferredInstallPrompt = null;
        if (!appInstalled) {
          if (result.outcome !== "accepted") {
            setInstallButtons("安裝 DIJI", true);
            openGuide("browser");
            return;
          }
          setInstallButtons("Web App 安裝中…", true, true);
          window.setTimeout(() => {
            if (!appInstalled) {
              setInstallButtons("完成安裝", true);
              openGuide("browser");
            }
          }, 2500);
        }
      } catch {
        setInstallButtons("安裝 DIJI", true);
        openGuide("browser");
      }
      return;
    }
    openGuide();
  }

  installButtons.forEach((button) => button.addEventListener("click", install));
  document.querySelectorAll("[data-pwa-guide-close]").forEach((button) => button.addEventListener("click", closeGuide));
  guide.addEventListener("click", (event) => {
    if (event.target === guide) closeGuide();
  });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    if (!isStandalone() && !appInstalled) setInstallButtons("安裝 DIJI", true);
  });

  window.addEventListener("appinstalled", () => {
    appInstalled = true;
    deferredInstallPrompt = null;
    setInstallButtons("已安裝 DIJI", false);
    closeGuide();
  });

  if (isAppleMobile() && !isStandalone()) setInstallButtons("加入主畫面", true);

  if ("serviceWorker" in navigator && window.location.protocol !== "file:") {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch(() => {
        setInstallButtons("安裝暫時無法使用", false);
      });
    });
  }
})();
