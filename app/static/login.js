(() => {
  const boot = document.getElementById("auth-boot");
  const root = document.getElementById("login-root");
  const form = document.getElementById("login-form");
  const userEl = document.getElementById("login-user");
  const passEl = document.getElementById("login-pass");
  const errEl = document.getElementById("login-error");
  const submitEl = document.getElementById("login-submit");
  const togglePw = document.getElementById("login-toggle-pw");
  const asideEl = document.getElementById("login-aside");

  function t(path, vars) {
    return window.SensorsI18n?.t?.(path, vars) ?? path;
  }

  function sanitizeFrom(raw) {
    const v = raw || "/";
    if (!v.startsWith("/") || v.startsWith("//") || v.startsWith("/login")) return "/";
    return v;
  }

  function fromParam() {
    const q = new URLSearchParams(location.search);
    return sanitizeFrom(q.get("from") || "/");
  }

  function showError(msg) {
    errEl.hidden = !msg;
    errEl.textContent = msg || "";
  }

  function setBusy(on) {
    submitEl.disabled = on;
    userEl.disabled = on;
    passEl.disabled = on;
    submitEl.textContent = on ? t("login.submitting") : t("login.submit");
  }

  async function fetchMe() {
    const res = await fetch("/api/auth/me", { credentials: "same-origin" });
    return res.json();
  }

  async function login(username, password) {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { ok: false, error: data.error || data.detail || `HTTP ${res.status}` };
    }
    return data;
  }

  function showForm(status) {
    boot.hidden = true;
    root.hidden = false;
    const hint = status?.usernameHint || "sensors";
    userEl.value = hint;
    asideEl.textContent = t("login.aside", { user: hint });
    window.SensorsI18n?.applyDomI18n?.(document);
    // re-sync locale pill active state
    document.querySelectorAll("#locale-seg [data-locale]").forEach((btn) => {
      const on = btn.getAttribute("data-locale") === (window.SensorsI18n?.getLocale?.() || "zh");
      btn.classList.toggle("active", on);
      btn.classList.toggle("login-lang-btn", true);
      if (on) btn.classList.add("active");
    });
  }

  togglePw?.addEventListener("click", () => {
    const show = passEl.type === "password";
    passEl.type = show ? "text" : "password";
    togglePw.textContent = show ? t("login.hide") : t("login.show");
  });

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("");
    setBusy(true);
    try {
      const out = await login(userEl.value.trim(), passEl.value);
      if (!out.ok) {
        const raw = out.error || "";
        showError(!raw || /^HTTP \d+$/.test(raw) ? t("login.fail") : raw);
        return;
      }
      location.replace(fromParam());
    } catch (err) {
      showError(err instanceof Error ? err.message : t("login.networkError"));
    } finally {
      setBusy(false);
    }
  });

  window.SensorsI18n?.onLocaleChange?.(() => {
    if (!root.hidden) {
      const hint = userEl.value || "sensors";
      asideEl.textContent = t("login.aside", { user: hint });
      submitEl.textContent = submitEl.disabled ? t("login.submitting") : t("login.submit");
      togglePw.textContent = passEl.type === "password" ? t("login.show") : t("login.hide");
    } else if (!boot.hidden) {
      boot.querySelector("p") && (boot.querySelector("p").textContent = t("login.checkingSession"));
    }
  });

  (async () => {
    try {
      const me = await fetchMe();
      if (!me.authRequired || me.authenticated) {
        location.replace(fromParam());
        return;
      }
      const st = await fetch("/api/auth/status", { credentials: "same-origin" }).then((r) => r.json());
      showForm(st);
    } catch {
      showForm({ usernameHint: "sensors" });
    }
  })();
})();
