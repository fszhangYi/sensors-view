---
name: sensors-view-iframe-embed
description: >-
  Wire a host SPA to embed sensors-view (or compatible guest) via iframe:
  iframe status badge, host-driven locale/theme sync, Settings URL persistence,
  server-side reachability ping, and grey-out of nav when unreachable; guest
  hides logout/users/locale/theme chrome. Use when adding sensors-view iframe,
  embed-host, postMessage embed-prefs, SensorsEmbedProvider, sensors-view/ping,
  or porting host/guest embed contracts.
---

# sensors-view iframe embed

Canonical pair:

| Side | Repo path |
| --- | --- |
| **Guest** | `/root/autodl-tmp/sensors-view` (`app/static/embed.js`, `docs/embed-host.md`) |
| **Host** | `/root/autodl-tmp/embody_model_eval` (`SensorsPage`, `SensorsEmbedContext`, `/api/sensors-view/ping`) |

Protocol doc (guest): `sensors-view/docs/embed-host.md`. File map: [reference.md](reference.md).

## Non-negotiables (user requirements)

1. **显示当前是 iframe 状态** — guest shows a visible iframe badge when framed.
2. **国际化和主题随宿主** — URL params on first paint + `postMessage` thereafter; guest must **not** persist host prefs to its own localStorage.
3. **宿主有设置则增加 URL 配置** — Settings tab; auto-save; ping on boot and after URL change.
4. **不可达则跳转不可用、按钮置灰** — nav / home module / shortcuts skip or disable Sensors entry when `reachability === 'fail'`.
5. **iframe 下隐藏敏感功能** — guest hides logout, users, locale switcher, theme switcher (and related modals).

## Architecture

```text
Host SPA
  Settings → localStorage URL
  SensorsEmbedProvider → ping /api/sensors-view/ping
  Nav / Home → disabled when fail
  SensorsPage → <iframe src="?locale&theme"> + postMessage embed-prefs

Guest (sensors-view)
  embed.js → isFramed?
    badge on
    hide chrome (logout / users / locale / theme)
    applyPrefs(URL) persist:false
    post embed-ready / embed-request-prefs
    listen host embed-prefs
```

## Port checklist

Copy and tick:

```text
Guest
- [ ] 1. Detect framed: window.self !== window.top (catch → true)
- [ ] 2. iframe badge (#iframe-embed-badge) visible only when framed
- [ ] 3. Hide: logout, users, locale, theme (+ users modal)
- [ ] 4. URL ?locale|lang=zh|en & ?theme=dark|light|system (persist:false)
- [ ] 5. postMessage source sensors-view: embed-ready + embed-request-prefs
- [ ] 6. Accept host source sensors-view-host: embed-prefs / embed-locale / embed-theme
- [ ] 7. Host-driven setLocale/setTheme with persist:false

Host
- [ ] 8. Prefs module: normalize URL, localStorage key, origin helper, ping client
- [ ] 9. Provider: load URL, setUrl→persist, ping on mount + URL change (after auth)
- [ ] 10. Settings Sensors tab: draft input, debounce/blur auto-save, status + re-ping
- [ ] 11. Server GET /api/…/ping?url= → probe /api/health then base URL
- [ ] 12. Page: iframe with locale/theme query; remount only on base URL change
- [ ] 13. Message bridge: validate event.origin; reply embed-prefs; push on locale/theme change
- [ ] 14. Gate: PageNav + Home card + keyboard shortcuts grey/skip when fail
- [ ] 15. Unreachable Sensors route: status copy (optional; nav already blocked)
```

## Guest: iframe badge + chrome hide

Badge markup (status region, red pulse dot + `iframe` label). CSS: `.iframe-embed-badge`, `.iframe-embed-dot` pulse. i18n title key e.g. `embed.iframe`.

Chrome IDs hidden when framed (sensors-view):

| id | Why |
| --- | --- |
| `btn-logout` | session / identity |
| `btn-users` | user admin |
| `locale-seg` | guest must not own locale |
| `theme-seg` | guest must not own theme |

Also force-hide `#users-modal`. Re-apply after auth UI refreshes (auth may unhide logout).

## Guest ↔ host messages

| Direction | `source` | `type` | Payload |
| --- | --- | --- | --- |
| Guest → host | `sensors-view` | `embed-ready` / `embed-request-prefs` | `version: 1` |
| Host → guest | `sensors-view-host` | `embed-prefs` | `locale?`, `theme?` |
| Host → guest | same | `embed-locale` / `embed-theme` | single field |

Host rules:

- `targetOrigin` = guest origin (never `*` for host→guest).
- Validate `event.origin` on inbound guest messages.
- First paint: `?locale=&theme=` on iframe `src`.
- Later host preference changes: postMessage only — **do not** reload iframe.

## Host: Settings URL + ping + gate

**Persistence:** `localStorage` key (embody: `embody.sensorsEmbedUrl`); normalize to `https://…/` with trailing slash on path.

**Ping:** browser must not rely on cross-origin fetch (CORS). Host backend probes:

1. `{base}/api/health`
2. else `{base}/`  
Treat HTTP `200/3xx/401/403` as reachable (SPA/login still means host is up).

**Provider timing:** ping when auth allows (`!authRequired || user`); re-ping whenever URL changes.

**Gate:** `reachability === 'fail'` →

- nav item: `<span aria-disabled>` + `.disabled` (not `<Link>`)
- home module card: same
- Alt+digit / adjacent page shortcuts: skip blocked id

While `checking` / `unknown`, keep entry enabled (avoid flash-disable on boot).

## Host iframe page sketch

```ts
// src once: baseUrl + locale + theme query
// on baseUrl change: remount iframe (key={baseUrl})
// on locale/theme change: postMessage embed-prefs only
window.addEventListener('message', (e) => {
  if (e.origin !== guestOrigin) return
  if (e.data?.source !== 'sensors-view') return
  if (e.data.type !== 'embed-ready' && e.data.type !== 'embed-request-prefs') return
  e.source?.postMessage({ source: 'sensors-view-host', type: 'embed-prefs', locale, theme }, e.origin)
})
```

## Security notes

- Cross-site iframe: guest session cookies are usually **not** sent (`SameSite=Lax`) — embed is not a login surface; hiding logout/users is required.
- Do not put API keys in iframe URL query.
- Ping endpoint should be auth-gated like other host APIs.

## Related skills

- Guest appearance/i18n internals: `embody-appearance-theme`, `embody-i18n` (patterns), guest still owns apply APIs.
- Host Settings chrome: follow existing SettingsModal tab patterns in embody.
- Protocol detail + message examples: `sensors-view/docs/embed-host.md` and [reference.md](reference.md).
