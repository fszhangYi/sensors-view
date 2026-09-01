# RealSense（realsense）测速算法

覆盖：**读速 only**。通用紧循环测 `wait_for_frames` 吞吐，并用配置 fps 封顶，避免报告超过相机协商帧率。

## 入口

| 操作 | API | 脚本 |
|---|---|---|
| 读速 | `POST /api/probe/{id}/read-rate` | `scripts/probe_read_rate.py` |

实现：`app/read_rate_probe.py` 的 `probe_read_hz` + `_hardware_fps_cap`；驱动为 `sensors/drivers/camera/realsense.py`。

UI：「测量最大读取频率」按钮（`kind=realsense`）。

默认时长：**3 s**（取帧较重，缩短探测时间）。

---

## 算法（`tight_read_loop` + 硬件 fps 封顶）

1. 打开 RealSense pipeline（按配置分辨率 / fps / depth；可能自动回退可用流）。
2. 在约 3 s 内尽可能快地循环 `sensor.read()`（内部 `wait_for_frames`）。
3. 成功帧记时间戳；错误过多且样本不足则失败。
4. 基础计量：

```text
measured_hz = (N − 1) / (t_last − t_first)   # N ≥ 3
read_cap_hz = floor(measured × 0.95 × 10) / 10
```

5. **硬件封顶**：若 config 含 `fps` / `framerate` / `frame_rate`：

```text
read_cap_hz = min(read_cap_hz, floor(hardware_fps × 10) / 10)
```

结果里附带 `hardware_fps_cap`。

---

## 测的是什么

当前流配置下，主机侧连续取色/深帧的可达频率（受 USB、分辨率、对齐、CPU 影响）。  
cap 不会高于配置请求的相机 fps，避免把瞬时抖动报成「超 fps」。

无写速测。结果设为读频上限。
