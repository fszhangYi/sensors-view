# 六维力（ft）测速算法

覆盖：**读速 only**。优先走驱动原生 `probe_max_read_hz`（串口连续流帧计数），而不是泛化的 `sensor.read()` 节拍。

## 入口

| 操作 | API | 脚本 |
|---|---|---|
| 读速 | `POST /api/probe/{id}/read-rate` | `scripts/probe_read_rate.py` |

实现：`app/read_rate_probe.py` → 发现驱动有 `probe_max_read_hz` 则调用  
`sensors/drivers/extensions/force_torque.py`。

UI：「测量最大读取频率」按钮（`kind=ft`）。

默认时长：**5 s**。测前会把 `timeout_ms` 压到约 20–80 ms，避免缺帧时空等拖慢探测。

---

## 算法（实机：`ft_stream_frames`）

力传感器在 START 后持续往串口吐 28 字节 wrench 帧。测速数的是**流里到达的有效帧**，不是 UI HTTP tick。

1. 打开串口并进入采样流。
2. **预热**约 0.25 s：`_drain_serial` + 弹出至少一帧，确认流已起来。
3. 在 `duration_s` 内循环：
   - 排空 RX 缓冲；
   - 用 `_pop_frame_from_buffer(latest=False)` **逐帧**取出所有完整帧（不是只取最新一帧丢掉中间帧）；
   - 每解析成功一帧记一个时间戳；
   - 本轮无帧则 `sleep(0.0005)` 再试。
4. `measured_hz = (N − 1) / (t_last − t_first)`（N ≥ 3）。
5. `read_cap_hz = floor(measured × 0.95 × 10) / 10`。
6. 附带间隔统计：`dt_ms_p50` / `dt_ms_p95` / `dt_ms_mean`。

帧过少时失败提示检查 port / baud / START 流。

### 为何不用普通 `read()` 紧循环

普通 `read()` 常取「最新一帧」并可能阻塞等待，容易低估或混入 UI 超时语义。流式帧计数更接近总线真实吞吐。

---

## dry-run（`ft_dry_run_loop`）

无串口时紧循环调用 `read()`（合成数据），仍按时间戳算 `measured_hz` / `read_cap_hz`，便于无硬件自检。

---

## 测的是什么

连续串口 wrench 帧到达率（设备推流能力 + 主机收包解析）。结果写入前端读频上限。
