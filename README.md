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
python -m app.main --host 0.0.0.0 --port 8765
```

浏览器打开 `http://<host>:8765`。

默认 `dry_run: true`（见 `configs/view.yaml`）。真机探测时改为 `false`，并确保已安装 sensors 可选依赖（serial / zmq / realsense / dynamixel）。

## API

| 路径 | 说明 |
|------|------|
| `GET /api/meta` | site / dry_run / device ids |
| `GET /api/probe` | `SensorManager.probe_all()` |
| `GET /api/read/{id}` | open → read → close |
| `POST /api/reload` | 重载 YAML 配置 |

## 与 embody_model_eval

本项目独立，不依赖 embody_model_eval Web 状态页。

## License

Apache-2.0
