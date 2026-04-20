(() => {
  try {
    const key = "erp.ui.locale";
    const stored = localStorage.getItem(key);
    const locale = stored === "zh-CN" || stored === "en"
      ? stored
      : ((navigator.language || navigator.languages?.[0] || "en").toLowerCase().startsWith("zh") ? "zh-CN" : "en");
    document.documentElement.lang = locale;
    document.documentElement.dataset.locale = locale;
  } catch {
    document.documentElement.lang = "en";
    document.documentElement.dataset.locale = "en";
  }
})();
