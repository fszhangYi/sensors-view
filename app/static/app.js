(() => {
  const grid = document.getElementById("device-grid");
  const summary = document.getElementById("summary");
  const autoEl = document.getElementById("auto-refresh");
  const btnRefresh = document.getElementById("btn-refresh");
  const btnReload = document.getElementById("btn-reload");
  const drawer = document.getElementById("drawer");
  const drawerTitle = document.getElementById("drawer-title");
  const drawerBody = document.getElementById("drawer-body");
  const drawerClose = document.getElementById("drawer-close");
  const refreshHint = document.getElementById("refresh-hint");

  const refreshSeconds = Number(window.__VIEW__?.refreshSeconds || grid?.dataset.refresh || 5);
  let timer = null;
  let busy = false;

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function renderSummary(devices) {
    const counts = {};
    for (const d of devices) {
      counts[d.status] = (counts[d.status] || 0) + 1;
    }
    summary.innerHTML = Object.entries(counts)
      .map(([status, n]) => `<span class="chip" data-status="${escapeHtml(status)}">${escapeHtml(status)} × ${n}</span>`)
      .join("");
  }

  function renderCards(devices) {
    grid.innerHTML = devices
      .map((d, i) => {
        const checks = (d.checks || [])
          .slice(0, 5)
          .map((c) => {
            const cls = c.ok ? "ok" : "bad";
            const detail = c.detail ? ` — ${escapeHtml(c.detail)}` : "";
            return `<li><span class="dot ${cls}"></span><span><strong>${escapeHtml(c.name)}</strong>${detail}</span></li>`;
          })
          .join("");
        const more = (d.checks || []).length > 5 ? `<li><span class="dot"></span><span>… +${d.checks.length - 5} checks</span></li>` : "";
        return `
          <article class="card" style="animation-delay:${Math.min(i * 0.03, 0.3)}s" data-id="${escapeHtml(d.id)}">
            <div class="card-head">
              <div>
                <p class="card-id">${escapeHtml(d.kind)} · ${escapeHtml(d.id)}</p>
                <h2 class="card-title">${escapeHtml(d.name || d.id)}</h2>
              </div>
              <span class="status-pill" data-status="${escapeHtml(d.status)}">${escapeHtml(d.status)}</span>
            </div>
            <p class="msg">${escapeHtml(d.message || "")}</p>
            <ul class="checks">${checks}${more}</ul>
            <div class="card-actions">
              <button type="button" class="btn primary btn-sample" data-id="${escapeHtml(d.id)}">采样 read</button>
            </div>
          </article>
        `;
      })
      .join("");

    grid.querySelectorAll(".btn-sample").forEach((btn) => {
      btn.addEventListener("click", () => sample(btn.dataset.id, btn));
    });
    grid.querySelectorAll(".card").forEach((card) => card.classList.add("pulse"));
  }

  async function loadMeta() {
    const res = await fetch("/api/meta");
    if (!res.ok) throw new Error(`meta ${res.status}`);
    const meta = await res.json();
    setText("meta-site", meta.site || "—");
    setText("meta-count", String(meta.count ?? "—"));
    setText("meta-mode", meta.dry_run ? "dry-run" : "live");
    setText("meta-config", meta.sensors_config || "—");
    if (refreshHint) refreshHint.textContent = `refresh ${meta.refresh_seconds || refreshSeconds}s`;
    return meta;
  }

  async function probe() {
    if (busy) return;
    busy = true;
    btnRefresh.disabled = true;
    try {
      await loadMeta();
      const res = await fetch("/api/probe");
      if (!res.ok) throw new Error(`probe ${res.status}`);
      const data = await res.json();
      renderSummary(data.devices || []);
      renderCards(data.devices || []);
      setText("meta-updated", new Date().toLocaleTimeString());
    } catch (err) {
      summary.innerHTML = `<span class="chip" data-status="error">probe failed: ${escapeHtml(err.message || err)}</span>`;
    } finally {
      busy = false;
      btnRefresh.disabled = false;
    }
  }

  async function sample(id, btn) {
    if (!id) return;
    const prev = btn.textContent;
    btn.disabled = true;
    btn.textContent = "读取中…";
    try {
      const res = await fetch(`/api/read/${encodeURIComponent(id)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      drawerTitle.textContent = id;
      drawerBody.textContent = JSON.stringify(data.sample, null, 2);
      drawer.hidden = false;
    } catch (err) {
      drawerTitle.textContent = id;
      drawerBody.textContent = String(err.message || err);
      drawer.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = prev;
    }
  }

  async function reloadCfg() {
    btnReload.disabled = true;
    try {
      const res = await fetch("/api/reload", { method: "POST" });
      if (!res.ok) throw new Error(`reload ${res.status}`);
      await probe();
    } catch (err) {
      summary.innerHTML = `<span class="chip" data-status="error">reload failed: ${escapeHtml(err.message || err)}</span>`;
    } finally {
      btnReload.disabled = false;
    }
  }

  function schedule() {
    if (timer) clearInterval(timer);
    timer = null;
    if (autoEl.checked) {
      timer = setInterval(probe, Math.max(2, refreshSeconds) * 1000);
    }
  }

  btnRefresh.addEventListener("click", probe);
  btnReload.addEventListener("click", reloadCfg);
  autoEl.addEventListener("change", schedule);
  drawerClose.addEventListener("click", () => { drawer.hidden = true; });
  drawer.addEventListener("click", (e) => {
    if (e.target === drawer) drawer.hidden = true;
  });

  probe();
  schedule();
})();
