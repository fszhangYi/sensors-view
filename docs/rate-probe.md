# 传感器测速（Rate Probe）总览

本文档说明 sensors-view 已实现的离线测速能力。测速在**独立工作线程 + 子进程脚本**中完成，不经 HTTP 逐拍；前端只显示「测速中」，结束后渲染结果。

## 覆盖范围

| 传感器 kind | 读速 | 写速 | 入口 | 算法文档 |
|---|---|---|---|---|
| `gripper`（DH AG95） | ✅ | ✅（同步写→读） | 初始化/校准后自动读测；写测按钮 | [rate-probe-gripper.md](./rate-probe-gripper.md) |
| `ft`（六维力） | ✅（驱动原生帧计数） | — | 「测量最大读取频率」 | [rate-probe-ft.md](./rate-probe-ft.md) |
| `gello` | ✅（驱动原生 SyncRead） | — | 「测量最大读取频率」 | [rate-probe-gello.md](./rate-probe-gello.md) |
| `tactile`（Paxini） | ✅（通用紧循环） | — | 「测量最大读取频率」 | [rate-probe-tactile.md](./rate-probe-tactile.md) |
| `realsense` | ✅（通用紧循环 + fps 封顶） | — | 「测量最大读取频率」 | [rate-probe-realsense.md](./rate-probe-realsense.md) |
| `arm` | ❌ 暂未启用 | — | — | — |

未覆盖：`pipeline` / `bus`（非高频采样流）。

相关：iframe 宿主嵌入约定见 [embed-host.md](./embed-host.md)。

## 公共约定

### 调度方式

1. API 收到请求后关闭该设备现有会话（独占串口/设备）。
2. Worker 线程拉起专用脚本（`scripts/probe_*.py`），写入 job JSON，等待子进程退出。
3. 脚本打开驱动、测速、写结果 JSON 退出；API 只回传结果。

相关代码：`app/main.py`（`_run_probe_script`）、`app/read_rate_probe.py`、`app/gripper_rate_probe.py`。

### 频率计量

对成功时间戳列表 `times`（至少 3 个点）：

```text
measured_hz = (N - 1) / (t_last - t_first)
```

读取上限（留约 5% 余量，一位小数）：

```text
read_cap_hz = floor(measured_hz × 0.95 × 10) / 10
```

下限不低于 `0.2` Hz。前端可能再按 UI 的 `hzMin`/`hzMax` 放宽边界，但**不会**把实测结果抬高到虚假下限。

### 默认测读时长

| kind | 默认 `duration_s` |
|---|---|
| `realsense` | 3 |
| `ft` / `gello` | 5 |
| 其余（含 `gripper` / `tactile`） | 10 |

### 与连续采样的关系

连续采样仍走 HTTP tick，只读可视化/落盘；测速结果只用来设定读频上限（夹爪另可展示最大同步写频）。采样路径本身不参与寻峰。

### 过程数据回传

测速结果 JSON 中带 `process` 字段，供前端弹框折叠展示：

```text
process.steps[]          # { t_s, name, detail } 阶段时间线
process.dt_ms_series[]   # 间隔采样（最多约 200 点，避免过大）
process.summary          # 关键指标摘要
```

通用紧循环与夹爪写测会写入完整 steps + 间隔序列；驱动原生测读（FT/Gello）若未自带 process，由 `attach_process_from_probe` 用汇总字段合成。
