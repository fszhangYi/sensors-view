/**
 * sensors-view i18n (embody-i18n port, vanilla).
 * Storage: sensors-view.locale  (zh | en), default zh
 */
(() => {
  const LOCALE_KEY = "sensors-view.locale";
  const DEFAULT_LOCALE = "zh";

  const catalogs = {
    zh: {
      "meta.title": "sensors-view",
      "home.brand": "sensors-view",
      "home.title": "现场传感器状态",
      "home.lede": "点击卡片配置连接，按设定频率连续采样并在弹窗内可视化。",
      "theme.aria": "外观主题",
      "theme.system": "系统",
      "theme.dark": "深色",
      "theme.light": "浅色",
      "locale.aria": "界面语言",
      "locale.zh": "中文",
      "locale.en": "English",
      "btn.probe": "探测状态",
      "btn.reload": "重载配置",
      "btn.close": "关闭",
      "btn.start": "开始连续采样",
      "btn.stop": "停止",
      "btn.once": "单次采样",
      "btn.saveStream": "保存采样文件",
      "btn.batchStart": "开始连续采样",
      "btn.batchStop": "停止",
      "btn.batchSave": "保存数据文件",
      "btn.batchPost": "批后处理",
      "field.batchSeq": "序号",
      "field.exportDir": "保存文件夹",
      "field.postInDir": "输入路径",
      "field.postOutDir": "输出路径",
      "card.select": "选择",
      "batch.lede": "各卡片单独设定目标频率与上下限；采集中按实测 Hz 更新 status",
      "batch.none": "请先勾选至少一个传感器",
      "batch.checking": "逐个检查在线状态…",
      "batch.offline": "{id} 未在线（{status}）",
      "batch.starting": "统一开始采集…",
      "batch.running": "批量采集中 · {n} 路 · 合计 {count} 样 · 达标 {ok}/{n}",
      "batch.stopped": "已停止 · 共 {count} 样，填写序号后保存",
      "batch.needSeq": "请填写序号",
      "batch.needSeqInt": "序号必须是正整数",
      "batch.needDir": "请填写保存文件夹",
      "batch.nothing": "没有可保存的批量采样数据",
      "batch.saving": "正在后台线程保存…",
      "batch.saved": "已保存 {count} 样 → {path}",
      "batch.saveFailed": "保存失败: {err}",
      "batch.posting": "正在后台线程做批后处理…",
      "batch.posted": "批后处理完成 · {n} 个文件 · {frames} 帧 → {path}",
      "batch.postFailed": "批后处理失败: {err}",
      "batch.startFailed": "启动失败 {id}: {err}",
      "post.lede": "将保存目录中的 sensors-view JSON 转为 hik episode；需指定输入与输出路径",
      "post.needIn": "请填写输入路径",
      "post.needOut": "请填写输出路径",
      "live.kicker": "live · batch",
      "live.title": "连续采样",
      "live.lede": "2×2：三路相机 + 其他传感器数值",
      "live.tileMeta": "目标 {hz} · 实测 {measured} · tick {tick}",
      "live.waiting": "等待首帧…",
      "live.statusWarm": "测评中",
      "live.camEmpty": "未选择相机",
      "live.othersTitle": "其他传感器",
      "live.noOthers": "未勾选非相机传感器",
      "card.hz": "目标 Hz",
      "card.hzMin": "下限",
      "card.hzMax": "上限",
      "card.measured": "实测 {hz} Hz",
      "card.measuredWarm": "实测 —",
      "status.rate": "rate",
      "btn.capture": "从最新采样捕获显示基准",
      "btn.randomCmd": "随机下发一次",
      "field.sampleRate": "目标频率 Hz",
      "field.rateBounds": "允许范围 {min}–{max} Hz",
      "field.dryRun": "dry-run（不连真机）",
      "control.kicker": "command · linear map",
      "control.hint.joints": "显示 = rs·生数据 + ro；真实下发 = ws·显示 + wo（scale/offset 为浮点，scale 可为负）",
      "control.hint.gripper": "夹爪同样：显示=rs·raw+ro；真实下发=ws·显示+wo（浮点，scale 可为负）",
      "control.autoCmd": "随连续采样自动随机下发",
      "control.baselineNone": "尚未捕获",
      "control.baselineNeedSample": "请先采样一次再捕获显示基准",
      "control.baselineCaptured": "已捕获显示基准 {vals}",
      "control.baselineReady": "已有采样，可点击捕获显示基准",
      "control.baselineLabel": "显示基准 {val}",
      "control.rs": "rs 读scale",
      "control.ro": "ro 读offset",
      "control.ws": "ws 写scale",
      "control.wo": "wo 写offset",
      "control.delta": "±delta",
      "viz.kicker": "visualization",
      "viz.rawJson": "原始 JSON",
      "viz.noteDry": "dry-run 采样",
      "viz.noteLive": "live 采样",
      "viz.jointsDisplay": "关节角·显示",
      "viz.gripperDisplay": "夹爪开合·显示",
      "foot.sdk": "linked SDK: ./sensors → hik-sensors",
      "foot.stream": "连续采样 · 可调频率",
      "card.cta.writable": "点击采集 / 下发控制 →",
      "card.cta.sample": "点击配置并连续采样 →",
      "form.noFields": "该设备无可编辑连接字段，仍可直接采样。",
      "form.loading": "加载配置…",
      "form.hint.writable": "先连续/单次采集，再捕获基准并随机下发",
      "form.hint.sample": "设定频率后开始连续采样",
      "form.opening": "打开会话…",
      "form.streaming": "连续采样中 — 可改频率 / 捕获基准后下发",
      "form.onceBusy": "单次采样…",
      "form.onceDone": "单次采样完成",
      "form.stopped": "已停止",
      "form.stoppedSample": "已停止采样",
      "form.stopFailed": "停止失败: {err}",
      "form.rateChanged": "频率已改为 {hz} Hz",
      "stream.running": "连续中 · 目标 {hz} · 实测 {measured} · {rateStatus} · tick {tick} · {elapsed}s{auto}",
      "stream.rateOk": "达标",
      "stream.rateBad": "频率不符",
      "stream.rateWarm": "测评中",
      "stream.once": "单次",
      "stream.auto": " · auto-cmd",
      "stream.saved": "已保存 {count} 条 → {path}",
      "stream.nothing": "暂无连续采样可保存",
      "stream.saveFailed": "保存失败: {err}",
      "cmd.sending": "下发中…",
      "cmd.dryRun": "dry-run 显示={display} → 真实={real}",
      "cmd.sent": "已下发 显示={display} → 真实={real}",
      "cmd.needBaseline": "请先捕获显示基准",
      "err.probe": "probe failed: {err}",
      "err.reload": "reload failed: {err}",
      "field.num_joints": "关节数",
      "field.joint_ids": "关节 ID (逗号分隔)",
      "field.robot_ip": "机器人 IP",
      "field.endpoint": "端点",
      "field.port": "串口 / 端口",
      "field.port_substr": "端口子串",
      "field.serial": "序列号",
      "field.role": "角色",
      "field.width": "宽",
      "field.height": "高",
      "field.fps": "帧率",
      "field.baudrate": "波特率",
      "field.slave_id": "从站 ID",
      "field.zmq_port": "ZMQ 端口",
      "field.backend": "后端",
      "login.loading": "正在加载…",
      "login.checkingSession": "正在校验会话…",
      "login.title": "登录到 sensors-view",
      "login.sub": "使用本机账号继续",
      "login.username": "用户名",
      "login.password": "密码",
      "login.show": "显示",
      "login.hide": "隐藏",
      "login.submit": "登录",
      "login.submitting": "登录中…",
      "login.fail": "登录失败",
      "login.networkError": "网络错误",
      "login.aside": "默认用户 {user}（可用 SENSORS_VIEW_AUTH_* 覆盖）",
      "login.asideMuted": "会话 Cookie · 7 天 · HttpOnly",
      "login.footerTag": "现场传感器控制台",
      "btn.logout": "退出",
      "btn.users": "用户",
      "users.kicker": "accounts",
      "users.title": "用户与密码",
      "users.passwordTitle": "修改我的密码",
      "users.currentPassword": "当前密码",
      "users.newPassword": "新密码",
      "users.savePassword": "保存密码",
      "users.passwordOk": "密码已更新",
      "users.listTitle": "账号列表",
      "users.inviteTitle": "添加用户",
      "users.newUsername": "用户名",
      "users.newRole": "角色",
      "users.roleUser": "user",
      "users.roleAdmin": "admin",
      "users.create": "创建",
      "users.colUser": "用户",
      "users.colRole": "角色",
      "users.colEnabled": "启用",
      "users.colActions": "操作",
      "users.resetPassword": "重置密码",
      "users.delete": "删除",
      "users.created": "已创建 {user}",
      "users.deleted": "已删除 {user}",
      "users.updated": "已更新 {user}",
      "users.resetPrompt": "输入 {user} 的新密码",
    },
    en: {
      "meta.title": "sensors-view",
      "home.brand": "sensors-view",
      "home.title": "Live sensor status",
      "home.lede": "Open a card to configure the link, stream samples at a set Hz, and visualize in the modal.",
      "theme.aria": "Appearance",
      "theme.system": "System",
      "theme.dark": "Dark",
      "theme.light": "Light",
      "locale.aria": "Language",
      "locale.zh": "中文",
      "locale.en": "English",
      "btn.probe": "Probe",
      "btn.reload": "Reload config",
      "btn.close": "Close",
      "btn.start": "Start stream",
      "btn.stop": "Stop",
      "btn.once": "Sample once",
      "btn.saveStream": "Save samples",
      "btn.batchStart": "Start stream",
      "btn.batchStop": "Stop",
      "btn.batchSave": "Save data file",
      "btn.batchPost": "Postprocess",
      "field.batchSeq": "Seq no.",
      "field.exportDir": "Save folder",
      "field.postInDir": "Input path",
      "field.postOutDir": "Output path",
      "card.select": "Select",
      "batch.lede": "Set target Hz and limits per card; status reflects measured rate while streaming",
      "batch.none": "Select at least one sensor",
      "batch.checking": "Checking online status…",
      "batch.offline": "{id} offline ({status})",
      "batch.starting": "Starting all sessions…",
      "batch.running": "Batch · {n} · {count} samples · ok {ok}/{n}",
      "batch.stopped": "Stopped · {count} samples — enter seq and save",
      "batch.needSeq": "Enter a sequence number",
      "batch.needSeqInt": "Sequence must be a positive integer",
      "batch.needDir": "Enter a save folder",
      "batch.nothing": "No batch samples to save",
      "batch.saving": "Saving on background thread…",
      "batch.saved": "Saved {count} samples → {path}",
      "batch.saveFailed": "Save failed: {err}",
      "batch.posting": "Postprocessing on background thread…",
      "batch.posted": "Postprocess done · {n} file(s) · {frames} frames → {path}",
      "batch.postFailed": "Postprocess failed: {err}",
      "batch.startFailed": "Start failed {id}: {err}",
      "post.lede": "Convert sensors-view JSON under the input folder into hik episodes; set input and output paths",
      "post.needIn": "Enter an input path",
      "post.needOut": "Enter an output path",
      "live.kicker": "live · batch",
      "live.title": "Live sampling",
      "live.lede": "2×2: three cameras + numeric others",
      "live.tileMeta": "target {hz} · measured {measured} · tick {tick}",
      "live.waiting": "Waiting for first frame…",
      "live.statusWarm": "warming",
      "live.camEmpty": "No camera selected",
      "live.othersTitle": "Other sensors",
      "live.noOthers": "No non-camera sensors selected",
      "card.hz": "Target Hz",
      "card.hzMin": "Min",
      "card.hzMax": "Max",
      "card.measured": "Measured {hz} Hz",
      "card.measuredWarm": "Measured —",
      "status.rate": "rate",
      "btn.capture": "Capture display baseline",
      "btn.randomCmd": "Random command once",
      "field.sampleRate": "Target rate Hz",
      "field.rateBounds": "Allowed {min}–{max} Hz",
      "field.dryRun": "dry-run (no hardware)",
      "control.kicker": "command · linear map",
      "control.hint.joints": "display = rs·raw + ro; real cmd = ws·display + wo (float scale/offset; scale may be negative)",
      "control.hint.gripper": "Gripper: display = rs·raw + ro; real = ws·display + wo (float; scale may be negative)",
      "control.autoCmd": "Auto random command while streaming",
      "control.baselineNone": "No baseline yet",
      "control.baselineNeedSample": "Sample once before capturing a display baseline",
      "control.baselineCaptured": "Baseline captured {vals}",
      "control.baselineReady": "Sample ready — capture a display baseline",
      "control.baselineLabel": "baseline {val}",
      "control.rs": "rs read scale",
      "control.ro": "ro read offset",
      "control.ws": "ws write scale",
      "control.wo": "wo write offset",
      "control.delta": "±delta",
      "viz.kicker": "visualization",
      "viz.rawJson": "Raw JSON",
      "viz.noteDry": "dry-run sample",
      "viz.noteLive": "live sample",
      "viz.jointsDisplay": "Joints · display",
      "viz.gripperDisplay": "Gripper · display",
      "foot.sdk": "linked SDK: ./sensors → hik-sensors",
      "foot.stream": "Continuous sampling · adjustable Hz",
      "card.cta.writable": "Sample / command →",
      "card.cta.sample": "Configure & stream →",
      "form.noFields": "No editable link fields — you can still sample.",
      "form.loading": "Loading config…",
      "form.hint.writable": "Stream or sample once, capture baseline, then random-command",
      "form.hint.sample": "Set Hz, then start continuous sampling",
      "form.opening": "Opening session…",
      "form.streaming": "Streaming — change Hz / capture baseline to command",
      "form.onceBusy": "Sampling once…",
      "form.onceDone": "Single sample done",
      "form.stopped": "Stopped",
      "form.stoppedSample": "Sampling stopped",
      "form.stopFailed": "Stop failed: {err}",
      "form.rateChanged": "Rate set to {hz} Hz",
      "stream.running": "Streaming · target {hz} · measured {measured} · {rateStatus} · tick {tick} · {elapsed}s{auto}",
      "stream.rateOk": "ok",
      "stream.rateBad": "rate mismatch",
      "stream.rateWarm": "warming",
      "stream.once": "Once",
      "stream.auto": " · auto-cmd",
      "stream.saved": "Saved {count} → {path}",
      "stream.nothing": "No stream samples to save",
      "stream.saveFailed": "Save failed: {err}",
      "cmd.sending": "Sending…",
      "cmd.dryRun": "dry-run display={display} → real={real}",
      "cmd.sent": "Sent display={display} → real={real}",
      "cmd.needBaseline": "Capture a display baseline first",
      "err.probe": "probe failed: {err}",
      "err.reload": "reload failed: {err}",
      "field.num_joints": "Joint count",
      "field.joint_ids": "Joint IDs (comma-separated)",
      "field.robot_ip": "Robot IP",
      "field.endpoint": "Endpoint",
      "field.port": "Port / serial",
      "field.port_substr": "Port substring",
      "field.serial": "Serial",
      "field.role": "Role",
      "field.width": "Width",
      "field.height": "Height",
      "field.fps": "FPS",
      "field.baudrate": "Baud rate",
      "field.slave_id": "Slave ID",
      "field.zmq_port": "ZMQ port",
      "field.backend": "Backend",
      "login.loading": "Loading…",
      "login.checkingSession": "Checking session…",
      "login.title": "Sign in to sensors-view",
      "login.sub": "Continue with your local account",
      "login.username": "Username",
      "login.password": "Password",
      "login.show": "Show",
      "login.hide": "Hide",
      "login.submit": "Sign in",
      "login.submitting": "Signing in…",
      "login.fail": "Sign-in failed",
      "login.networkError": "Network error",
      "login.aside": "Default user {user} (override with SENSORS_VIEW_AUTH_*)",
      "login.asideMuted": "Session cookie · 7 days · HttpOnly",
      "login.footerTag": "Live sensor console",
      "btn.logout": "Log out",
      "btn.users": "Users",
      "users.kicker": "accounts",
      "users.title": "Users & password",
      "users.passwordTitle": "Change my password",
      "users.currentPassword": "Current password",
      "users.newPassword": "New password",
      "users.savePassword": "Save password",
      "users.passwordOk": "Password updated",
      "users.listTitle": "Accounts",
      "users.inviteTitle": "Add user",
      "users.newUsername": "Username",
      "users.newRole": "Role",
      "users.roleUser": "user",
      "users.roleAdmin": "admin",
      "users.create": "Create",
      "users.colUser": "User",
      "users.colRole": "Role",
      "users.colEnabled": "Enabled",
      "users.colActions": "Actions",
      "users.resetPassword": "Reset password",
      "users.delete": "Delete",
      "users.created": "Created {user}",
      "users.deleted": "Deleted {user}",
      "users.updated": "Updated {user}",
      "users.resetPrompt": "New password for {user}",
    },
  };

  const listeners = new Set();
  let locale = DEFAULT_LOCALE;

  function isLocale(v) {
    return v === "zh" || v === "en";
  }

  function readStoredLocale() {
    try {
      const v = localStorage.getItem(LOCALE_KEY);
      if (isLocale(v)) return v;
    } catch {
      /* ignore */
    }
    return DEFAULT_LOCALE;
  }

  function formatMessage(raw, vars) {
    if (!vars) return raw;
    return String(raw).replace(/\{(\w+)\}/g, (_, k) =>
      vars[k] == null ? `{${k}}` : String(vars[k])
    );
  }

  function lookup(loc, path) {
    return catalogs[loc]?.[path];
  }

  function t(path, vars) {
    const raw = lookup(locale, path) ?? lookup("zh", path) ?? path;
    return formatMessage(raw, vars);
  }

  function applyDomI18n(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (!key) return;
      const attr = el.getAttribute("data-i18n-attr");
      const text = t(key);
      if (attr) el.setAttribute(attr, text);
      else el.textContent = text;
    });
    const titleKey = document.body?.getAttribute("data-i18n-title");
    if (titleKey) document.title = t(titleKey);
  }

  function syncLocaleSeg() {
    const seg = document.getElementById("locale-seg");
    if (!seg) return;
    seg.querySelectorAll("[data-locale]").forEach((btn) => {
      const on = btn.getAttribute("data-locale") === locale;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function setLocale(next) {
    if (!isLocale(next) || next === locale) {
      syncLocaleSeg();
      return;
    }
    locale = next;
    try {
      localStorage.setItem(LOCALE_KEY, locale);
    } catch {
      /* ignore */
    }
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
    applyDomI18n(document);
    syncLocaleSeg();
    listeners.forEach((fn) => {
      try {
        fn(locale);
      } catch {
        /* ignore */
      }
    });
  }

  function onLocaleChange(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  function fieldLabel(key, fallback) {
    const path = `field.${key}`;
    if (lookup(locale, path) || lookup("zh", path)) return t(path);
    return fallback || key;
  }

  function init() {
    locale = readStoredLocale();
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
    applyDomI18n(document);
    syncLocaleSeg();
    const seg = document.getElementById("locale-seg");
    if (seg) {
      seg.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-locale]");
        if (!btn) return;
        setLocale(btn.getAttribute("data-locale"));
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Early lang for FOUC companion (theme script may run first)
  try {
    const early = readStoredLocale();
    document.documentElement.lang = early === "zh" ? "zh-CN" : "en";
  } catch {
    /* ignore */
  }

  window.SensorsI18n = {
    t,
    setLocale,
    getLocale: () => locale,
    onLocaleChange,
    applyDomI18n,
    fieldLabel,
    catalogs,
  };
})();
