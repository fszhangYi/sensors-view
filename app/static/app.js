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
  const batchDryRunEl = document.getElementById("batch-dry-run");
  const btnBatchStart = document.getElementById("btn-batch-start");
  const btnBatchStop = document.getElementById("btn-batch-stop");
  const btnBatchSave = document.getElementById("btn-batch-save");
  const btnBatchPost = document.getElementById("btn-batch-post");
  const batchSeqEl = document.getElementById("batch-seq");
  const batchSeqWrap = document.getElementById("batch-seq-wrap");
  const batchHint = document.getElementById("batch-hint");
  const exportDirEl = document.getElementById("export-dir");
  const liveModal = document.getElementById("live-modal");
  const liveStage = document.getElementById("live-stage");
  const liveStatusList = document.getElementById("live-status-list");
  const liveHint = document.getElementById("live-hint");
  const btnLiveStop = document.getElementById("btn-live-stop");
  const btnLiveClose = document.getElementById("btn-live-close");
  const btnLiveSave = document.getElementById("btn-live-save");
  const btnLivePost = document.getElementById("btn-live-post");
  const liveSeqEl = document.getElementById("live-seq");
  const liveSeqWrap = document.getElementById("live-seq-wrap");
  const rateBoundsHint = document.getElementById("rate-bounds-hint");
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

  const RATE_PREFS_KEY = "sensors-view.ratePrefs";
  /** @type {Record<string, { min: number, max: number, defaultHz: number }>} */
  const KIND_RATE_DEFAULTS = {
    realsense: { min: 5, max: 30, defaultHz: 15 },
    arm: { min: 100, max: 1000, defaultHz: 100 },
    gello: { min: 100, max: 1000, defaultHz: 100 },
    gripper: { min: 1, max: 50, defaultHz: 10 },
    tactile: { min: 1, max: 50, defaultHz: 10 },
    ft: { min: 100, max: 2000, defaultHz: 200 },
    bus: { min: 1, max: 50, defaultHz: 10 },
    pipeline: { min: 1, max: 50, defaultHz: 10 },
  };
  const FALLBACK_RATE = { min: 1, max: 50, defaultHz: 10 };
  const RATE_WINDOW = 24;
  const RATE_TOL_RATIO = 0.2;

  let busy = false;
  let currentDevice = null;
  let sessionId = null;
  let streamTimer = null;
  let tickInFlight = false;
  let streamStartedAt = 0;
  let lastPayload = null;
  let streamRecords = [];
  let streamRecording = false;
  /** @type {number[]} */
  let streamRateTimes = [];
  let streamMeasuredHz = null;
  let streamRateOk = null;
  let baseline = null; // number[]
  let lastDevices = [];
  const deviceCache = {};
  const selectedIds = new Set();
  /** ids that already received a default checkbox decision */
  const selectionSeeded = new Set();
  const DEFAULT_UNCHECKED_KINDS = new Set(["tactile", "ft", "bus"]);
  /** @type {Record<string, { hz: number, hzMin: number, hzMax: number }>} */
  let ratePrefs = loadRatePrefs();
  let batchRunning = false;
  let batchStartedAt = 0;
  /**
   * @type {{
   *   id: string,
   *   sessionId: string,
   *   kind: string,
   *   name: string,
   *   hz: number,
   *   hzMin: number,
   *   hzMax: number,
   *   timer: ReturnType<typeof setInterval> | null,
   *   tickInFlight: boolean,
   *   times: number[],
   *   measuredHz: number | null,
   *   rateOk: boolean | null,
   *   sampleCount: number,
   * }[]}
   */
  let batchSessions = [];
  /** @type {Record<string, object[]>} */
  let batchStreams = {};
  /** @type {Record<string, { hz: number, hzMin: number, hzMax: number, measuredHz: number | null, rateOk: boolean | null, kind: string, name: string }>} */
  let batchMeta = {};
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

  function loadRatePrefs() {
    try {
      const raw = localStorage.getItem(RATE_PREFS_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  function saveRatePrefs() {
    try {
      localStorage.setItem(RATE_PREFS_KEY, JSON.stringify(ratePrefs));
    } catch {
      /* ignore quota */
    }
  }

  function kindRateDefaults(kind) {
    return KIND_RATE_DEFAULTS[kind] || FALLBACK_RATE;
  }

  function getRatePrefs(id, kind) {
    const def = kindRateDefaults(kind);
    const saved = ratePrefs[id] || {};
    let hzMin = Number(saved.hzMin);
    let hzMax = Number(saved.hzMax);
    let hz = Number(saved.hz);
    if (!Number.isFinite(hzMin)) hzMin = def.min;
    if (!Number.isFinite(hzMax)) hzMax = def.max;
    if (hzMax < hzMin) {
      const tmp = hzMin;
      hzMin = hzMax;
      hzMax = tmp;
    }
    if (!Number.isFinite(hz)) hz = def.defaultHz;
    hz = Math.min(hzMax, Math.max(hzMin, hz));
    return { hz, hzMin, hzMax };
  }

  function setRatePrefs(id, kind, patch) {
    const cur = getRatePrefs(id, kind);
    const next = { ...cur, ...patch };
    if (next.hzMax < next.hzMin) {
      const tmp = next.hzMin;
      next.hzMin = next.hzMax;
      next.hzMax = tmp;
    }
    next.hz = Math.min(next.hzMax, Math.max(next.hzMin, Number(next.hz)));
    ratePrefs[id] = next;
    saveRatePrefs();
    return next;
  }

  function clampDeviceHz(v, prefs) {
    const n = Number(v);
    if (!Number.isFinite(n)) return prefs.hz;
    return Math.min(prefs.hzMax, Math.max(prefs.hzMin, n));
  }

  function intervalMsForHz(hz) {
    const n = Number(hz);
    if (!Number.isFinite(n) || n <= 0) return 500;
    return Math.max(1, Math.round(1000 / n));
  }

  function observeRate(times, hz, now = performance.now()) {
    times.push(now);
    while (times.length > RATE_WINDOW) times.shift();
    if (times.length < 3) {
      return { measured: null, ok: null };
    }
    const span = times[times.length - 1] - times[0];
    if (span <= 0) return { measured: null, ok: null };
    const measured = ((times.length - 1) * 1000) / span;
    const target = Number(hz) || 0;
    const tol = Math.max(target * RATE_TOL_RATIO, Math.min(2, Math.max(0.5, target * 0.05)));
    const ok = Math.abs(measured - target) <= tol;
    return { measured, ok };
  }

  function formatMeasured(hz) {
    if (hz == null || !Number.isFinite(hz)) return "—";
    if (hz >= 100) return hz.toFixed(0);
    if (hz >= 10) return hz.toFixed(1);
    return hz.toFixed(2);
  }

  function rateStatusLabel(ok) {
    if (ok === true) return t("stream.rateOk");
    if (ok === false) return t("stream.rateBad");
    return t("stream.rateWarm");
  }

  function clampHz(v) {
    if (!currentDevice) {
      const n = Number(v);
      if (!Number.isFinite(n)) return 2;
      return Math.min(2000, Math.max(0.2, n));
    }
    const prefs = getRatePrefs(currentDevice.id, currentDevice.kind);
    return clampDeviceHz(v, prefs);
  }

  function intervalMs() {
    return intervalMsForHz(clampHz(rateEl.value));
  }

  function applyModalRateBounds() {
    if (!currentDevice || !rateEl) return;
    const prefs = getRatePrefs(currentDevice.id, currentDevice.kind);
    rateEl.min = String(prefs.hzMin);
    rateEl.max = String(prefs.hzMax);
    rateEl.step = prefs.hzMax >= 100 ? "1" : "0.1";
    rateEl.value = String(prefs.hz);
    if (rateBoundsHint) {
      rateBoundsHint.textContent = t("field.rateBounds", {
        min: prefs.hzMin,
        max: prefs.hzMax,
      });
    }
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

  function isOnlineStatus(status) {
    return status === "ok" || status === "warn";
  }

  function batchSampleTotal() {
    return Object.values(batchStreams).reduce((n, arr) => n + (arr?.length || 0), 0);
  }

  function batchRateOkCount() {
    return batchSessions.filter((s) => s.rateOk === true).length;
  }

  function updateBatchHintText() {
    if (!batchHint || !batchRunning) return;
    batchHint.textContent = t("batch.running", {
      n: batchSessions.length,
      count: batchSampleTotal(),
      ok: batchRateOkCount(),
    });
  }

  function setBatchUi() {
    if (!btnBatchStart) return;
    btnBatchStart.disabled = batchRunning;
    btnBatchStop.disabled = !batchRunning;
    if (batchDryRunEl) batchDryRunEl.disabled = batchRunning;
    grid?.querySelectorAll(".card-check").forEach((el) => {
      el.disabled = batchRunning;
    });
    grid?.querySelectorAll(".card-rate input").forEach((el) => {
      if (el.classList.contains("card-hz")) return;
      el.disabled = batchRunning;
    });
    const showSave = batchCanSave && !batchRunning && batchSampleTotal() > 0;
    const dirReady = !!String(exportDirEl?.value || "").trim();
    const showPost = !batchRunning && dirReady;
    if (batchSeqWrap) batchSeqWrap.hidden = !(showSave || showPost);
    if (btnBatchSave) {
      btnBatchSave.hidden = !showSave;
      btnBatchSave.disabled = !showSave;
    }
    if (btnBatchPost) {
      btnBatchPost.hidden = !showPost;
      btnBatchPost.disabled = !showPost;
    }
    if (btnLiveStop) btnLiveStop.disabled = !batchRunning;
    if (liveSeqWrap) liveSeqWrap.hidden = !(showSave || showPost);
    if (btnLiveSave) {
      btnLiveSave.hidden = !showSave;
      btnLiveSave.disabled = !showSave;
    }
    if (btnLivePost) {
      btnLivePost.hidden = !showPost;
      btnLivePost.disabled = !showPost;
    }
    if ((showSave || showPost) && liveSeqEl && batchSeqEl && !liveSeqEl.value) {
      liveSeqEl.value = batchSeqEl.value || "";
    }
  }

  /** @type {Record<string, object>} */
  let livePayloads = {};

  function isCameraKind(kind) {
    return kind === "realsense";
  }

  const CAM_ID_ORDER = ["rs-left", "rs-right", "rs-middle"];

  function sortCameraSessions(sessions) {
    return sessions
      .filter((s) => isCameraKind(s.kind))
      .sort((a, b) => {
        const ia = CAM_ID_ORDER.indexOf(a.id);
        const ib = CAM_ID_ORDER.indexOf(b.id);
        const sa = ia === -1 ? 100 : ia;
        const sb = ib === -1 ? 100 : ib;
        if (sa !== sb) return sa - sb;
        return String(a.id).localeCompare(String(b.id));
      })
      .slice(0, 3);
  }

  function formatDigit(v, digits = 3) {
    if (v == null || v === "") return "—";
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v);
    if (Math.abs(n) >= 1000) return n.toFixed(0);
    if (Math.abs(n) >= 100) return n.toFixed(1);
    if (Math.abs(n) >= 10) return n.toFixed(2);
    return n.toFixed(digits);
  }

  function digitsFromPayload(payload) {
    const kind = payload?.kind || "";
    const sample = payload?.sample || {};
    const viz = payload?.viz || {};
    /** @type {{ label: string, value: string }[]} */
    const rows = [];

    // Prefer viz charts (dry-run arm/gripper put values here while sample.* is null)
    for (const ch of viz.charts || []) {
      if (!ch || typeof ch !== "object") continue;
      if (ch.type === "bars" && Array.isArray(ch.values) && ch.values.length) {
        const labels = ch.labels || [];
        const prefix = String(ch.title || "")
          .replace(/\s*\([^)]*\)\s*/g, "")
          .trim()
          .slice(0, 6);
        ch.values.forEach((v, i) => {
          const lab = labels[i] != null && labels[i] !== "" ? String(labels[i]) : `${prefix || "v"}${i + 1}`;
          rows.push({ label: lab, value: formatDigit(v) });
        });
      } else if (ch.type === "gauge" && ch.value != null && Number.isFinite(Number(ch.value))) {
        const lab = String(ch.title || "val")
          .replace(/\s*\([^)]*\)\s*/g, "")
          .trim()
          .slice(0, 8) || "val";
        rows.push({ label: lab, value: formatDigit(ch.value) });
      }
    }
    if (rows.length) return rows.slice(0, 18);

    if (kind === "arm" || kind === "gello") {
      const joints = sample.joints || sample.joints_rad || sample.arm_joints || [];
      if (Array.isArray(joints) && joints.length) {
        joints.forEach((v, i) => rows.push({ label: `j${i + 1}`, value: formatDigit(v) }));
      }
    } else if (kind === "gripper") {
      if (sample.position_norm != null) rows.push({ label: "norm", value: formatDigit(sample.position_norm) });
      if (sample.position_raw != null) rows.push({ label: "raw", value: String(sample.position_raw) });
      if (sample.grip_detected != null) rows.push({ label: "grip", value: String(sample.grip_detected) });
      if (sample.init_state != null) rows.push({ label: "init", value: String(sample.init_state) });
    } else if (kind === "ft") {
      const force = sample.force || [];
      const torque = sample.torque || [];
      ["Fx", "Fy", "Fz"].forEach((lab, i) => {
        if (force[i] != null) rows.push({ label: lab, value: formatDigit(force[i]) });
      });
      ["Tx", "Ty", "Tz"].forEach((lab, i) => {
        if (torque[i] != null) rows.push({ label: lab, value: formatDigit(torque[i]) });
      });
    } else if (kind === "tactile") {
      const rf = sample.rest_force;
      if (Array.isArray(rf)) {
        ["Rx", "Ry", "Rz"].forEach((lab, i) => rows.push({ label: lab, value: formatDigit(rf[i]) }));
      } else if (rf != null) {
        rows.push({ label: "rest", value: formatDigit(rf) });
      }
      if (sample.contact_force != null) rows.push({ label: "Fz", value: formatDigit(sample.contact_force) });
    }

    if (!rows.length) {
      for (const m of viz.metrics || []) {
        const label = String(m.label || "");
        if (!label || label === "tick") continue;
        rows.push({ label, value: String(m.value ?? "—") });
        if (rows.length >= 12) break;
      }
    }
    return rows.slice(0, 18);
  }

  function liveStatusText(s) {
    if (s.rateOk === false) return t("status.rate");
    if (s.rateOk === true) return "ok";
    if (batchRunning) return t("live.statusWarm");
    return deviceCache[s.id]?.status || "—";
  }

  function liveStatusKind(s) {
    if (s.rateOk === false) return "rate";
    if (s.rateOk === true) return "ok";
    return deviceCache[s.id]?.status || "unknown";
  }

  function applyLiveGrid2x2() {
    if (!liveStage) return;
    liveStage.style.setProperty("--live-cols", "2");
    liveStage.style.setProperty("--live-rows", "2");
    liveStage.classList.add("is-2x2");
  }

  function renderCamTileHtml(s, slot) {
    if (!s) {
      return `
        <article class="live-tile live-cam is-empty" data-slot="${slot}">
          <div class="live-tile-head">
            <div>
              <p class="live-tile-kind">camera · ${slot + 1}</p>
              <h3>${escapeHtml(t("live.camEmpty"))}</h3>
            </div>
          </div>
          <div class="live-tile-body live-cam-body">
            <div class="live-cam-placeholder">${escapeHtml(t("live.camEmpty"))}</div>
          </div>
        </article>`;
    }
    const st = liveStatusKind(s);
    return `
      <article class="live-tile live-cam" data-id="${escapeHtml(s.id)}" data-slot="${slot}" data-status="${escapeHtml(st)}">
        <div class="live-tile-head">
          <div>
            <p class="live-tile-kind">${escapeHtml(s.kind)} · ${escapeHtml(s.id)}</p>
            <h3>${escapeHtml(s.name || s.id)}</h3>
          </div>
          <span class="status-pill" data-status="${escapeHtml(st)}">${escapeHtml(liveStatusText(s))}</span>
        </div>
        <p class="live-tile-meta">${escapeHtml(
          t("live.tileMeta", {
            hz: s.hz,
            measured: formatMeasured(s.measuredHz),
            tick: "—",
          })
        )}</p>
        <div class="live-tile-body live-cam-body">
          <div class="viz-images"></div>
        </div>
      </article>`;
  }

  function renderNumericBlockHtml(s) {
    const st = liveStatusKind(s);
    return `
      <div class="live-num-block" data-id="${escapeHtml(s.id)}" data-status="${escapeHtml(st)}">
        <div class="live-num-head">
          <div>
            <p class="live-num-kind">${escapeHtml(s.kind)} · ${escapeHtml(s.id)}</p>
            <h4>${escapeHtml(s.name || s.id)}</h4>
          </div>
          <span class="status-pill" data-status="${escapeHtml(st)}">${escapeHtml(liveStatusText(s))}</span>
        </div>
        <p class="live-tile-meta">${escapeHtml(
          t("live.tileMeta", {
            hz: s.hz,
            measured: formatMeasured(s.measuredHz),
            tick: "—",
          })
        )}</p>
        <div class="live-num-digits"></div>
      </div>`;
  }

  function buildLiveDashboard(sessions, initialPayloads = {}) {
    if (!liveStage || !liveStatusList) return;
    livePayloads = { ...initialPayloads };
    applyLiveGrid2x2();
    const cams = sortCameraSessions(sessions);
    const others = sessions.filter((s) => !isCameraKind(s.kind));
    const camSlots = [cams[0] || null, cams[1] || null, cams[2] || null];

    liveStatusList.innerHTML = sessions
      .map((s) => {
        const st = liveStatusKind(s);
        return `
          <div class="live-status-item" data-id="${escapeHtml(s.id)}">
            <p class="name">${escapeHtml(s.name || s.id)}</p>
            <span class="status-pill" data-status="${escapeHtml(st)}">${escapeHtml(liveStatusText(s))}</span>
            <p class="sub">${escapeHtml(s.kind)} · ${escapeHtml(s.id)}</p>
          </div>`;
      })
      .join("");

    liveStage.innerHTML = `
      ${camSlots.map((s, i) => renderCamTileHtml(s, i)).join("")}
      <article class="live-tile live-numeric" data-slot="3">
        <div class="live-tile-head">
          <div>
            <p class="live-tile-kind">numeric</p>
            <h3>${escapeHtml(t("live.othersTitle"))}</h3>
          </div>
        </div>
        <div class="live-tile-body">
          <div class="live-numeric-grid" id="live-numeric-grid">
            ${
              others.length
                ? others.map((s) => renderNumericBlockHtml(s)).join("")
                : `<p class="live-num-empty">${escapeHtml(t("live.noOthers"))}</p>`
            }
          </div>
        </div>
      </article>`;

    for (const s of sessions) {
      const payload = initialPayloads[s.id];
      if (payload) updateLiveTile(s, payload);
    }
    if (liveHint) {
      liveHint.textContent = t("batch.running", {
        n: sessions.length,
        count: batchSampleTotal(),
        ok: batchRateOkCount(),
      });
    }
  }

  function openLiveDashboard(sessions, initialPayloads = {}) {
    buildLiveDashboard(sessions, initialPayloads);
    if (liveModal) liveModal.hidden = false;
    setBatchUi();
  }

  function closeLiveDashboard() {
    if (liveModal) liveModal.hidden = true;
    if (liveStage) {
      liveStage.innerHTML = "";
      liveStage.classList.remove("is-2x2");
    }
    if (liveStatusList) liveStatusList.innerHTML = "";
    if (liveHint) liveHint.textContent = "";
    livePayloads = {};
  }

  async function dismissLiveDashboard() {
    if (batchRunning) await stopBatch({ quiet: true });
    closeLiveDashboard();
  }

  function updateLiveStatusItem(s) {
    const esc = String(s.id).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    const statusItem = liveStatusList?.querySelector(`.live-status-item[data-id="${esc}"]`);
    if (!statusItem) return;
    const pill = statusItem.querySelector(".status-pill");
    if (pill) {
      const st = liveStatusKind(s);
      pill.dataset.status = st;
      pill.textContent = liveStatusText(s);
    }
  }

  function updateLiveCameraTile(s, payload) {
    const esc = String(s.id).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    const tile = liveStage?.querySelector(`.live-cam[data-id="${esc}"]`);
    if (!tile) return;
    const st = liveStatusKind(s);
    tile.dataset.status = st;
    const pill = tile.querySelector(".status-pill");
    if (pill) {
      pill.dataset.status = st;
      pill.textContent = liveStatusText(s);
    }
    const meta = tile.querySelector(".live-tile-meta");
    if (meta) {
      meta.textContent = t("live.tileMeta", {
        hz: s.hz,
        measured: formatMeasured(s.measuredHz),
        tick: payload?.tick ?? "—",
      });
    }
    const images = (payload?.viz?.images || []).slice(0, 1);
    renderImages(tile.querySelector(".viz-images"), images);
  }

  function updateLiveNumericBlock(s, payload) {
    const esc = String(s.id).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    const block = liveStage?.querySelector(`.live-num-block[data-id="${esc}"]`);
    if (!block) return;
    const st = liveStatusKind(s);
    block.dataset.status = st;
    const pill = block.querySelector(".status-pill");
    if (pill) {
      pill.dataset.status = st;
      pill.textContent = liveStatusText(s);
    }
    const meta = block.querySelector(".live-tile-meta");
    if (meta) {
      meta.textContent = t("live.tileMeta", {
        hz: s.hz,
        measured: formatMeasured(s.measuredHz),
        tick: payload?.tick ?? "—",
      });
    }
    const digits = digitsFromPayload({ ...payload, kind: payload?.kind || s.kind });
    const digitsEl = block.querySelector(".live-num-digits");
    if (digitsEl) {
      digitsEl.innerHTML = digits.length
        ? digits
            .map(
              (d) => `
            <div class="live-digit">
              <span class="live-digit-k">${escapeHtml(d.label)}</span>
              <span class="live-digit-v">${escapeHtml(d.value)}</span>
            </div>`
            )
            .join("")
        : `<div class="live-digit"><span class="live-digit-k">—</span><span class="live-digit-v">—</span></div>`;
    }
  }

  function updateLiveTile(s, payload) {
    if (payload) livePayloads[s.id] = payload;
    updateLiveStatusItem(s);
    if (isCameraKind(s.kind)) {
      updateLiveCameraTile(s, payload || livePayloads[s.id]);
    } else {
      updateLiveNumericBlock(s, payload || livePayloads[s.id]);
    }
    if (liveHint && batchRunning) {
      liveHint.textContent = t("batch.running", {
        n: batchSessions.length,
        count: batchSampleTotal(),
        ok: batchRateOkCount(),
      });
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

  function cardSelector(id) {
    return `.card[data-id="${String(id).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"]`;
  }

  function updateCardRateUi(id, { measured, ok, probeStatus } = {}) {
    const card = grid?.querySelector(cardSelector(id));
    if (!card) return;
    const measuredEl = card.querySelector(".card-rate-measured");
    if (measuredEl) {
      measuredEl.textContent =
        measured == null
          ? t("card.measuredWarm")
          : t("card.measured", { hz: formatMeasured(measured) });
    }
    const pill = card.querySelector(".status-pill");
    if (!pill) return;
    if (ok === false) {
      pill.dataset.status = "rate";
      pill.textContent = t("status.rate");
      card.dataset.status = "rate";
    } else if (ok === true) {
      pill.dataset.status = "ok";
      pill.textContent = "ok";
      card.dataset.status = "ok";
    } else if (probeStatus != null) {
      pill.dataset.status = probeStatus;
      pill.textContent = probeStatus;
      card.dataset.status = probeStatus;
    }
  }

  function restoreCardProbeStatuses() {
    for (const d of lastDevices) {
      updateCardRateUi(d.id, { measured: null, ok: null, probeStatus: d.status });
      const measuredEl = grid?.querySelector(`${cardSelector(d.id)} .card-rate-measured`);
      if (measuredEl) measuredEl.textContent = t("card.measuredWarm");
    }
  }

  function frameReadingFromPayload(payload) {
    const viz = payload.viz || null;
    // Keep images (and light charts) so 批后处理 can rebuild hik rgb_*/steps
    let vizLight = null;
    if (viz && typeof viz === "object") {
      vizLight = {
        images: Array.isArray(viz.images) ? viz.images : [],
        charts: Array.isArray(viz.charts) ? viz.charts : [],
        metrics: Array.isArray(viz.metrics) ? viz.metrics : [],
      };
    }
    return {
      tick: payload.tick,
      dry_run: !!payload.dry_run,
      sample: payload.sample ?? null,
      raw: extractRawFromPayload(payload),
      display: extractDisplayFromPayload(payload),
      config_used: payload.config_used ?? null,
      kind: payload.kind || null,
      name: payload.name || null,
      viz: vizLight,
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

  function clearBatchTimers() {
    for (const s of batchSessions) {
      if (s.timer) {
        clearInterval(s.timer);
        s.timer = null;
      }
    }
  }

  function armBatchSessionTimer(s) {
    if (s.timer) {
      clearInterval(s.timer);
      s.timer = null;
    }
    s.timer = setInterval(() => {
      tickBatchDevice(s).catch(() => {});
    }, intervalMsForHz(s.hz));
  }

  async function tickBatchDevice(s) {
    if (!batchRunning || s.tickInFlight) return;
    s.tickInFlight = true;
    try {
      const res = await fetch(`/api/session/${encodeURIComponent(s.sessionId)}/tick`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(`${s.id}: ${data.detail || res.status}`);
      const reading = frameReadingFromPayload(data);
      if (!batchStreams[s.id]) batchStreams[s.id] = [];
      batchStreams[s.id].push({
        t: new Date().toISOString(),
        ...reading,
      });
      s.sampleCount = batchStreams[s.id].length;
      const evaled = observeRate(s.times, s.hz);
      s.measuredHz = evaled.measured;
      s.rateOk = evaled.ok;
      if (batchMeta[s.id]) {
        batchMeta[s.id].measuredHz = s.measuredHz;
        batchMeta[s.id].rateOk = s.rateOk;
        batchMeta[s.id].hz = s.hz;
      }
      updateCardRateUi(s.id, { measured: s.measuredHz, ok: s.rateOk });
      updateLiveTile(s, data);
      updateBatchHintText();
    } catch (err) {
      if (batchHint) batchHint.textContent = String(err.message || err);
      if (liveHint) liveHint.textContent = String(err.message || err);
      await stopBatch({ quiet: true });
    } finally {
      s.tickInFlight = false;
    }
  }

  async function stopBatch({ quiet = false } = {}) {
    clearBatchTimers();
    const sessions = batchSessions.slice();
    batchSessions = [];
    batchRunning = false;
    batchCanSave = batchSampleTotal() > 0;
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
    restoreCardProbeStatuses();
    const msg = t("batch.stopped", { count: batchSampleTotal() });
    if (!quiet && batchHint) batchHint.textContent = msg;
    if (liveHint) liveHint.textContent = msg;
    setBatchUi();
  }

  async function startBatch() {
    const ids = selectedDeviceIds();
    if (!ids.length) {
      if (batchHint) batchHint.textContent = t("batch.none");
      return;
    }
    if (batchRunning) return;
    await stopStream({ quiet: true });
    batchStreams = {};
    batchMeta = {};
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
      const initialPayloads = {};
      for (const id of ids) {
        try {
          const data = await startBatchSession(id);
          const kind = data.kind || deviceCache[id]?.kind || "";
          const prefs = getRatePrefs(id, kind);
          const session = {
            id,
            sessionId: data.session_id,
            kind,
            name: data.name || deviceCache[id]?.name || id,
            hz: prefs.hz,
            hzMin: prefs.hzMin,
            hzMax: prefs.hzMax,
            timer: null,
            tickInFlight: false,
            times: [],
            measuredHz: null,
            rateOk: null,
            sampleCount: 0,
          };
          batchStreams[id] = [
            {
              t: new Date().toISOString(),
              ...frameReadingFromPayload(data),
            },
          ];
          session.sampleCount = 1;
          batchMeta[id] = {
            hz: session.hz,
            hzMin: session.hzMin,
            hzMax: session.hzMax,
            measuredHz: null,
            rateOk: null,
            kind: session.kind,
            name: session.name,
          };
          observeRate(session.times, session.hz);
          initialPayloads[id] = data;
          started.push(session);
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
      updateBatchHintText();
      openLiveDashboard(batchSessions, initialPayloads);
      for (const s of batchSessions) {
        updateCardRateUi(s.id, { measured: null, ok: null });
        armBatchSessionTimer(s);
      }
    } catch (err) {
      batchStreams = {};
      batchMeta = {};
      batchCanSave = false;
      batchRunning = false;
      batchSessions = [];
      setBatchUi();
      syncCardSelectionUi();
      if (batchHint) batchHint.textContent = String(err.message || err);
    }
  }

  function saveBatchFile() {
    const count = batchSampleTotal();
    if (!count) {
      const msg = t("batch.nothing");
      if (batchHint) batchHint.textContent = msg;
      if (liveHint) liveHint.textContent = msg;
      return;
    }
    if (liveSeqEl?.value && batchSeqEl && !String(batchSeqEl.value || "").trim()) {
      batchSeqEl.value = liveSeqEl.value;
    }
    if (batchSeqEl?.value && liveSeqEl && !String(liveSeqEl.value || "").trim()) {
      liveSeqEl.value = batchSeqEl.value;
    }
    const seq = String(liveSeqEl?.value || batchSeqEl?.value || "").trim();
    if (!seq) {
      const msg = t("batch.needSeq");
      if (batchHint) batchHint.textContent = msg;
      if (liveHint) liveHint.textContent = msg;
      (liveSeqEl || batchSeqEl)?.focus();
      return;
    }
    if (batchSeqEl) batchSeqEl.value = seq;
    if (liveSeqEl) liveSeqEl.value = seq;
    const dir = String(exportDirEl?.value || "").trim();
    if (!dir) {
      const msg = t("batch.needDir");
      if (batchHint) batchHint.textContent = msg;
      if (liveHint) liveHint.textContent = msg;
      exportDirEl?.focus();
      return;
    }
    const safeSeq = seq.replace(/[^\w.\-]+/g, "_");
    const file = `sensors-view-${safeSeq}.json`;
    const deviceIds = Object.keys(batchStreams);
    const payload = {
      seq,
      saved_at: new Date().toISOString(),
      started_at: batchStartedAt ? new Date(batchStartedAt).toISOString() : null,
      dry_run: !!batchDryRunEl?.checked,
      device_ids: deviceIds,
      devices: deviceIds.map((id) => {
        const meta = batchMeta[id] || {};
        const prefs = getRatePrefs(id, meta.kind || deviceCache[id]?.kind || "");
        return {
          id,
          kind: meta.kind || deviceCache[id]?.kind || batchStreams[id]?.[0]?.kind || null,
          name: meta.name || deviceCache[id]?.name || batchStreams[id]?.[0]?.name || id,
          hz: meta.hz ?? prefs.hz,
          hz_min: meta.hzMin ?? prefs.hzMin,
          hz_max: meta.hzMax ?? prefs.hzMax,
          measured_hz: meta.measuredHz ?? null,
          rate_ok: meta.rateOk ?? null,
        };
      }),
      count,
      streams: JSON.parse(JSON.stringify(batchStreams)),
    };
    const starting = t("batch.saving");
    if (batchHint) batchHint.textContent = starting;
    if (liveHint) liveHint.textContent = starting;
    btnBatchSave.disabled = true;
    if (btnLiveSave) btnLiveSave.disabled = true;
    saveJsonToServer(file, payload, dir)
      .then((res) => {
        const msg = t("batch.saved", { count, path: res.path || file });
        if (batchHint) batchHint.textContent = msg;
        if (liveHint) liveHint.textContent = msg;
      })
      .catch((err) => {
        const msg = t("batch.saveFailed", { err: err.message || err });
        if (batchHint) batchHint.textContent = msg;
        if (liveHint) liveHint.textContent = msg;
      })
      .finally(() => {
        setBatchUi();
      });
  }

  async function pollExportJob(jobId) {
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      const res = await fetch(`/api/export/jobs/${encodeURIComponent(jobId)}`);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(body) || `HTTP ${res.status}`);
      if (body.status === "done") return body;
      if (body.status === "error") throw new Error(body.error || "export failed");
      await new Promise((r) => setTimeout(r, 120));
    }
    throw new Error("export timeout");
  }

  async function saveJsonToServer(filename, data, dir) {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename,
        data,
        dir: dir || undefined,
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiDetail(body) || `HTTP ${res.status}`);
    if (body.job_id) return pollExportJob(body.job_id);
    return body;
  }

  async function pollPostprocessJob(jobId) {
    const deadline = Date.now() + 600000;
    while (Date.now() < deadline) {
      const res = await fetch(`/api/postprocess/jobs/${encodeURIComponent(jobId)}`);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(body) || `HTTP ${res.status}`);
      if (body.status === "done") return body;
      if (body.status === "error") throw new Error(body.error || "postprocess failed");
      await new Promise((r) => setTimeout(r, 200));
    }
    throw new Error("postprocess timeout");
  }

  function runBatchPostprocess() {
    if (liveSeqEl?.value && batchSeqEl && !String(batchSeqEl.value || "").trim()) {
      batchSeqEl.value = liveSeqEl.value;
    }
    if (batchSeqEl?.value && liveSeqEl && !String(liveSeqEl.value || "").trim()) {
      liveSeqEl.value = batchSeqEl.value;
    }
    const dir = String(exportDirEl?.value || "").trim();
    if (!dir) {
      const msg = t("batch.needDir");
      if (batchHint) batchHint.textContent = msg;
      if (liveHint) liveHint.textContent = msg;
      exportDirEl?.focus();
      return;
    }
    const seq = String(liveSeqEl?.value || batchSeqEl?.value || "").trim();
    const starting = t("batch.posting");
    if (batchHint) batchHint.textContent = starting;
    if (liveHint) liveHint.textContent = starting;
    if (btnBatchPost) btnBatchPost.disabled = true;
    if (btnLivePost) btnLivePost.disabled = true;
    fetch("/api/postprocess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dir,
        seq: seq || undefined,
        interval_ms: 200,
        write_video: false,
      }),
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiDetail(body) || `HTTP ${res.status}`);
        if (body.job_id) return pollPostprocessJob(body.job_id);
        return body;
      })
      .then((res) => {
        const results = res.results || [];
        const first = results[0] || {};
        const msg = t("batch.posted", {
          n: results.length || 1,
          frames: first.frames ?? "—",
          path: first.path || res.out_dir || res.path || dir,
        });
        if (batchHint) batchHint.textContent = msg;
        if (liveHint) liveHint.textContent = msg;
      })
      .catch((err) => {
        const msg = t("batch.postFailed", { err: err.message || err });
        if (batchHint) batchHint.textContent = msg;
        if (liveHint) liveHint.textContent = msg;
      })
      .finally(() => {
        setBatchUi();
      });
  }

  async function persistExportDir() {
    if (!exportDirEl) return;
    const dir = String(exportDirEl.value || "").trim();
    if (!dir) return;
    const res = await fetch("/api/export", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dir }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiDetail(body) || `HTTP ${res.status}`);
    if (body.dir) exportDirEl.value = body.dir;
  }

  function bindCardRateControls(card, d) {
    const prefs = getRatePrefs(d.id, d.kind);
    const hzEl = card.querySelector(".card-hz");
    const minEl = card.querySelector(".card-hz-min");
    const maxEl = card.querySelector(".card-hz-max");
    const syncInputs = (p) => {
      if (hzEl) {
        hzEl.min = String(p.hzMin);
        hzEl.max = String(p.hzMax);
        hzEl.value = String(p.hz);
      }
      if (minEl) minEl.value = String(p.hzMin);
      if (maxEl) maxEl.value = String(p.hzMax);
    };
    syncInputs(prefs);

    const apply = (patch) => {
      const next = setRatePrefs(d.id, d.kind, patch);
      syncInputs(next);
      const live = batchSessions.find((s) => s.id === d.id);
      if (live && patch.hz != null) {
        live.hz = next.hz;
        live.times = [];
        live.measuredHz = null;
        live.rateOk = null;
        armBatchSessionTimer(live);
        updateCardRateUi(d.id, { measured: null, ok: null });
      }
      if (currentDevice?.id === d.id) {
        applyModalRateBounds();
        if (sessionId) {
          armStreamTimer();
          updateStreamStatus();
        }
      }
    };

    hzEl?.addEventListener("change", () => {
      apply({ hz: clampDeviceHz(hzEl.value, getRatePrefs(d.id, d.kind)) });
    });
    minEl?.addEventListener("change", () => {
      const cur = getRatePrefs(d.id, d.kind);
      let hzMin = Number(minEl.value);
      if (!Number.isFinite(hzMin)) hzMin = cur.hzMin;
      apply({ hzMin, hz: clampDeviceHz(cur.hz, { ...cur, hzMin }) });
    });
    maxEl?.addEventListener("change", () => {
      const cur = getRatePrefs(d.id, d.kind);
      let hzMax = Number(maxEl.value);
      if (!Number.isFinite(hzMax)) hzMax = cur.hzMax;
      apply({ hzMax, hz: clampDeviceHz(cur.hz, { ...cur, hzMax }) });
    });
  }

  function renderCards(devices) {
    lastDevices = devices || [];
    for (const d of lastDevices) deviceCache[d.id] = d;
    const known = new Set(lastDevices.map((d) => d.id));
    for (const id of [...selectedIds]) {
      if (!known.has(id)) selectedIds.delete(id);
    }
    for (const id of [...selectionSeeded]) {
      if (!known.has(id)) selectionSeeded.delete(id);
    }
    for (const d of lastDevices) {
      if (selectionSeeded.has(d.id)) continue;
      selectionSeeded.add(d.id);
      if (!DEFAULT_UNCHECKED_KINDS.has(d.kind)) selectedIds.add(d.id);
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
        const prefs = getRatePrefs(d.id, d.kind);
        const live = batchSessions.find((s) => s.id === d.id);
        const status = live && live.rateOk === false ? "rate" : live && live.rateOk === true ? "ok" : d.status;
        const statusText = status === "rate" ? t("status.rate") : status;
        const measuredText =
          live && live.measuredHz != null
            ? t("card.measured", { hz: formatMeasured(live.measuredHz) })
            : t("card.measuredWarm");
        return `
          <article class="card clickable${selected ? " is-selected" : ""}" style="animation-delay:${Math.min(i * 0.03, 0.3)}s" data-id="${escapeHtml(d.id)}" data-status="${escapeHtml(status)}" tabindex="0" role="button">
            <div class="card-head">
              <div>
                <label class="card-select">
                  <input type="checkbox" class="card-check" data-id="${escapeHtml(d.id)}" ${selected ? "checked" : ""} ${batchRunning ? "disabled" : ""} />
                  <span class="card-select-label">${escapeHtml(t("card.select"))}</span>
                </label>
                <p class="card-id">${escapeHtml(d.kind)} · ${escapeHtml(d.id)}</p>
                <h2 class="card-title">${escapeHtml(d.name || d.id)}</h2>
              </div>
              <span class="status-pill" data-status="${escapeHtml(status)}">${escapeHtml(statusText)}</span>
            </div>
            <p class="msg">${escapeHtml(d.message || "")}</p>
            <div class="card-rate" data-id="${escapeHtml(d.id)}">
              <label class="field">
                <span class="field-label">${escapeHtml(t("card.hz"))}</span>
                <input type="number" class="card-hz" step="${prefs.hzMax >= 100 ? "1" : "0.1"}" value="${prefs.hz}" ${batchRunning && !live ? "disabled" : ""} />
              </label>
              <label class="field">
                <span class="field-label">${escapeHtml(t("card.hzMin"))}</span>
                <input type="number" class="card-hz-min" step="0.1" value="${prefs.hzMin}" ${batchRunning ? "disabled" : ""} />
              </label>
              <label class="field">
                <span class="field-label">${escapeHtml(t("card.hzMax"))}</span>
                <input type="number" class="card-hz-max" step="0.1" value="${prefs.hzMax}" ${batchRunning ? "disabled" : ""} />
              </label>
              <div class="card-rate-meta">
                <p class="card-rate-measured">${escapeHtml(measuredText)}</p>
              </div>
            </div>
            <ul class="checks">${checks}</ul>
            <div class="card-actions">
              <span class="card-cta">${cta}</span>
            </div>
          </article>
        `;
      })
      .join("");

    grid.querySelectorAll(".card").forEach((card) => {
      const id = card.dataset.id;
      const d = deviceCache[id];
      if (d) bindCardRateControls(card, d);
      const open = () => openModal(card.dataset.id);
      card.addEventListener("click", (e) => {
        if (e.target.closest(".card-select") || e.target.closest(".card-rate")) return;
        open();
      });
      card.addEventListener("keydown", (e) => {
        if (e.target.closest(".card-select") || e.target.closest(".card-rate")) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      });
    });
    grid.querySelectorAll(".card-select").forEach((label) => {
      label.addEventListener("click", (e) => e.stopPropagation());
    });
    grid.querySelectorAll(".card-rate").forEach((el) => {
      el.addEventListener("click", (e) => e.stopPropagation());
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
    setBatchUi();
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
    const dir = String(exportDirEl?.value || "").trim();
    if (!dir) {
      formHint.textContent = t("batch.needDir");
      exportDirEl?.focus();
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
      hz_min: currentDevice ? getRatePrefs(currentDevice.id, currentDevice.kind).hzMin : null,
      hz_max: currentDevice ? getRatePrefs(currentDevice.id, currentDevice.kind).hzMax : null,
      measured_hz: streamMeasuredHz,
      rate_ok: streamRateOk,
      dry_run: !!dryRunEl.checked,
      started_at: streamStartedAt ? new Date(streamStartedAt).toISOString() : null,
      count: streamRecords.length,
      samples: streamRecords,
    };
    formHint.textContent = t("form.opening");
    btnSaveStream.disabled = true;
    saveJsonToServer(file, payload, dir)
      .then((res) => {
        formHint.textContent = t("stream.saved", {
          count: streamRecords.length,
          path: res.path || file,
        });
      })
      .catch((err) => {
        formHint.textContent = t("stream.saveFailed", { err: err.message || err });
      })
      .finally(() => {
        updateSaveStreamBtn();
      });
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
      measured: formatMeasured(streamMeasuredHz),
      rateStatus: rateStatusLabel(streamRateOk),
      tick: tick ?? "—",
      elapsed,
      auto,
    });
    if (currentDevice?.id) {
      updateCardRateUi(currentDevice.id, {
        measured: streamMeasuredHz,
        ok: streamRateOk,
      });
    }
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
    const prevId = currentDevice?.id;
    sessionId = null;
    streamRecording = false;
    streamRateTimes = [];
    streamMeasuredHz = null;
    streamRateOk = null;
    updateSaveStreamBtn();
    setStreamingUi(false);
    if (prevId && !batchRunning) {
      const probe = deviceCache[prevId]?.status;
      updateCardRateUi(prevId, { measured: null, ok: null, probeStatus: probe });
    }
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
      const evaled = observeRate(streamRateTimes, clampHz(rateEl.value));
      streamMeasuredHz = evaled.measured;
      streamRateOk = evaled.ok;
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
      streamRateTimes = [];
      streamMeasuredHz = null;
      streamRateOk = null;
      observeRate(streamRateTimes, clampHz(rateEl.value));
      updateSaveStreamBtn();
      setStreamingUi(true);
      showViz(data);
      updateStreamStatus(data.tick);
      formHint.textContent = t("form.streaming");
      armStreamTimer();
      if (currentDevice?.id) {
        const prefs = getRatePrefs(currentDevice.id, currentDevice.kind);
        setRatePrefs(currentDevice.id, currentDevice.kind, { hz: clampHz(rateEl.value) });
        void prefs;
      }
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
      applyModalRateBounds();

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
      currentDevice = { id, fields: [], config: deviceCache[id]?.config || {}, control: { writable: false }, kind: deviceCache[id]?.kind || "device" };
      modalTitle.textContent = id;
      modalKind.textContent = deviceCache[id]?.kind || "device";
      formFields.innerHTML = "";
      controlPanel.hidden = true;
      applyModalRateBounds();
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
    if (exportDirEl && meta.export_dir) {
      exportDirEl.value = meta.export_dir;
      exportDirEl.placeholder = meta.export_dir_default || meta.export_dir;
    }
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
    if (currentDevice?.id) {
      setRatePrefs(currentDevice.id, currentDevice.kind, { hz: clampHz(rateEl.value) });
      const cardHz = grid?.querySelector(`${cardSelector(currentDevice.id)} .card-hz`);
      if (cardHz) cardHz.value = rateEl.value;
    }
    if (sessionId) {
      streamRateTimes = [];
      streamMeasuredHz = null;
      streamRateOk = null;
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
  btnBatchPost?.addEventListener("click", runBatchPostprocess);
  btnLiveStop?.addEventListener("click", () => {
    stopBatch().catch((err) => {
      if (liveHint) liveHint.textContent = String(err.message || err);
    });
  });
  btnLiveSave?.addEventListener("click", saveBatchFile);
  btnLivePost?.addEventListener("click", runBatchPostprocess);
  btnLiveClose?.addEventListener("click", () => {
    dismissLiveDashboard().catch((err) => {
      if (liveHint) liveHint.textContent = String(err.message || err);
    });
  });
  exportDirEl?.addEventListener("change", () => {
    persistExportDir().catch((err) => {
      if (batchHint) batchHint.textContent = t("batch.saveFailed", { err: err.message || err });
    });
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
    } else if (liveModal && !liveModal.hidden) {
      e.preventDefault();
      dismissLiveDashboard().catch(() => {});
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
      updateBatchHintText();
    } else if (batchCanSave && batchHint && batchSampleTotal()) {
      batchHint.textContent = t("batch.stopped", { count: batchSampleTotal() });
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
