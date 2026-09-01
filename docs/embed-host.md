# 宿主嵌入（iframe）约定

sensors-view 在检测到自己处于 iframe 中时：

- 显示红点跳动的 `iframe` 标记
- **隐藏**：退出、用户、中英文切换、深浅色切换
- **语言 / 主题跟随宿主**（不写回 localStorage）

## 宿主需要暴露什么

不必改同源 Cookie / 不必提供 HTTP API。只需对 iframe 的 `contentWindow` 做 **`postMessage`**。

### 1. 监听子页就绪（推荐）

子页加载后会向 `parent` 发送：

```js
{
  source: "sensors-view",
  version: 1,
  type: "embed-ready"           // 以及随后的 "embed-request-prefs"
}
```

宿主示例：

```js
const iframe = document.getElementById("sensors-view");

window.addEventListener("message", (event) => {
  // 建议校验 event.origin === "https://your-sensors-view-host"
  const data = event.data;
  if (!data || data.source !== "sensors-view") return;
  if (data.type !== "embed-ready" && data.type !== "embed-request-prefs") return;

  iframe.contentWindow.postMessage(
    {
      source: "sensors-view-host",
      type: "embed-prefs",
      locale: "zh",          // "zh" | "en"
      theme: "dark",         // "dark" | "light" | "system"
    },
    event.origin,            // 或具体的 sensors-view origin
  );
});
```

### 2. 随时推送变更

宿主切换语言/主题时，再发同样消息即可：

```js
iframe.contentWindow.postMessage(
  {
    source: "sensors-view-host",
    type: "embed-prefs",
    locale: nextLocale,   // 可选；省略则不改语言
    theme: nextTheme,     // 可选；省略则不改主题
  },
  "https://sensors-view.example",
);
```

也可拆开发：

| `type` | 字段 |
|---|---|
| `embed-prefs` / `appearance` | `locale?`, `theme?` |
| `embed-locale` | `locale`: `"zh"` \| `"en"` |
| `embed-theme` | `theme`: `"dark"` \| `"light"` \| `"system"` |

**必填协议字段**：`source: "sensors-view-host"`（子页只认这个 source）。

### 3. URL 参数兜底（首屏 / 宿主暂无 JS）

```text
https://sensors-view.example/?locale=zh&theme=dark
```

- `locale` / `lang`: `zh` | `en`
- `theme`: `dark` | `light` | `system`

iframe 内会读一次并应用；仍建议再用 postMessage 做后续同步。

## 字段取值

| 键 | 取值 | 含义 |
|---|---|---|
| `locale` | `zh` / `en` | 界面语言 |
| `theme` | `dark` / `light` / `system` | 外观；`system` 跟随 iframe 所在环境的 `prefers-color-scheme` |

## 安全建议

- 宿主发送时用具体 `targetOrigin`，不要用 `*`（示例里子页向父页请求时用了 `*`，因无法预知父 origin）。
- 宿主收子页消息时校验 `event.origin`。
- 跨站 iframe 下会话 Cookie 为 `SameSite=Lax`，通常**不会**带上；嵌入场景默认不当作独立登录入口（退出/用户已隐藏）。
