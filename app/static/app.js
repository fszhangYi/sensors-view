(() => {
  const grid = document.getElementById("device-grid");
  const summary = document.getElementById("summary");
  const btnRefresh = document.getElementById("btn-refresh");
  const btnReload = document.getElementById("btn-reload");
  const btnLogout = document.getElementById("btn-logout");
  const btnUsers = document.getElementById("btn-users");
  const usersModal = document.getElementById("users-modal");
  const usersClose = document.getElementById("users-close");
  const usersAdmin = document.getElementById("users-admin");
  const usersTbody = document.getElementById("users-tbody");
  const usersHint = document.getElementById("users-hint");
  const passwordForm = document.getElementById("password-form");
  const passwordHint = document.getElementById("password-hint");
  const userCreateForm = document.getElementById("user-create-form");

  let currentAuthUser = null;

  const modal = document.getElementById("modal");
  const modalTitle = document.getElementById("modal-title");
  const modalKind = document.getElementById("modal-kind");
  const modalClose = document.getElementById("modal-close");
  const form = document.getElementById("connect-form");
  const formFields = document.getElementById("form-fields");
  const dryRunEl = document.getElementById("sample-dry-run");
  const rateEl = document.getElementById("sample-rate");
  const formHint = document.getElementById("form-hint");
  const btnStart = document.getElementById("btn-start");
  const btnStop = document.getElementById("btn-stop");
  const btnOnce = document.getElementById("btn-once");
  const btnSaveStream = document.getElementById("btn-save-stream");
  const batchRateEl = document.getElementById("batch-rate");
  const batchDryRunEl = document.getElementById("batch-dry-run");
  const btnBatchStart = document.getElementById("btn-batch-start");
  const btnBatchStop = document.getElementById("btn-batch-stop");
  const btnBatchSave = document.getElementById("btn-batch-save");
  const batchSeqEl = document.getElementById("batch-seq");
  const batchSeqWrap = document.getElementById("batch-seq-wrap");
  const batchHint = document.getElementById("batch-hint");
  const modalPreview = document.getElementById("modal-preview");
  const vizNote = document.getElementById("viz-note");
  const vizJson = document.getElementById("viz-json");
  const streamStatus = document.getElementById("stream-status");

  const controlPanel = document.getElementById("control-panel");
  const controlHint = document.getElementById("control-hint");
  const deltaGrid = document.getElementById("delta-grid");
  const btnCapture = document.getElementById("btn-capture");
  const baselineHint = document.getElementById("baseline-hint");
  const btnRandomCmd = document.getElementById("btn-random-cmd");
  const autoCommandEl = document.getElementById("auto-command");
  const commandHint = document.getElementById("command-hint");

  let busy = false;
  let currentDevice = null;
  let sessionId = null;
  let streamTimer = null;
  let tickInFlight = false;
  let streamStartedAt = 0;
  let lastPayload = null;
  let streamRecords = [];
  let streamRecording = false;
  let baseline = null; // number[]
  let lastDevices = [];
  const deviceCache = {};
  const selectedIds = new Set();
  let batchRunning = false;
  let batchTimer = null;
  let batchTickInFlight = false;
  let batchStartedAt = 0;
  /** @type {{ id: string, sessionId: string, kind: string, name: string }[]} */
  let batchSessions = [];
  /** @type {object[]} */
  let batchFrames = [];
  let batchCanSave = false;

  const _fetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const opts = { ...init, credentials: init.credentials || "same-origin" };
    const res = await _fetch(input, opts);
    const url = typeof input === "string" ? input : input?.url || "";
    if (
      res.status === 401 &&
      !String(url).includes("/api/auth/") &&
      !location.pathname.startsWith("/login")
    ) {
      const from = `${location.pathname}${location.search}${location.hash}` || "/";
      const safe = from.startsWith("/") && !from.startsWith("//") && !from.startsWith("/login") ? from : "/";
      location.assign(`/login?from=${encodeURIComponent(safe)}`);
    }
    return res;
  };

  function t(path, vars) {
    return window.SensorsI18n?.t?.(path, vars) ?? path;
  }

  function fieldLabel(key, fallback) {
    return window.SensorsI18n?.fieldLabel?.(key, fallback) ?? fallback ?? key;
  }

  async function requireAuth() {
    try {
      const res = await fetch("/api/auth/me");
      const me = await res.json();
      if (me.authRequired && !me.authenticated) {
        const from = `${location.pathname}${location.search}${location.hash}` || "/";
        const safe = from.startsWith("/") && !from.startsWith("//") && !from.startsWith("/login") ? from : "/";
        location.replace(`/login?from=${encodeURIComponent(safe)}`);
        return false;
      }
      document.body.hidden = false;
      currentAuthUser = me.user || null;
      if (btnLogout) btnLogout.hidden = !me.authRequired;
      if (btnUsers) btnUsers.hidden = !me.authRequired;
      return true;
    } catch {
      document.body.hidden = false;
      return true;
    }
  }

  async function logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      location.assign("/login?from=/");
    }
  }

  function apiDetail(data) {
    if (!data) return "";
    if (typeof data.detail === "string") return data.detail;
    if (data.detail?.error) return data.detail.error;
    if (data.error) return data.error;
    return JSON.stringify(data.detail || data);
  }

  async function loadUsers() {
    if (!usersTbody) return;
    usersHint.textContent = "";
    const res = await fetch("/api/users");
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      usersHint.textContent = apiDetail(data) || `HTTP ${res.status}`;
      usersAdmin.hidden = true;
      return;
    }
    usersAdmin.hidden = false;
    const me = currentAuthUser?.username || "";
    usersTbody.innerHTML = (data.users || [])
      .map((u) => {
        const name = escapeHtml(u.username);
        const role = u.role === "admin" ? "admin" : "user";
        return `
          <tr data-user="${name}">
            <td class="mono">${name}</td>
            <td>
              <select class="user-role" data-user="${name}">
                <option value="user" ${role === "user" ? "selected" : ""}>user</option>
                <option value="admin" ${role === "admin" ? "selected" : ""}>admin</option>
              </select>
            </td>
            <td><input type="checkbox" class="user-enabled" data-user="${name}" ${u.enabled ? "checked" : ""} /></td>
            <td>
              <div class="users-actions">
                <button type="button" class="btn ghost user-reset" data-user="${name}">${escapeHtml(t("users.resetPassword"))}</button>
                <button type="button" class="btn danger user-del" data-user="${name}" ${u.username === me ? "disabled" : ""}>${escapeHtml(t("users.delete"))}</button>
              </div>
            </td>
          </tr>`;
      })
      .join("");
  }

  async function patchUser(username, body) {
    const res = await fetch(`/api/users/${encodeURIComponent(username)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiDetail(data) || `HTTP ${res.status}`);
    return data;
  }

  async function openUsersModal() {
    usersModal.hidden = false;
    passwordHint.textContent = "";
    usersHint.textContent = "";
    passwordForm?.reset();
    const isAdmin = currentAuthUser?.role === "admin";
    usersAdmin.hidden = !isAdmin;
    if (isAdmin) {
      try {
        await loadUsers();
      } catch (err) {
        usersHint.textContent = String(err.message || err);
      }
    }
  }

  function closeUsersModal() {
    usersModal.hidden = true;
  }

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

  function clampHz(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return 2;
    return Math.min(30, Math.max(0.2, n));
  }

  function intervalMs() {
    return Math.round(1000 / clampHz(rateEl.value));
  }

  function control() {
    return currentDevice?.control || { writable: false };
  }

  function setStreamingUi(on) {
    btnStart.disabled = on;
    btnStop.disabled = !on;
    btnOnce.disabled = on;
    dryRunEl.disabled = on;
    formFields.querySelectorAll("input").forEach((el) => {
      el.disabled = on;
    });
    modal.classList.toggle("is-streaming", on);
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

  function clampBatchHz(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return 2;
    return Math.min(30, Math.max(0.2, n));
  }

  function batchIntervalMs() {
    return Math.round(1000 / clampBatchHz(batchRateEl?.value));
  }

  function isOnlineStatus(status) {
    return status === "ok" || status === "warn";
  }

  function setBatchUi() {
    if (!btnBatchStart) return;
    btnBatchStart.disabled = batchRunning;
    btnBatchStop.disabled = !batchRunning;
    if (batchRateEl) batchRateEl.disabled = batchRunning;
    if (batchDryRunEl) batchDryRunEl.disabled = batchRunning;
    grid?.querySelectorAll(".card-check").forEach((el) => {
      el.disabled = batchRunning;
    });
    const showSave = batchCanSave && !batchRunning && batchFrames.length > 0;
    if (batchSeqWrap) batchSeqWrap.hidden = !showSave;
    if (btnBatchSave) {
      btnBatchSave.hidden = !showSave;
      btnBatchSave.disabled = !showSave;
    }
  }

  function syncCardSelectionUi() {
    grid?.querySelectorAll(".card").forEach((card) => {
      const id = card.dataset.id;
      const on = selectedIds.has(id);
      card.classList.toggle("is-selected", on);
      card.classList.toggle("is-batch-live", batchRunning && batchSessions.some((s) => s.id === id));
      const box = card.querySelector(".card-check");
      if (box) box.checked = on;
    });
  }

  function selectedDeviceIds() {
    return [...selectedIds];
  }

  function frameReadingFromPayload(payload) {
    return {
      tick: payload.tick,
      dry_run: !!payload.dry_run,
      sample: payload.sample ?? null,
      raw: extractRawFromPayload(payload),
      display: extractDisplayFromPayload(payload),
      config_used: payload.config_used ?? null,
      kind: payload.kind || null,
      name: payload.name || null,
    };
  }

  async function probeOne(id) {
    const res = await fetch(`/api/probe?id=${encodeURIComponent(id)}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `probe ${res.status}`);
    const d = (data.devices || [])[0];
    if (!d) throw new Error(`no probe result for ${id}`);
    return d;
  }

  async function startBatchSession(id) {
    const res = await fetch(`/api/session/start/${encodeURIComponent(id)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        config: {},
        dry_run: !!batchDryRunEl?.checked,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.detail?.error || `HTTP ${res.status}`);
    return data;
  }

  function clearBatchTimer() {
    if (batchTimer) {
      clearInterval(batchTimer);
      batchTimer = null;
    }
  }

  async function tickBatchOnce() {
    if (!batchRunning || batchTickInFlight || !batchSessions.length) return;
    batchTickInFlight = true;
    try {
      const results = await Promise.all(
        batchSessions.map(async (s) => {
          const res = await fetch(`/api/session/${encodeURIComponent(s.sessionId)}/tick`, { method: "POST" });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(`${s.id}: ${data.detail || res.status}`);
          return { id: s.id, data };
        })
      );
      const readings = {};
      let tick = 0;
      for (const { id, data } of results) {
        readings[id] = frameReadingFromPayload(data);
        tick = Math.max(tick, Number(data.tick) || 0);
      }
      batchFrames.push({
        t: new Date().toISOString(),
        tick,
        readings,
      });
      if (batchHint) {
        batchHint.textContent = t("batch.running", {
          n: batchSessions.length,
          hz: clampBatchHz(batchRateEl?.value),
          tick,
          count: batchFrames.length,
        });
      }
    } catch (err) {
      if (batchHint) batchHint.textContent = String(err.message || err);
      await stopBatch({ quiet: true });
    } finally {
      batchTickInFlight = false;
    }
  }

  async function stopBatch({ quiet = false } = {}) {
    clearBatchTimer();
    const sessions = batchSessions.slice();
    batchSessions = [];
    batchRunning = false;
    batchTickInFlight = false;
    batchCanSave = batchFrames.length > 0;
    setBatchUi();
    syncCardSelectionUi();
    await Promise.all(
      sessions.map(async (s) => {
        try {
          await fetch(`/api/session/${encodeURIComponent(s.sessionId)}/stop`, { method: "POST" });
        } catch {
          /* ignore */
        }
      })
    );
    if (!quiet && batchHint) {
      batchHint.textContent = t("batch.stopped", { count: batchFrames.length });
    }
  }

  async function startBatch() {
    const ids = selectedDeviceIds();
    if (!ids.length) {
      if (batchHint) batchHint.textContent = t("batch.none");
      return;
    }
    if (batchRunning) return;
    await stopStream({ quiet: true });
    batchFrames = [];
    batchCanSave = false;
    setBatchUi();
    if (batchHint) batchHint.textContent = t("batch.checking");
    btnBatchStart.disabled = true;
    try {
      for (const id of ids) {
        if (batchHint) batchHint.textContent = `${t("batch.checking")} ${id}`;
        const d = await probeOne(id);
        deviceCache[id] = { ...deviceCache[id], ...d };
        const dry = !!batchDryRunEl?.checked;
        if (!dry && !isOnlineStatus(d.status)) {
          throw new Error(t("batch.offline", { id, status: d.status || "unknown" }));
        }
      }
      if (batchHint) batchHint.textContent = t("batch.starting");
      const started = [];
      for (const id of ids) {
        try {
          const data = await startBatchSession(id);
          started.push({
            id,
            sessionId: data.session_id,
            kind: data.kind || deviceCache[id]?.kind || "",
            name: data.name || deviceCache[id]?.name || id,
          });
          if (!batchFrames.length) {
            batchFrames.push({
              t: new Date().toISOString(),
              tick: data.tick || 1,
              readings: { [id]: frameReadingFromPayload(data) },
            });
          } else {
            const first = batchFrames[0];
            first.readings[id] = frameReadingFromPayload(data);
            first.tick = Math.max(Number(first.tick) || 0, Number(data.tick) || 0);
          }
        } catch (err) {
          for (const s of started) {
            try {
              await fetch(`/api/session/${encodeURIComponent(s.sessionId)}/stop`, { method: "POST" });
            } catch {
              /* ignore */
            }
          }
          throw new Error(t("batch.startFailed", { id, err: err.message || err }));
        }
      }
      batchSessions = started;
      batchRunning = true;
      batchStartedAt = Date.now();
      setBatchUi();
      syncCardSelectionUi();
      if (batchHint) {
        batchHint.textContent = t("batch.running", {
          n: batchSessions.length,
          hz: clampBatchHz(batchRateEl?.value),
          tick: batchFrames[0]?.tick || 1,
          count: batchFrames.length,
        });
      }
      clearBatchTimer();
      batchTimer = setInterval(tickBatchOnce, batchIntervalMs());
    } catch (err) {
      batchFrames = [];
      batchCanSave = false;
      batchRunning = false;
      batchSessions = [];
      setBatchUi();
      syncCardSelectionUi();
      if (batchHint) batchHint.textContent = String(err.message || err);
    }
  }

  function saveBatchFile() {
    if (!batchFrames.length) {
      if (batchHint) batchHint.textContent = t("batch.nothing");
      return;
    }
    const seq = String(batchSeqEl?.value || "").trim();
    if (!seq) {
      if (batchHint) batchHint.textContent = t("batch.needSeq");
      batchSeqEl?.focus();
      return;
    }
    const safeSeq = seq.replace(/[^\w.\-]+/g, "_");
    const file = `sensors-view-${safeSeq}.json`;
    const payload = {
      seq,
      saved_at: new Date().toISOString(),
      started_at: batchStartedAt ? new Date(batchStartedAt).toISOString() : null,
      hz: clampBatchHz(batchRateEl?.value),
      dry_run: !!batchDryRunEl?.checked,
      device_ids: [...new Set(batchFrames.flatMap((f) => Object.keys(f.readings || {})))],
      devices: (batchFrames[0]
        ? Object.keys(batchFrames[0].readings || {})
        : selectedDeviceIds()
      ).map((id) => ({
        id,
        kind: deviceCache[id]?.kind || batchFrames[0]?.readings?.[id]?.kind || null,
        name: deviceCache[id]?.name || batchFrames[0]?.readings?.[id]?.name || id,
      })),
      count: batchFrames.length,
      frames: batchFrames,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = file;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    if (batchHint) batchHint.textContent = t("batch.saved", { count: batchFrames.length, file });
  }

  function renderCards(devices) {
    lastDevices = devices || [];
    for (const d of lastDevices) deviceCache[d.id] = d;
    const known = new Set(lastDevices.map((d) => d.id));
    for (const id of [...selectedIds]) {
      if (!known.has(id)) selectedIds.delete(id);
    }
    grid.innerHTML = lastDevices
      .map((d, i) => {
        const checks = (d.checks || [])
          .slice(0, 4)
          .map((c) => {
            const cls = c.ok ? "ok" : "bad";
            const detail = c.detail ? ` — ${escapeHtml(c.detail)}` : "";
            return `<li><span class="dot ${cls}"></span><span><strong>${escapeHtml(c.name)}</strong>${detail}</span></li>`;
          })
          .join("");
        const cta = d.kind === "arm" || d.kind === "gripper"
          ? t("card.cta.writable")
          : t("card.cta.sample");
        const selected = selectedIds.has(d.id);
        return `
          <article class="card clickable${selected ? " is-selected" : ""}" style="animation-delay:${Math.min(i * 0.03, 0.3)}s" data-id="${escapeHtml(d.id)}" data-status="${escapeHtml(d.status)}" tabindex="0" role="button">
            <div class="card-head">
              <div>
                <label class="card-select">
                  <input type="checkbox" class="card-check" data-id="${escapeHtml(d.id)}" ${selected ? "checked" : ""} ${batchRunning ? "disabled" : ""} />
                  <span class="card-select-label">${escapeHtml(t("card.select"))}</span>
                </label>
                <p class="card-id">${escapeHtml(d.kind)} · ${escapeHtml(d.id)}</p>
                <h2 class="card-title">${escapeHtml(d.name || d.id)}</h2>
              </div>
              <span class="status-pill" data-status="${escapeHtml(d.status)}">${escapeHtml(d.status)}</span>
            </div>
            <p class="msg">${escapeHtml(d.message || "")}</p>
            <ul class="checks">${checks}</ul>
            <div class="card-actions">
              <span class="card-cta">${cta}</span>
            </div>
          </article>
        `;
      })
      .join("");

    grid.querySelectorAll(".card").forEach((card) => {
      const open = () => openModal(card.dataset.id);
      card.addEventListener("click", (e) => {
        if (e.target.closest(".card-select")) return;
        open();
      });
      card.addEventListener("keydown", (e) => {
        if (e.target.closest(".card-select")) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      });
    });
    grid.querySelectorAll(".card-select").forEach((label) => {
      label.addEventListener("click", (e) => e.stopPropagation());
    });
    grid.querySelectorAll(".card-check").forEach((box) => {
      box.addEventListener("change", () => {
        const id = box.dataset.id;
        if (box.checked) selectedIds.add(id);
        else selectedIds.delete(id);
        syncCardSelectionUi();
      });
    });
    syncCardSelectionUi();
  }

  function fieldValue(cfg, key, asType) {
    const v = cfg?.[key];
    if (asType === "int_list" && Array.isArray(v)) return v.join(", ");
    if (v == null) return "";
    return String(v);
  }

  function collectFormConfig() {
    const out = {};
    formFields.querySelectorAll("input[name]").forEach((input) => {
      out[input.name] = input.value;
    });
    return out;
  }

  function renderMetrics(el, metrics) {
    if (!metrics?.length) {
      el.innerHTML = "";
      return;
    }
    el.innerHTML = metrics
      .map((m) => `<div class="metric"><span class="k">${escapeHtml(m.label)}</span><span class="v">${escapeHtml(m.value)}</span></div>`)
      .join("");
  }

  function renderImages(el, images) {
    if (!images?.length) {
      el.innerHTML = "";
      return;
    }
    el.innerHTML = images
      .map(
        (img) => `
        <figure class="viz-fig">
          <figcaption>${escapeHtml(img.title || "image")}</figcaption>
          <img src="${img.src}" alt="${escapeHtml(img.title || "sample")}" />
        </figure>`
      )
      .join("");
  }

  function renderCharts(el, charts) {
    if (!charts?.length) {
      el.innerHTML = "";
      return;
    }
    el.innerHTML = charts
      .map((c) => {
        if (c.type === "gauge") {
          const min = Number(c.min ?? 0);
          const max = Number(c.max ?? 1);
          const val = Number(c.value ?? 0);
          const pct = Math.max(0, Math.min(100, ((val - min) / (max - min || 1)) * 100));
          return `
            <div class="chart-card">
              <h3>${escapeHtml(c.title || "gauge")}</h3>
              <div class="gauge">
                <div class="gauge-track"><div class="gauge-fill" style="width:${pct}%"></div></div>
                <div class="gauge-val">${val.toFixed(4)} <span class="muted">(${pct.toFixed(0)}%)</span></div>
              </div>
            </div>`;
        }
        const values = c.values || [];
        const absMax = Math.max(...values.map((v) => Math.abs(Number(v) || 0)), 1e-6);
        const bars = values
          .map((v, i) => {
            const n = Number(v) || 0;
            const h = Math.max(4, (Math.abs(n) / absMax) * 100);
            const label = (c.labels && c.labels[i]) || String(i);
            return `
              <div class="bar">
                <div class="bar-col" style="height:${h}%" title="${escapeHtml(String(n))}"></div>
                <span class="bar-label">${escapeHtml(label)}</span>
                <span class="bar-num">${n.toFixed(3)}</span>
              </div>`;
          })
          .join("");
        return `
          <div class="chart-card">
            <h3>${escapeHtml(c.title || "chart")}</h3>
            <div class="bars">${bars}</div>
          </div>`;
      })
      .join("");
  }

  function showControlPanel() {
    const c = control();
    if (!c.writable) {
      controlPanel.hidden = true;
      return;
    }
    controlPanel.hidden = false;
    controlHint.textContent =
      c.mode === "gripper" ? t("control.hint.gripper") : t("control.hint.joints");
    const n = c.num_dofs || 1;
    const labels = c.labels || [];
    const defDelta = c.default_delta ?? 0.05;
    const rs = c.read_scale || [];
    const ro = c.read_offset || [];
    const ws = c.write_scale || [];
    const wo = c.write_offset || [];
    const fmt = (v, fallback) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return String(fallback);
      // keep decimals visible (e.g. -0.5, 1.5708); avoid sci-notation for typical ranges
      return String(Number(n.toPrecision(12)));
    };
    deltaGrid.innerHTML = Array.from({ length: n }, (_, i) => {
      const label = labels[i] || `dof${i + 1}`;
      const base = baseline?.[i];
      return `
        <div class="delta-card" data-i="${i}">
          <span class="dof-name">${escapeHtml(label)} (${escapeHtml(c.unit || "")})</span>
          <span class="baseline">${escapeHtml(t("control.baselineLabel", { val: base == null ? "—" : Number(base).toFixed(4) }))}</span>
          <label class="affine-field"><span>${escapeHtml(t("control.rs"))}</span><input type="number" class="rs-input" data-i="${i}" step="0.001" inputmode="decimal" value="${fmt(rs[i], 1)}" /></label>
          <label class="affine-field"><span>${escapeHtml(t("control.ro"))}</span><input type="number" class="ro-input" data-i="${i}" step="0.001" inputmode="decimal" value="${fmt(ro[i], 0)}" /></label>
          <label class="affine-field"><span>${escapeHtml(t("control.ws"))}</span><input type="number" class="ws-input" data-i="${i}" step="0.001" inputmode="decimal" value="${fmt(ws[i], 1)}" /></label>
          <label class="affine-field"><span>${escapeHtml(t("control.wo"))}</span><input type="number" class="wo-input" data-i="${i}" step="0.001" inputmode="decimal" value="${fmt(wo[i], 0)}" /></label>
          <label class="affine-field"><span>${escapeHtml(t("control.delta"))}</span><input type="number" class="delta-input" data-i="${i}" min="${c.min_delta ?? 0}" max="${c.max_delta ?? 1}" step="0.001" value="${fmt(defDelta, 0.05)}" /></label>
        </div>`;
    }).join("");
  }

  function refreshBaselineLabels() {
    deltaGrid.querySelectorAll(".delta-card").forEach((card) => {
      const i = Number(card.dataset.i);
      const el = card.querySelector(".baseline");
      const base = baseline?.[i];
      if (el) {
        el.textContent = t("control.baselineLabel", {
          val: base == null ? "—" : Number(base).toFixed(4),
        });
      }
    });
  }

  function readAffineColumn(cls, fallback) {
    const c = control();
    const n = c.num_dofs || 1;
    const out = [];
    for (let i = 0; i < n; i++) {
      const input = deltaGrid.querySelector(`.${cls}[data-i="${i}"]`);
      let v = Number(input?.value);
      if (!Number.isFinite(v)) v = fallback;
      out.push(v);
    }
    return out;
  }

  function applyAffine(values, scales, offsets) {
    return values.map((v, i) => Number(scales[i] ?? 1) * Number(v) + Number(offsets[i] ?? 0));
  }

  function extractRawFromPayload(payload) {
    const c = control();
    if (!c.writable || !payload) return null;
    const sample = payload.sample || {};
    if (c.mode === "joints") {
      const joints = sample.arm_joints || sample.joints;
      if (Array.isArray(joints) && joints.length) {
        return joints.slice(0, c.num_dofs).map(Number);
      }
      return null; // dry-run placeholder lives in viz only
    }
    if (c.mode === "gripper") {
      if (sample.position_norm != null) return [Number(sample.position_norm)];
      return null;
    }
    return null;
  }

  function extractDisplayFromPayload(payload) {
    const c = control();
    if (!c.writable || !payload) return null;
    const raw = extractRawFromPayload(payload);
    if (raw) {
      const rs = readAffineColumn("rs-input", 1);
      const ro = readAffineColumn("ro-input", 0);
      return applyAffine(raw, rs, ro);
    }
    // Fallback: dry-run synthetic viz already in display-ish space
    if (c.mode === "joints") {
      const chart = (payload.viz?.charts || []).find((x) => x.type === "bars");
      if (chart?.values?.length) return chart.values.slice(0, c.num_dofs).map(Number);
      return Array.from({ length: c.num_dofs }, () => 0);
    }
    if (c.mode === "gripper") {
      const gauge = (payload.viz?.charts || []).find((x) => x.type === "gauge");
      if (gauge && gauge.value != null) return [Number(gauge.value)];
      return [0.3];
    }
    return null;
  }

  function remappedViz(payload) {
    const viz = JSON.parse(JSON.stringify(payload.viz || {}));
    const c = control();
    if (!c.writable) return viz;
    const display = extractDisplayFromPayload(payload);
    const raw = extractRawFromPayload(payload);
    if (!display) return viz;

    if (c.mode === "joints") {
      const chart = (viz.charts || []).find((x) => x.type === "bars");
      if (chart) {
        chart.title = t("viz.jointsDisplay");
        chart.values = display;
      }
    } else if (c.mode === "gripper") {
      const gauge = (viz.charts || []).find((x) => x.type === "gauge");
      if (gauge) {
        gauge.title = t("viz.gripperDisplay");
        gauge.value = display[0];
      }
    }

    viz.metrics = (viz.metrics || []).filter((m) => !String(m.label).startsWith("raw_") && !String(m.label).startsWith("disp_"));
    if (raw) {
      raw.forEach((v, i) => viz.metrics.push({ label: `raw_${i + 1}`, value: Number(v).toFixed(4) }));
    }
    display.forEach((v, i) => viz.metrics.push({ label: `disp_${i + 1}`, value: Number(v).toFixed(4) }));
    return viz;
  }

  function captureBaseline() {
    const vals = extractDisplayFromPayload(lastPayload);
    if (!vals) {
      baselineHint.textContent = t("control.baselineNeedSample");
      return;
    }
    baseline = vals;
    baselineHint.textContent = t("control.baselineCaptured", {
      vals: vals.map((v) => v.toFixed(3)).join(", "),
    });
    refreshBaselineLabels();
  }

  function readDeltas() {
    const c = control();
    const n = c.num_dofs || 1;
    const out = [];
    for (let i = 0; i < n; i++) {
      const input = deltaGrid.querySelector(`.delta-input[data-i="${i}"]`);
      let d = Number(input?.value);
      if (!Number.isFinite(d)) d = c.default_delta ?? 0.05;
      d = Math.max(c.min_delta ?? 0, Math.min(c.max_delta ?? d, Math.abs(d)));
      out.push(d);
    }
    return out;
  }

  function randomDisplayFromBaseline() {
    const c = control();
    if (!baseline) throw new Error(t("cmd.needBaseline"));
    const deltas = readDeltas();
    return baseline.map((b, i) => {
      const d = deltas[i] ?? 0;
      let v = b + (Math.random() * 2 - 1) * d;
      if (c.mode === "gripper") {
        // clamp in display space using mapped limits of raw [0, 0.637] is imperfect when scale≠1;
        // keep soft clamp on display using value_min/max only when scales≈identity.
        const rs = readAffineColumn("rs-input", 1)[0];
        const ro = readAffineColumn("ro-input", 0)[0];
        const lo = Math.min(rs * (c.value_min ?? 0) + ro, rs * (c.value_max ?? 0.637) + ro);
        const hi = Math.max(rs * (c.value_min ?? 0) + ro, rs * (c.value_max ?? 0.637) + ro);
        v = Math.max(lo, Math.min(hi, v));
      }
      return v;
    });
  }

  function displayToRealCommand(displayValues) {
    const c = control();
    const ws = readAffineColumn("ws-input", 1);
    const wo = readAffineColumn("wo-input", 0);
    const real = applyAffine(displayValues, ws, wo);
    if (c.mode === "joints") {
      return { joints: real, display: displayValues };
    }
    return { position_norm: real[0], display: displayValues };
  }

  function randomCommandFromBaseline() {
    const display = randomDisplayFromBaseline();
    return displayToRealCommand(display);
  }

  async function sendCommand(command) {
    const bodyCmd = { ...command };
    delete bodyCmd.display;
    let res;
    if (sessionId) {
      res = await fetch(`/api/session/${encodeURIComponent(sessionId)}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: bodyCmd }),
      });
    } else {
      res = await fetch(`/api/command/${encodeURIComponent(currentDevice.id)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command: bodyCmd,
          config: collectFormConfig(),
          dry_run: dryRunEl.checked,
        }),
      });
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    data._display = command.display;
    data._real = bodyCmd;
    return data;
  }

  async function randomCommandOnce() {
    try {
      const command = randomCommandFromBaseline();
      commandHint.textContent = t("cmd.sending");
      const data = await sendCommand(command);
      const cr = data.command_result || {};
      const vars = {
        display: JSON.stringify(command.display),
        real: JSON.stringify(data._real),
      };
      commandHint.textContent = cr.dry_run ? t("cmd.dryRun", vars) : t("cmd.sent", vars);
    } catch (err) {
      commandHint.textContent = String(err.message || err);
    }
  }

  function updateSaveStreamBtn() {
    if (!btnSaveStream) return;
    const n = streamRecords.length;
    btnSaveStream.disabled = n === 0;
    btnSaveStream.textContent = n
      ? `${t("btn.saveStream")} (${n})`
      : t("btn.saveStream");
  }

  function recordStreamSample(payload) {
    streamRecords.push({
      t: new Date().toISOString(),
      tick: payload.tick ?? streamRecords.length,
      dry_run: !!payload.dry_run,
      sample: payload.sample ?? null,
      raw: extractRawFromPayload(payload),
      display: extractDisplayFromPayload(payload),
      config_used: payload.config_used ?? null,
    });
    updateSaveStreamBtn();
  }

  function clearStreamRecords() {
    streamRecords = [];
    streamRecording = false;
    updateSaveStreamBtn();
  }

  function saveStreamFile() {
    if (!streamRecords.length) {
      formHint.textContent = t("stream.nothing");
      return;
    }
    const id = currentDevice?.id || "sensor";
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const file = `sensors-view-${id}-${stamp}.json`;
    const payload = {
      saved_at: new Date().toISOString(),
      device_id: currentDevice?.id || null,
      kind: currentDevice?.kind || null,
      name: currentDevice?.name || null,
      hz: clampHz(rateEl.value),
      dry_run: !!dryRunEl.checked,
      started_at: streamStartedAt ? new Date(streamStartedAt).toISOString() : null,
      count: streamRecords.length,
      samples: streamRecords,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = file;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    formHint.textContent = t("stream.saved", { count: streamRecords.length, file });
  }

  function showViz(payload) {
    lastPayload = payload;
    if (streamRecording) recordStreamSample(payload);
    const viz = remappedViz(payload);
    modalPreview.hidden = false;
    vizNote.textContent = viz.note || (payload.dry_run ? t("viz.noteDry") : t("viz.noteLive"));
    renderMetrics(document.getElementById("modal-metrics"), viz.metrics);
    renderImages(document.getElementById("modal-images"), viz.images);
    renderCharts(document.getElementById("modal-charts"), viz.charts);
    const raw = extractRawFromPayload(payload);
    const disp = extractDisplayFromPayload(payload);
    vizJson.textContent = JSON.stringify(
      {
        tick: payload.tick,
        raw,
        display: disp,
        sample: payload.sample,
        config_used: payload.config_used,
        dry_run: payload.dry_run,
        session_id: payload.session_id,
      },
      null,
      2
    );
    if (control().writable && !baseline) {
      baselineHint.textContent = t("control.baselineReady");
    }
  }

  function updateStreamStatus(tick) {
    if (!sessionId) {
      streamStatus.textContent = "";
      return;
    }
    const hz = clampHz(rateEl.value);
    const elapsed = ((Date.now() - streamStartedAt) / 1000).toFixed(1);
    const auto = autoCommandEl.checked ? t("stream.auto") : "";
    streamStatus.textContent = t("stream.running", {
      hz,
      tick: tick ?? "—",
      elapsed,
      auto,
    });
  }

  function clearStreamTimer() {
    if (streamTimer) {
      clearInterval(streamTimer);
      streamTimer = null;
    }
  }

  async function stopStream({ quiet = false } = {}) {
    clearStreamTimer();
    const sid = sessionId;
    sessionId = null;
    streamRecording = false;
    updateSaveStreamBtn();
    setStreamingUi(false);
    if (!sid) {
      if (!quiet) formHint.textContent = t("form.stopped");
      updateStreamStatus();
      return;
    }
    try {
      await fetch(`/api/session/${encodeURIComponent(sid)}/stop`, { method: "POST" });
      if (!quiet) formHint.textContent = t("form.stoppedSample");
    } catch (err) {
      if (!quiet) formHint.textContent = t("form.stopFailed", { err: err.message || err });
    }
    updateStreamStatus();
  }

  async function tickOnce() {
    if (!sessionId || tickInFlight) return;
    tickInFlight = true;
    try {
      if (autoCommandEl.checked && control().writable && baseline) {
        try {
          await sendCommand(randomCommandFromBaseline());
        } catch (err) {
          commandHint.textContent = String(err.message || err);
        }
      }
      const res = await fetch(`/api/session/${encodeURIComponent(sessionId)}/tick`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      showViz(data);
      updateStreamStatus(data.tick);
    } catch (err) {
      formHint.textContent = String(err.message || err);
      await stopStream({ quiet: true });
    } finally {
      tickInFlight = false;
    }
  }

  function armStreamTimer() {
    clearStreamTimer();
    streamTimer = setInterval(tickOnce, intervalMs());
  }

  async function startStream() {
    if (!currentDevice?.id || sessionId) return;
    await stopBatch({ quiet: true });
    formHint.textContent = t("form.opening");
    btnStart.disabled = true;
    try {
      const res = await fetch(`/api/session/start/${encodeURIComponent(currentDevice.id)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config: collectFormConfig(),
          dry_run: dryRunEl.checked,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      sessionId = data.session_id;
      streamStartedAt = Date.now();
      streamRecords = [];
      streamRecording = true;
      updateSaveStreamBtn();
      setStreamingUi(true);
      showViz(data);
      updateStreamStatus(data.tick);
      formHint.textContent = t("form.streaming");
      armStreamTimer();
    } catch (err) {
      formHint.textContent = String(err.message || err);
      setStreamingUi(false);
    }
  }

  async function sampleOnce() {
    if (!currentDevice?.id || sessionId) return;
    formHint.textContent = t("form.onceBusy");
    btnOnce.disabled = true;
    try {
      const res = await fetch(`/api/sample/${encodeURIComponent(currentDevice.id)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config: collectFormConfig(),
          dry_run: dryRunEl.checked,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      formHint.textContent = t("form.onceDone");
      showViz(data);
      streamStatus.textContent = t("stream.once");
    } catch (err) {
      formHint.textContent = String(err.message || err);
    } finally {
      btnOnce.disabled = false;
    }
  }

  async function openModal(id) {
    if (!id) return;
    await stopStream({ quiet: true });
    formHint.textContent = t("form.loading");
    modal.hidden = false;
    modalPreview.hidden = true;
    streamStatus.textContent = "";
    lastPayload = null;
    clearStreamRecords();
    baseline = null;
    commandHint.textContent = "";
    baselineHint.textContent = t("control.baselineNone");
    try {
      const res = await fetch(`/api/device/${encodeURIComponent(id)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      currentDevice = data;
      modalTitle.textContent = data.name || data.id;
      modalKind.textContent = `${data.kind} · ${data.id}`;
      dryRunEl.checked = !!data.dry_run_default;

      const fields = data.fields || [];
      if (!fields.length) {
        formFields.innerHTML = `<p class="msg">${escapeHtml(t("form.noFields"))}</p>`;
      } else {
        formFields.innerHTML = fields
          .map((f) => {
            const val = escapeHtml(fieldValue(data.config, f.key, f.as));
            const inputType = f.type === "number" && f.as !== "int_list" ? "number" : "text";
            const label = fieldLabel(f.key, f.label);
            return `
              <label class="field">
                <span class="field-label">${escapeHtml(label)}</span>
                <input name="${escapeHtml(f.key)}" type="${inputType}" value="${val}" data-as="${escapeHtml(f.as || "")}" />
              </label>
            `;
          })
          .join("");
      }
      showControlPanel();
      formHint.textContent = control().writable ? t("form.hint.writable") : t("form.hint.sample");
      setStreamingUi(false);
    } catch (err) {
      formHint.textContent = String(err.message || err);
      currentDevice = { id, fields: [], config: deviceCache[id]?.config || {}, control: { writable: false } };
      modalTitle.textContent = id;
      modalKind.textContent = deviceCache[id]?.kind || "device";
      formFields.innerHTML = "";
      controlPanel.hidden = true;
    }
  }

  async function closeModal() {
    modal.hidden = true;
    await stopStream({ quiet: true });
  }

  async function loadMeta() {
    const res = await fetch("/api/meta");
    if (!res.ok) throw new Error(`meta ${res.status}`);
    const meta = await res.json();
    setText("meta-site", meta.site || "—");
    setText("meta-count", String(meta.count ?? "—"));
    setText("meta-mode", meta.dry_run ? "dry-run" : "live");
    if (batchDryRunEl && !batchRunning) batchDryRunEl.checked = !!meta.dry_run;
    setText("meta-config", meta.sensors_config || "—");
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
      setText("meta-updated", new Date().toLocaleTimeString(window.SensorsI18n?.getLocale?.() === "en" ? "en-US" : "zh-CN"));
    } catch (err) {
      summary.innerHTML = `<span class="chip" data-status="error">${escapeHtml(t("err.probe", { err: err.message || err }))}</span>`;
    } finally {
      busy = false;
      btnRefresh.disabled = false;
    }
  }

  async function reloadCfg() {
    btnReload.disabled = true;
    try {
      await stopStream({ quiet: true });
      const res = await fetch("/api/reload", { method: "POST" });
      if (!res.ok) throw new Error(`reload ${res.status}`);
      await probe();
    } catch (err) {
      summary.innerHTML = `<span class="chip" data-status="error">${escapeHtml(t("err.reload", { err: err.message || err }))}</span>`;
    } finally {
      btnReload.disabled = false;
    }
  }

  form.addEventListener("submit", (e) => e.preventDefault());
  btnStart.addEventListener("click", startStream);
  btnStop.addEventListener("click", () => stopStream());
  btnOnce.addEventListener("click", sampleOnce);
  btnSaveStream?.addEventListener("click", saveStreamFile);
  btnCapture.addEventListener("click", captureBaseline);
  btnRandomCmd.addEventListener("click", randomCommandOnce);
  rateEl.addEventListener("change", () => {
    rateEl.value = String(clampHz(rateEl.value));
    if (sessionId) {
      armStreamTimer();
      updateStreamStatus();
      formHint.textContent = t("form.rateChanged", { hz: clampHz(rateEl.value) });
    }
  });

  btnRefresh.addEventListener("click", probe);
  btnReload.addEventListener("click", reloadCfg);
  btnBatchStart?.addEventListener("click", () => {
    startBatch().catch((err) => {
      if (batchHint) batchHint.textContent = String(err.message || err);
    });
  });
  btnBatchStop?.addEventListener("click", () => {
    stopBatch().catch((err) => {
      if (batchHint) batchHint.textContent = String(err.message || err);
    });
  });
  btnBatchSave?.addEventListener("click", saveBatchFile);
  batchRateEl?.addEventListener("change", () => {
    if (batchRateEl) batchRateEl.value = String(clampBatchHz(batchRateEl.value));
    if (batchRunning) {
      clearBatchTimer();
      batchTimer = setInterval(tickBatchOnce, batchIntervalMs());
    }
  });
  btnLogout?.addEventListener("click", logout);
  btnUsers?.addEventListener("click", () => {
    openUsersModal().catch((err) => {
      usersHint.textContent = String(err.message || err);
    });
  });
  usersClose?.addEventListener("click", closeUsersModal);

  passwordForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    passwordHint.textContent = "";
    try {
      const res = await fetch("/api/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: document.getElementById("pw-current").value,
          new_password: document.getElementById("pw-new").value,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data) || `HTTP ${res.status}`);
      passwordHint.textContent = t("users.passwordOk");
      passwordForm.reset();
    } catch (err) {
      passwordHint.textContent = String(err.message || err);
    }
  });

  userCreateForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    usersHint.textContent = "";
    try {
      const res = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("user-new-name").value.trim(),
          password: document.getElementById("user-new-pass").value,
          role: document.getElementById("user-new-role").value,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data) || `HTTP ${res.status}`);
      userCreateForm.reset();
      usersHint.textContent = t("users.created", { user: data.user?.username || "" });
      await loadUsers();
    } catch (err) {
      usersHint.textContent = String(err.message || err);
    }
  });

  usersTbody?.addEventListener("change", async (e) => {
    const roleEl = e.target.closest(".user-role");
    const enEl = e.target.closest(".user-enabled");
    try {
      if (roleEl) {
        await patchUser(roleEl.dataset.user, { role: roleEl.value });
        usersHint.textContent = t("users.updated", { user: roleEl.dataset.user });
      } else if (enEl) {
        await patchUser(enEl.dataset.user, { enabled: enEl.checked });
        usersHint.textContent = t("users.updated", { user: enEl.dataset.user });
      }
    } catch (err) {
      usersHint.textContent = String(err.message || err);
      await loadUsers();
    }
  });

  usersTbody?.addEventListener("click", async (e) => {
    const resetBtn = e.target.closest(".user-reset");
    const delBtn = e.target.closest(".user-del");
    try {
      if (resetBtn) {
        const user = resetBtn.dataset.user;
        const pw = window.prompt(t("users.resetPrompt", { user }), "");
        if (pw == null || pw === "") return;
        await patchUser(user, { password: pw });
        usersHint.textContent = t("users.updated", { user });
      } else if (delBtn) {
        const user = delBtn.dataset.user;
        if (!window.confirm(`${t("users.delete")}: ${user}?`)) return;
        const res = await fetch(`/api/users/${encodeURIComponent(user)}`, { method: "DELETE" });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiDetail(data) || `HTTP ${res.status}`);
        usersHint.textContent = t("users.deleted", { user });
        await loadUsers();
      }
    } catch (err) {
      usersHint.textContent = String(err.message || err);
      await loadUsers();
    }
  });

  modalClose.addEventListener("click", closeModal);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (usersModal && !usersModal.hidden) {
      e.preventDefault();
      closeUsersModal();
    } else if (!modal.hidden) {
      e.preventDefault();
      closeModal();
    }
  });
  window.addEventListener("beforeunload", () => {
    if (sessionId) {
      navigator.sendBeacon?.(`/api/session/${encodeURIComponent(sessionId)}/stop`);
    }
    for (const s of batchSessions) {
      navigator.sendBeacon?.(`/api/session/${encodeURIComponent(s.sessionId)}/stop`);
    }
  });

  window.SensorsI18n?.onLocaleChange?.(() => {
    if (lastDevices.length) renderCards(lastDevices);
    updateSaveStreamBtn();
    setBatchUi();
    if (batchRunning && batchHint) {
      batchHint.textContent = t("batch.running", {
        n: batchSessions.length,
        hz: clampBatchHz(batchRateEl?.value),
        tick: batchFrames[batchFrames.length - 1]?.tick || "—",
        count: batchFrames.length,
      });
    } else if (batchCanSave && batchHint && batchFrames.length) {
      batchHint.textContent = t("batch.stopped", { count: batchFrames.length });
    }
    if (!modal.hidden && currentDevice) {
      const writable = control().writable;
      if (writable) showControlPanel();
      if (!sessionId && !lastPayload) {
        formHint.textContent = writable ? t("form.hint.writable") : t("form.hint.sample");
        baselineHint.textContent = baseline
          ? t("control.baselineCaptured", { vals: baseline.map((v) => v.toFixed(3)).join(", ") })
          : t("control.baselineNone");
      } else if (lastPayload) {
        const wasRecording = streamRecording;
        streamRecording = false;
        showViz(lastPayload);
        streamRecording = wasRecording;
        updateStreamStatus();
      }
      formFields.querySelectorAll(".field").forEach((labelEl) => {
        const input = labelEl.querySelector("input[name]");
        const span = labelEl.querySelector(".field-label");
        if (input && span) span.textContent = fieldLabel(input.name, span.textContent);
      });
    }
  });

  (async () => {
    if (await requireAuth()) probe();
  })();
})();
