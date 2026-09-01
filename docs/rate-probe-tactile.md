# 触觉（tactile / Paxini）测速算法

覆盖：**读速 only**。无驱动原生 `probe_max_read_hz`，走通用紧循环。

## 入口

| 操作 | API | 脚本 |
|---|---|---|
| 读速 | `POST /api/probe/{id}/read-rate` | `scripts/probe_read_rate.py` |

实现：`app/read_rate_probe.py` 的 `probe_read_hz`；驱动为 `sensors/drivers/extensions/paxini.py`（`PaxiniTactileSensor`）。

UI：「测量最大读取频率」按钮（`kind=tactile`）。

默认时长：**10 s**。

---

## 算法（`tight_read_loop`）

1. 按当前配置打开触觉驱动（DLL / 通道 / group 等）。
2. 在 `duration_s` 内尽可能快地循环 `sensor.read()`：
   - 成功则记录 `perf_counter` 时间戳；
   - 异常计入 `errors`；错误 ≥ 8 且成功样本 &lt; 3 提前失败。
3. 计量：

```text
measured_hz = (N − 1) / (t_last − t_first)   # N ≥ 3
read_cap_hz = floor(measured × 0.95 × 10) / 10
```

4. 附带间隔分位数：`dt_ms_p50` / `dt_ms_p95` / `dt_ms_mean`。

无额外 config 改造（不像 ft 会压 `timeout_ms`）。

---

## 测的是什么

一次完整触觉 `read()`（rest_force + 触点场等）的进程内吞吐上限。  
dry-run 下为合成数据紧循环，仍返回真实墙钟频率，便于无硬件自检。

结果设为前端读频上限。无写速测（触觉驱动不提供位置写入寻峰）。
