# sensors-view iframe embed — reference

## Guest files (sensors-view)

| Path | Role |
| --- | --- |
| `app/static/embed.js` | Frame detect, badge, chrome hide, URL prefs, postMessage bridge |
| `app/static/app.js` | Re-hide logout/users after `/api/auth/me` (framed overrides) |
| `app/templates/index.html` | `#iframe-embed-badge`; early FOUC locale/theme from query when framed; loads `embed.js` |
| `app/static/style.css` | `.iframe-embed-badge` / pulse animations |
| `app/static/i18n.js` | `embed.iframe` title strings |
| `docs/embed-host.md` | Host-facing protocol (messages + URL params) |

### Guest bootstrap order

1. Inline head script (optional): if framed, apply `?theme` / `?locale` to `<html>` before paint.
2. `embed.js` on DOMContentLoaded: badge + chrome hide + URL prefs (`persist:false`) + `embed-ready`.
3. `app.js` auth refresh must not re-show logout/users when framed.

### Guest public API

```js
window.SensorsEmbed = {
  isFramed,
  applyPrefs,      // ({locale?, theme?}, {persist})
  setChromeHidden,
  syncIframeBadge,
  postToHost,
  SOURCE: 'sensors-view',
  HOST_SOURCE: 'sensors-view-host',
  VERSION: 1,
}
```

Host prefs application must call existing `SensorsI18n.setLocale` / `SensorsAppearance.setTheme` with **`persist: false`**.

## Host files (embody_model_eval)

| Path | Role |
| --- | --- |
| `frontend/src/prefs/sensorsEmbed.ts` | Default URL, normalize, localStorage, `pingSensorsEmbedUrl` |
| `frontend/src/prefs/SensorsEmbedContext.tsx` | Provider: url / setUrl / reachability / ping |
| `frontend/src/pages/SensorsPage.tsx` | iframe + message bridge + unreachable panel |
| `frontend/src/components/SettingsModal.tsx` | `PanelSensors` tab (auto-save + re-ping) |
| `frontend/src/components/PageNav.tsx` | Disable / skip sensors when fail |
| `frontend/src/pages/HomePage.tsx` | Disable sensors module card when fail |
| `frontend/src/App.tsx` | Wrap routes with `SensorsEmbedProvider` (inside `AuthProvider`) |
| `frontend/src/i18n/messages.ts` | `settings.sensors.*`, `settings.tabs.sensors`, esc hint |
| `frontend/src/styles/sensors.css` | Full-bleed iframe + unreachable state |
| `frontend/src/styles/settings.css` | `.settings-sensors-*`, stacked URL row |
| `frontend/src/styles/globals.css` | `.page-nav-item.disabled` |
| `frontend/src/styles/home.css` | `.home-module-card.disabled` |
| `scripts/agent_server.py` | `ping_sensors_view`, `GET /api/sensors-view/ping` |

### Host storage / API

| Item | Value |
| --- | --- |
| localStorage | `embody.sensorsEmbedUrl` |
| Default URL | seetacloud sensors-view base (trailing `/`) |
| Ping | `GET /api/sensors-view/ping?url=` → `{ ok, status, url, probed, message }` |

### Reachability enum

`unknown` | `checking` | `ok` | `fail`

Gate **only** on `fail`. Keep nav usable during `checking` / `unknown`.

### Ping probe order (server)

```text
1. {origin}{path}/api/health   (path normalized with trailing / stripped for join)
2. {base}/                     (SPA / login HTML)
Accept ok OR status in {200,301,302,303,307,308,401,403}
```

## Message examples

Guest → host:

```json
{ "source": "sensors-view", "version": 1, "type": "embed-ready" }
{ "source": "sensors-view", "version": 1, "type": "embed-request-prefs" }
```

Host → guest:

```json
{
  "source": "sensors-view-host",
  "type": "embed-prefs",
  "locale": "zh",
  "theme": "dark"
}
```

URL first paint:

```text
https://guest.example:8443/?locale=zh&theme=dark
```

## Porting to another host

1. Keep guest protocol (`source` strings, types, field names) unchanged.
2. Rename host storage key / ping path to your app prefix.
3. Wire Provider under your auth provider so ping uses session cookies.
4. Reuse Settings row stacking for long URLs (label above control).
5. Do not proxy the iframe document through the host unless you must defeat `X-Frame-Options` (sensors-view currently allows framing).

## Porting to another guest

If embedding a different app behind the same host:

1. Implement the same `source` / message types **or** dual-map in the host page.
2. Always: iframe badge, hide identity/locale/theme chrome, prefs `persist:false`.
3. Document the guest contract next to the app (mirror `docs/embed-host.md`).
