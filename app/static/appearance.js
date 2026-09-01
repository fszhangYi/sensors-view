/**
 * sensors-view appearance prefs (embody-appearance-theme port).
 * Storage: sensors-view.theme | .compact | .density
 */
(() => {
  const THEME_KEY = "sensors-view.theme";
  const COMPACT_KEY = "sensors-view.compact";
  const DENSITY_KEY = "sensors-view.density";

  const DEFAULTS = {
    theme: "dark",
    compact: false,
    density: "comfortable",
  };

  function isThemePref(v) {
    return v === "system" || v === "dark" || v === "light";
  }

  function isDensityPref(v) {
    return v === "comfortable" || v === "compact" || v === "dense";
  }

  function readStoredAppearance() {
    const out = { ...DEFAULTS };
    try {
      const theme = localStorage.getItem(THEME_KEY);
      if (isThemePref(theme)) out.theme = theme;
      const compact = localStorage.getItem(COMPACT_KEY);
      if (compact === "1" || compact === "true") out.compact = true;
      if (compact === "0" || compact === "false") out.compact = false;
      const density = localStorage.getItem(DENSITY_KEY);
      if (isDensityPref(density)) out.density = density;
    } catch {
      /* ignore */
    }
    return out;
  }

  function resolveTheme(pref) {
    if (pref === "dark" || pref === "light") return pref;
    if (typeof window !== "undefined" && window.matchMedia) {
      return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    }
    return "dark";
  }

  function applyAppearance(prefs) {
    const resolved = resolveTheme(prefs.theme);
    const root = document.documentElement;
    root.dataset.theme = resolved;
    root.dataset.themePref = prefs.theme;
    root.dataset.compact = prefs.compact ? "1" : "0";
    root.dataset.density = prefs.density;
    root.style.colorScheme = resolved;
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) meta.setAttribute("content", resolved);
    return resolved;
  }

  function persistAppearance(prefs) {
    try {
      localStorage.setItem(THEME_KEY, prefs.theme);
      localStorage.setItem(COMPACT_KEY, prefs.compact ? "1" : "0");
      localStorage.setItem(DENSITY_KEY, prefs.density);
    } catch {
      /* ignore */
    }
  }

  let prefs = readStoredAppearance();
  applyAppearance(prefs);

  let systemMq = null;
  function bindSystemListener() {
    if (systemMq) {
      systemMq.removeEventListener("change", onSystemChange);
      systemMq = null;
    }
    if (prefs.theme !== "system" || !window.matchMedia) return;
    systemMq = window.matchMedia("(prefers-color-scheme: light)");
    systemMq.addEventListener("change", onSystemChange);
  }

  function onSystemChange() {
    if (prefs.theme === "system") applyAppearance(prefs);
  }

  function setTheme(theme, opts) {
    if (!isThemePref(theme)) return;
    const persist = !opts || opts.persist !== false;
    prefs = { ...prefs, theme };
    if (persist) persistAppearance(prefs);
    applyAppearance(prefs);
    bindSystemListener();
    syncThemeSeg();
  }

  function syncThemeSeg() {
    const seg = document.getElementById("theme-seg");
    if (!seg) return;
    seg.querySelectorAll("[data-theme-pref]").forEach((btn) => {
      const on = btn.getAttribute("data-theme-pref") === prefs.theme;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function initThemeSeg() {
    const seg = document.getElementById("theme-seg");
    if (!seg) return;
    seg.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-theme-pref]");
      if (!btn) return;
      setTheme(btn.getAttribute("data-theme-pref"));
    });
    syncThemeSeg();
  }

  bindSystemListener();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initThemeSeg);
  } else {
    initThemeSeg();
  }

  window.SensorsAppearance = {
    readStoredAppearance,
    resolveTheme,
    applyAppearance,
    persistAppearance,
    setTheme,
    getPrefs: () => ({ ...prefs }),
    getResolved: () => resolveTheme(prefs.theme),
  };
})();
