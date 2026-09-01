/**
 * iframe / host embed bridge.
 *
 * When framed:
 *  - hide logout / users / locale / theme chrome
 *  - follow host locale + theme via postMessage (and optional URL params)
 *
 * Host contract: see docs/embed-host.md
 */
(() => {
  const SOURCE = "sensors-view";
  const HOST_SOURCE = "sensors-view-host";
  const VERSION = 1;

  function isFramed() {
    try {
      return window.self !== window.top;
    } catch {
      return true;
    }
  }

  function qsPrefs() {
    const out = {};
    try {
      const q = new URLSearchParams(location.search);
      const loc = (q.get("locale") || q.get("lang") || "").toLowerCase();
      if (loc === "zh" || loc === "en") out.locale = loc;
      const theme = (q.get("theme") || "").toLowerCase();
      if (theme === "dark" || theme === "light" || theme === "system") out.theme = theme;
    } catch {
      /* ignore */
    }
    return out;
  }

  function applyPrefs(prefs, { persist = false } = {}) {
    if (!prefs || typeof prefs !== "object") return;
    if (prefs.locale === "zh" || prefs.locale === "en") {
      window.SensorsI18n?.setLocale?.(prefs.locale, { persist });
    }
    if (prefs.theme === "dark" || prefs.theme === "light" || prefs.theme === "system") {
      window.SensorsAppearance?.setTheme?.(prefs.theme, { persist });
    }
  }

  function setChromeHidden(framed) {
    const ids = ["btn-logout", "btn-users", "locale-seg", "theme-seg"];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (!el) continue;
      if (framed) {
        el.hidden = true;
        el.setAttribute("data-embed-hidden", "1");
      } else if (el.getAttribute("data-embed-hidden") === "1") {
        el.hidden = false;
        el.removeAttribute("data-embed-hidden");
      }
    }
    // Users modal must stay closed / unreachable in embed mode
    if (framed) {
      const modal = document.getElementById("users-modal");
      if (modal) modal.hidden = true;
    }
  }

  function syncIframeBadge(framed) {
    const badge = document.getElementById("iframe-embed-badge");
    if (!badge) return;
    badge.hidden = !framed;
    badge.setAttribute("aria-hidden", framed ? "false" : "true");
  }

  function postToHost(payload) {
    if (!isFramed()) return;
    try {
      window.parent.postMessage({ source: SOURCE, version: VERSION, ...payload }, "*");
    } catch {
      /* ignore */
    }
  }

  function onHostMessage(event) {
    if (!isFramed()) return;
    // Only accept messages that claim to be from our host protocol.
    // Origin is host-chosen; child cannot verify parent origin reliably without config.
    const data = event?.data;
    if (!data || typeof data !== "object") return;
    if (data.source !== HOST_SOURCE) return;

    if (data.type === "embed-prefs" || data.type === "appearance") {
      applyPrefs(
        {
          locale: data.locale,
          theme: data.theme,
        },
        { persist: false },
      );
      return;
    }
    if (data.type === "embed-locale" && (data.locale === "zh" || data.locale === "en")) {
      applyPrefs({ locale: data.locale }, { persist: false });
      return;
    }
    if (
      data.type === "embed-theme" &&
      (data.theme === "dark" || data.theme === "light" || data.theme === "system")
    ) {
      applyPrefs({ theme: data.theme }, { persist: false });
    }
  }

  function boot() {
    const framed = isFramed();
    syncIframeBadge(framed);
    setChromeHidden(framed);
    if (!framed) return;

    // URL params as first paint / no-JS-host fallback (do not write localStorage).
    applyPrefs(qsPrefs(), { persist: false });

    window.addEventListener("message", onHostMessage);
    postToHost({ type: "embed-ready" });
    // Ask explicitly in case host only replies to requests.
    postToHost({ type: "embed-request-prefs" });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.SensorsEmbed = {
    isFramed,
    applyPrefs,
    setChromeHidden,
    syncIframeBadge,
    postToHost,
    HOST_SOURCE,
    SOURCE,
    VERSION,
  };
})();
