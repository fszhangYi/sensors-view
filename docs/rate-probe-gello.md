# Gello（gello）测速算法

覆盖：**读速 only**。走驱动原生 `probe_max_read_hz`：Dynamixel `GroupSyncRead` 紧循环。

## 入口

| 操作 | API | 脚本 |
|---|---|---|
| 读速 | `POST /api/probe/{id}/read-rate` | `scripts/probe_read_rate.py` |

实现：`app/read_rate_probe.py` → `sensors/drivers/gello/leader.py` 的 `probe_max_read_hz`。

UI：「测量最大读取频率」按钮（`kind=gello`）。

默认时长：**5 s**。

---

## 算法（`gello_sync_read_loop`）

1. 打开 Gello（Dynamixel 端口 + GroupSyncRead）。
2. 在 `duration_s` 内尽可能快地循环 `self.read()`（无 pacing sleep）。
3. 每次成功读关节记时间戳；异常累计，错误 ≥ 8 且样本 &lt; 3 则中止。
4. 计量：

```text
measured_hz = (N − 1) / (t_last − t_first)   # N ≥ 3；否则失败
read_cap_hz = floor(measured × 0.95 × 10) / 10
```

5. 附带 `dt_ms_p50` / `dt_ms_p95` / `dt_ms_mean`。

dry-run 或未建立 SyncRead 时仍跑循环，结果里 `dry_run=true`（合成/空总线路径）。

---

## 测的是什么

整组舵机 **GroupSyncRead 往返** 的真实总线吞吐，不是前端设定的采样 Hz。  
前端曾有过把偏低结果抬到 100 Hz 下限的假象；现已改为不抬高实测 cap。

结果设为读频上限 / 工作读频。
