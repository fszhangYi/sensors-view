# sensors-view

可视化前端，用于观察 **hik-sensors**（`../sensors`）的探针状态与采样结果。采集栈仍在独立仓库中维护；本仓库只做展示与轻量 API。

## 布局

```
sensors-view/
  sensors -> ../sensors     # 软链接到 hik-sensors
  configs/view.yaml         # 指向 sensors/configs/default.yaml
  app/                      # FastAPI + 状态页
```

## 启动

```bash
cd /root/autodl-tmp/sensors-view
pip install -e .
# 或仅装依赖后：
python -m app.main --host 0.0.0.0 --port 6008
```

浏览器打开 `http://<host>:6008`（未登录会跳到 `/login`）。

### 登录鉴权

默认开启 Cookie 会话（`sensors_view_session`）。首次启动会在 `config/users.json` 写入管理员；控制台会打印初始密码（或已用环境变量指定）。

| 环境变量 | 作用 |
|------|------|
| `SENSORS_VIEW_AUTH_DISABLED=1` | 关闭鉴权 |
| `SENSORS_VIEW_AUTH_USER` | 用户名（默认 `sensors`） |
| `SENSORS_VIEW_AUTH_PASSWORD` | 密码（首次/更新写入 users.json） |

`config/users.json` 与 `config/.auth.json` 已 gitignore。

登录后顶部可打开「用户」：任意登录用户可改自己的密码；**admin** 可增删改账号、重置密码、启停与改角色。

默认 `dry_run: true`（见 `configs/view.yaml`）。真机探测时改为 `false`。

桌面打包会通过 `requirements-hardware.txt` 打入 `pyrealsense2` / `dynamixel-sdk` / `pyserial` / `pyzmq`；
开发态也可：`pip install -r requirements-hardware.txt`（或 `pip install 'hik-sensors[realsense,dynamixel,serial,zmq]'`）。

## API

| 路径 | 说明 |
|------|------|
| `GET /login` | Embody 风格登录页 |
| `GET /api/auth/me` | 会话状态（公开） |
| `POST /api/auth/login` | 登录，Set-Cookie |
| `POST /api/auth/logout` | 登出 |
| `POST /api/auth/password` | 修改当前用户密码 |
| `GET/POST /api/users` | 列出 / 创建用户（admin） |
| `PUT/DELETE /api/users/{username}` | 更新 / 删除用户（admin） |
| `GET /api/meta` | site / dry_run / device ids（需登录） |
| `GET /api/probe` | `SensorManager.probe_all()`（需登录） |
| `GET /api/read/{id}` | open → read → close |
| `POST /api/reload` | 重载 YAML 配置 |

## 与 embody_model_eval

本项目独立，不依赖 embody_model_eval Web 状态页。

## License

Apache-2.0
