# 夹爪（gripper / DH AG95）测速算法

覆盖：**读速** + **写速（同步写→读）**。是目前唯一同时测读写的传感器。

## 入口

| 操作 | API | 脚本 |
|---|---|---|
| 校准 | `POST /api/probe/{id}/gripper/calibrate` | `scripts/probe_gripper_rate.py`（mode=calibrate） |
| 读速 | `POST /api/probe/{id}/gripper/read` | `scripts/probe_gripper_read_rate.py` |
| 写速 | `POST /api/probe/{id}/gripper/write` | `scripts/probe_gripper_write_rate.py` |
| 初始化（兼容） | `POST /api/probe/{id}/gripper/init` | 先校准脚本，再读速脚本（两次独立启动） |

实现：`app/gripper_rate_probe.py`；读循环复用 `app/read_rate_probe.probe_read_hz`。

UI：控制面板「初始化 / 校准」→ 校准后自动跑读速；「测量最大写入频率」单独触发写测。

---

## 1. 校准（不测频）

1. 独占打开夹爪驱动。
2. 下发 `calibrate`：完全闭合再张开，记录 `position_raw_min` / `position_raw_max`。
3. 回传校准结果；读速由另一次脚本完成。

---

## 2. 最大读取频率

### 流程

1. 实机（非 dry-run）可先 `initialize`，确保 Modbus 可用。
2. 默认约 **10 s** 内尽可能快地循环 `sensor.read()`（无 sleep）。
3. 成功时间戳算 `measured_hz`；`read_cap_hz = floor(measured × 0.95 × 10) / 10`。
4. 前端把 `read_cap_hz` 设为读取上限与工作读频。

### 计量

```text
measured_hz = (N − 1) / (t_last − t_first)   # N ≥ 3
method = "tight_read_loop"
```

错误 ≥ 8 且成功样本 &lt; 3 时提前失败。

### 测的是什么

Modbus 位置反馈的往返吞吐（读路径），不是 UI 设定的读频。

---

## 3. 最大同步写频

旧算法把「调度目标写频」当成结果，会虚高到 UI 上限（如 40）。现算法改为实测 **写→读成对节拍**。

### 流程

1. 打开夹爪并 `initialize`。
2. **只读基线**（默认约 1.5 s）：与读测相同的紧循环，得到 `baseline_read_hz`。
3. **同步节拍**（默认约 10 s，夹在 3–`max_duration_s`）：
   - 每轮：随机 `position_norm` ∈ `[value_min, value_max]`（默认 0–0.637），`wait_ms=0` 写入；
   - 写成功则立刻 `read()`，记录成功时间戳；
   - 写失败累计过多且几乎无成功则中止。
4. 用成对成功时间戳算 `write_measured_hz`。
5. 结果：

```text
cap = floor(write_measured_hz × 0.95 × 10) / 10
cap = min(cap, floor(baseline_read_hz × 0.95 × 10) / 10)  # 不超过只读基线
cap = clamp(cap, hz_min, hz_max)
max_sync_write_hz = cap
```

若实测已顶到 `hz_max`，`finish_reason = "ceiling"`；否则多为 `"measured"`。

### 测的是什么

同一总线上「随机写位置 + 读反馈」的 1:1 同步吞吐。**不会**把 UI 写频上限当作测得值；也不会声称同步写快于只读基线。

### 与连续采样

连续采样只读不写。需要定位用「固定下发」；写测结果仅展示最大同步写频。
