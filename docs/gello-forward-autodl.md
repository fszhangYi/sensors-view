# 本地串口传感器数据转发到 AutoDL：Gello 客户端 / 服务端实践

本文基于仓库中的 `client.py`（本地 Windows 侧）与 `server.py`（AutoDL 容器侧），说明如何把 Gello（Dynamixel）串口数据经公网转发到云端，并讨论如何扩展到多传感器。

---

## 1. 环境介绍

### 1.1 拓扑

```text
┌─────────────────────────────┐         HTTPS (AutoDL 自定义服务)        ┌──────────────────────────────┐
│  本地 Windows PC            │  ─────────────────────────────────────► │  AutoDL 容器                 │
│  Gello → COM3 (FTDI)        │   uu…seetacloud.com:8443                │  server.py 监听 0.0.0.0:6008 │
│  client.py 主动 SyncRead    │   /api/device_data                      │  打印 / 缓存最近一帧          │
└─────────────────────────────┘                                         └──────────────────────────────┘
```

| 角色 | 运行位置 | 关键文件 | 职责 |
|---|---|---|---|
| 客户端 | 接真机串口的 Windows | `client.py` | Dynamixel 轮询 → JSON POST |
| 服务端 | AutoDL GPU/CPU 实例 | `server.py` | FastAPI 收包 → 打印/缓存 |

### 1.2 依赖

**客户端（Windows）**

```bash
pip install dynamixel_sdk requests urllib3
```

**服务端（AutoDL / Linux）**

```bash
pip install fastapi uvicorn pydantic
```

### 1.3 AutoDL 网络要点

- 容器内服务绑定 `0.0.0.0:6008`；**外网不能直接打 TCP 6008**。
- 控制台开启「自定义服务」端口 **6008** 后，平台提供 HTTPS 代理，形如：

  ```text
  https://uu<账号片段>-<实例>.<region>.seetacloud.com:8443
  ```

- 注意子域名前缀：本实例中 **6008 对应双 `u`（`uu658526-…`）**；单 `u` 往往映射到别的端口（如 6006），不要混用。
- 环境变量可核对：`AutoDLService6008URL`。
- 代理证书校验常需关闭（客户端 `VERIFY_TLS = False`）。

### 1.4 设备侧约定（Gello）

| 项 | 值 |
|---|---|
| 串口 | Windows `COM3`（按设备管理器修改） |
| 波特率 | `57600` |
| 协议 | Dynamixel Protocol **2.0** |
| 寄存器 | Present Position，地址 `132`，长度 `4` |
| 舵机 ID | 默认 `[1, 2, 3, 4, 5, 6, 7]` |

Gello **不会**像文本传感器那样主动推送换行数据；必须用 `GroupSyncRead` 主动请求，否则 `readline()` 只会读到空串。

---

## 2. 目的介绍

本地工位有真实 Gello 串口，训练 / 可视化 / 联调却在 AutoDL 云端。目标是：

1. **在本地完成硬件访问**（只有本机有 COM3 / FTDI）。
2. **把采样结果经网络送到 AutoDL**，云端进程只需 HTTP，无需穿透串口。
3. **协议简单、可观测**：JSON POST + 健康检查 + 最近一帧查询，方便后续接到 `sensors-view`、录制脚本或策略服务。

一句话：**客户端端口数据 → 网络转发 → AutoDL 服务器**。

典型用途：

- 云端实时查看关节角 / ticks；
- 为远程算法提供「最新观测」；
- 验证 AutoDL 自定义服务链路是否畅通，再扩展到夹爪、力觉、相机等。

---

## 3. 构建过程

### 3.1 服务端（AutoDL）

1. 控制台为实例打开自定义端口 **6008**，记下公网 URL（或读 `AutoDLService6008URL`）。
2. 在项目目录启动：

   ```bash
   cd /root/autodl-tmp/sensors-view
   python server.py
   ```

3. 容器内自检：

   ```bash
   curl -s http://127.0.0.1:6008/api/health
   # {"ok":true,"received":0,"uptime_s":…,"has_latest":false}
   ```

4. 从公网自检（注意 HTTPS 与双 `u` 域名）：

   ```bash
   curl -sk https://uu658526-m86b-7fdc269f.weste.seetacloud.com:8443/api/health
   ```

### 3.2 客户端（Windows）

1. 确认 Gello 在设备管理器中对应 `COM3`（或改 `SERIAL_PORT`）。
2. 修改 `REMOTE_API` 为当前实例的公网地址 + `/api/device_data`。
3. 启动：

   ```bash
   python client.py
   ```

4. 预期：

   - 本地打印：`rad=[…] ticks=[…]`
   - AutoDL 终端打印：`#N ids=[…] rad=[…] ticks=[…]`

### 3.3 联调清单

| 现象 | 排查 |
|---|---|
| 客户端 `发送失败` / 超时 | 6008 是否开放；URL 是否双 `u`；服务是否在跑 |
| 服务端无输出 | 客户端是否打到别的端口服务；路径是否为 `/api/device_data` |
| 串口打不开 | COM 号错误、被其它进程占用、驱动未装 |
| SyncRead 失败 | 波特率 / 舵机 ID / 线材供电 |
| 公网卡顿 | 降低 `POLL_HZ`（建议 10–20） |

### 3.4 数据契约

客户端每次 POST：

```json
{
  "data": {
    "joint_ids": [1, 2, 3, 4, 5, 6, 7],
    "joints_raw_ticks": [3117, 2798, 2874, 3216, 4263, 2021, 1191],
    "joints_rad": [4.7814, 4.2921, 4.4087, 4.9333, 6.5394, 3.1002, 1.8270],
    "port": "COM3",
    "ts": 1725160000.123
  },
  "timestamp": 1725160000.123
}
```

服务端返回：`{"ok": true, "n": <累计帧序号>}`。

---

## 4. 代码详解

### 4.1 服务端 `server.py` 原文

```python
"""Gello 转发服务端 —— 配对 tmp.py（COM3 Dynamixel 客户端）。

接收 POST /api/device_data，打印关节角，并缓存最近一帧。
"""

from __future__ import annotations

import logging
import time
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

# ===== 配置区 =====
HOST = "0.0.0.0"
# HOST = "172.20.10.3"
# PORT = 8000
PORT = 6008

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(title="gello-forward-server")
_latest: dict[str, Any] | None = None
_count = 0
_t0 = time.time()


class DeviceDataBody(BaseModel):
    """兼容新旧客户端：data 可为字符串，或 joints_* 结构体。"""

    data: Any
    timestamp: float | None = None


def _format_sample(data: Any) -> str:
    if isinstance(data, dict) and "joints_rad" in data:
        rad = data.get("joints_rad") or []
        ticks = data.get("joints_raw_ticks")
        ids = data.get("joint_ids")
        rad_str = ", ".join(f"{float(v):+.4f}" for v in rad)
        return f"ids={ids} rad=[{rad_str}] ticks={ticks}"
    if isinstance(data, str):
        return data if data.strip() else "<empty string>"
    return repr(data)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "received": _count,
        "uptime_s": round(time.time() - _t0, 1),
        "has_latest": _latest is not None,
    }


@app.get("/api/latest")
def latest() -> dict[str, Any]:
    if _latest is None:
        return {"ok": False, "message": "no data yet"}
    return {"ok": True, **_latest}


@app.post("/api/device_data")
def device_data(body: DeviceDataBody) -> dict[str, Any]:
    global _latest, _count
    _count += 1
    ts = body.timestamp if body.timestamp is not None else time.time()
    _latest = {"data": body.data, "timestamp": ts, "n": _count, "recv_ts": time.time()}

    line = _format_sample(body.data)
    print(f"[{time.strftime('%H:%M:%S')}] #{_count} {line}", flush=True)
    return {"ok": True, "n": _count}


def main() -> None:
    logging.info("Gello forward server listening on http://%s:%s", HOST, PORT)
    logging.info("POST /api/device_data  GET /api/latest  GET /api/health")
    # access_log=False：少打「客户端临时端口」行，避免误以为占了很多端口
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
```

**要点说明**

- `HOST = "0.0.0.0"` + `PORT = 6008`：容器内监听，与 AutoDL 自定义服务映射一致。
- `uvicorn(..., access_log=False)`：关掉 access log，避免把客户端临时源端口（如 `127.0.0.1:52268`）误当成「占了很多端口」——那些只是 ephemeral port，**监听端口始终只有 6008**。
- 三个接口：

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/api/health` | 存活、已收帧数、是否有最新缓存 |
| `GET` | `/api/latest` | 取最近一帧（给下游轮询） |
| `POST` | `/api/device_data` | 接收客户端采样，写入 `_latest` 并打印 |

- `DeviceDataBody.data` 为 `Any`：既兼容结构化 Gello 样本，也兼容早期字符串 payload。
- `_format_sample`：识别 `joints_rad` 后格式化打印；空字符串会标成 `<empty string>`，便于排查。

### 4.2 客户端 `client.py` 原文

```python
"""Forward Gello (Dynamixel) joint data from COM3 to a remote API.

Gello is NOT a newline text stream. Servos speak Dynamixel Protocol 2.0 and only
reply when polled (GroupSyncRead Present Position). Using serial.readline() always
returns empty — that was the bug.
"""

from __future__ import annotations

import logging
import math
import struct
import time
import urllib3
from typing import Any

import requests

# ===== 配置区 =====
SERIAL_PORT = "COM3"  # Windows: COM3；本脚本在容器外运行
BAUDRATE = 57600
JOINT_IDS = [1, 2, 3, 4, 5, 6, 7]
# AutoDL 自定义服务 6008 公网地址（HTTPS:8443 代理，非容器内 localhost）
REMOTE_API = "https://uu658526-m86b-7fdc269f.weste.seetacloud.com:8443/api/device_data"
VERIFY_TLS = False  # AutoDL 代理证书常需关闭校验；正式环境可改 True
RETRY_INTERVAL = 5
POLL_HZ = 15  # 公网建议 10–20；过高易超时/堆积

# Dynamixel Protocol 2.0 — Present Position
ADDR_PRESENT_POSITION = 132
LEN_PRESENT_POSITION = 4
PROTOCOL_VERSION = 2.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
if not VERIFY_TLS:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 复用 TCP 连接（HTTP keep-alive），避免每次 POST 都换临时源端口
_http = requests.Session()
_http.headers.update({"Connection": "keep-alive"})


def ticks_to_rad(ticks: list[int]) -> list[float]:
    return [t / 2048.0 * math.pi for t in ticks]


def send_data(payload: dict[str, Any]) -> None:
    try:
        resp = _http.post(REMOTE_API, json=payload, timeout=5, verify=VERIFY_TLS)
        if resp.status_code != 200:
            logging.warning("服务器返回非200: %s body=%s", resp.status_code, resp.text[:200])
    except Exception as e:  # noqa: BLE001
        logging.error("发送失败: %s", e)


def open_gello(port: str, baudrate: int, joint_ids: list[int]):
    try:
        from dynamixel_sdk import GroupSyncRead, PacketHandler, PortHandler
        from dynamixel_sdk.robotis_def import COMM_SUCCESS
    except ImportError as e:
        raise RuntimeError(
            "需要 dynamixel_sdk：pip install dynamixel_sdk  （或 hik-sensors[dynamixel]）"
        ) from e

    port_handler = PortHandler(port)
    if not port_handler.openPort():
        raise RuntimeError(f"无法打开串口 {port}")
    if not port_handler.setBaudRate(baudrate):
        port_handler.closePort()
        raise RuntimeError(f"无法设置波特率 {baudrate}")

    packet_handler = PacketHandler(PROTOCOL_VERSION)
    group = GroupSyncRead(port_handler, packet_handler, ADDR_PRESENT_POSITION, LEN_PRESENT_POSITION)
    for dxl_id in joint_ids:
        if not group.addParam(dxl_id):
            port_handler.closePort()
            raise RuntimeError(f"GroupSyncRead 添加舵机 id={dxl_id} 失败")

    return port_handler, group, COMM_SUCCESS


def read_joints(group, joint_ids: list[int], comm_success: int) -> dict[str, Any]:
    result = group.txRxPacket()
    if result != comm_success:
        raise RuntimeError(f"GroupSyncRead 失败 code={result}")

    ticks: list[int] = []
    for dxl_id in joint_ids:
        if not group.isAvailable(dxl_id, ADDR_PRESENT_POSITION, LEN_PRESENT_POSITION):
            raise RuntimeError(f"舵机 id={dxl_id} 无 Present Position 数据")
        raw = group.getData(dxl_id, ADDR_PRESENT_POSITION, LEN_PRESENT_POSITION)
        # Dynamixel returns unsigned 32-bit; cast to signed int32 like the driver.
        ticks.append(int(struct.unpack("i", struct.pack("I", raw & 0xFFFFFFFF))[0]))

    rad = ticks_to_rad(ticks)
    return {
        "joint_ids": list(joint_ids),
        "joints_raw_ticks": ticks,
        "joints_rad": rad,
        "port": SERIAL_PORT,
        "ts": time.time(),
    }


def main() -> None:
    port_handler = None
    group = None
    comm_success = 0
    interval = 1.0 / max(1.0, float(POLL_HZ))

    try:
        logging.info("远端服务: %s (verify_tls=%s, poll_hz=%s)", REMOTE_API, VERIFY_TLS, POLL_HZ)
        while True:
            try:
                if port_handler is None:
                    port_handler, group, comm_success = open_gello(SERIAL_PORT, BAUDRATE, JOINT_IDS)
                    logging.info(
                        "已连接 Gello %s @ %s (Dynamixel SyncRead ids=%s)",
                        SERIAL_PORT,
                        BAUDRATE,
                        JOINT_IDS,
                    )

                sample = read_joints(group, JOINT_IDS, comm_success)
                rad_str = ", ".join(f"{v:+.4f}" for v in sample["joints_rad"])
                print(f"[{time.strftime('%H:%M:%S')}] rad=[{rad_str}]  ticks={sample['joints_raw_ticks']}")
                send_data({"data": sample, "timestamp": sample["ts"]})
                time.sleep(interval)

            except KeyboardInterrupt:
                logging.info("用户中断，退出")
                break
            except Exception as e:  # noqa: BLE001
                logging.error("读取/转发异常: %s", e)
                if port_handler is not None:
                    try:
                        port_handler.closePort()
                    except Exception:  # noqa: BLE001
                        pass
                port_handler = None
                group = None
                time.sleep(RETRY_INTERVAL)
    finally:
        if port_handler is not None:
            try:
                port_handler.closePort()
            except Exception:  # noqa: BLE001
                pass
        _http.close()


if __name__ == "__main__":
    main()
```

**要点说明**

| 变量 | 含义 |
|---|---|
| `SERIAL_PORT` | 本地串口（Windows `COM3`） |
| `REMOTE_API` | AutoDL 公网 HTTPS + `/api/device_data` |
| `VERIFY_TLS` | 公网代理常为 `False` |
| `POLL_HZ` | 公网建议 15 左右 |
| `JOINT_IDS` | SyncRead 舵机列表 |

- **为何不用 `readline()`**：Dynamixel 是请求/响应二进制协议；总线空闲时读行永远为空。必须 `PortHandler` → `PacketHandler(2.0)` → `GroupSyncRead(132, 4)` → 循环 `txRxPacket()` / `getData`。
- **单位换算**：`rad = ticks / 2048 * π`；ticks 按无符号 32 位再解释为有符号 int32。
- **HTTP**：`requests.Session()` + keep-alive，避免临时源端口狂涨；`verify=VERIFY_TLS` 适配 AutoDL 代理；异常时关串口再重连。
- **主循环**：`open_gello` → `read_joints` → `print` → `POST {data, timestamp}` → `sleep(1/POLL_HZ)`。

### 4.3 端到端时序

```text
client                     AutoDL Proxy                server(:6008)
  |                             |                           |
  |  GroupSyncRead (USB)        |                           |
  |  ← ticks / rad              |                           |
  |                             |                           |
  |  POST /api/device_data ────►|  转发到容器 6008 ─────────►|
  |  ← 200 {"ok", "n"}     ◄────|◄──────────────────────────|
  |                             |                           |  print + cache _latest
```

---

## 5. 多传感器拓展说明

当前实现是「单设备、单路径、单 JSON 结构」的最小闭环。扩展到多传感器时，建议在**契约层**先统一，再复制客户端进程或合并采集循环。

### 5.1 统一信封（推荐）

在现有 `{data, timestamp}` 外增加身份字段，服务端按 `sensor_id` / `kind` 分桶：

```json
{
  "sensor_id": "gello_left",
  "kind": "gello",
  "timestamp": 1725160000.123,
  "data": {
    "joint_ids": [1, 2, 3, 4, 5, 6, 7],
    "joints_raw_ticks": [],
    "joints_rad": [],
    "port": "COM3"
  }
}
```

其它 kind 的 `data` 示例：

| kind | 本地接口 | `data` 建议字段 |
|---|---|---|
| `gripper` | Modbus / 串口 | `position_norm`, `position_raw`, `force` |
| `ft` | 力觉串口流 | `wrench`（fx..tz）, `frame_id` |
| `tactile` | 厂商 SDK | `taxels` / 压缩数组 |
| `realsense` | USB 相机 | **不要**每帧 POST 原图；改传元数据 + 另开流媒体/对象存储 |
| `arm` | ZMQ / 厂家 API | `joints_rad`, `tcp_pose` |

### 5.2 服务端改造方向

1. **按传感器缓存**：`_latest: dict[str, dict]`，key = `sensor_id`。
2. **列表接口**：`GET /api/latest` → 全部；`GET /api/latest/{sensor_id}` → 单个。
3. **可选落盘**：按 `kind` 写 JSONL / 对接现有 `sensors-view` 导出目录。
4. **鉴权**：公网暴露时加 token / IP 白名单，避免裸 POST。

示例分桶：

```python
_latest_by_id: dict[str, dict] = {}

@app.post("/api/device_data")
def device_data(body: dict):
    sid = str(body.get("sensor_id") or body.get("kind") or "default")
    _latest_by_id[sid] = {**body, "recv_ts": time.time()}
    ...
```

### 5.3 客户端进程模型

| 方案 | 适用 | 说明 |
|---|---|---|
| 一传感器一进程 | 串口互斥、调试简单 | 复制 `client.py`，改 `SERIAL_PORT` / `kind` / `sensor_id` |
| 单进程多采集线程 | 同机多设备 | 每设备一线程 + 共享 `Session` 发送 |
| 批量打包 | 降公网 QPS | 本地 50Hz 采、100ms 聚合成 batch POST |

公网瓶颈往往在 **HTTPS RTT**，不在串口：多传感器时优先降发送频率或做 batch，而不是盲目提高 `POLL_HZ`。

### 5.4 与 `sensors-view` 的衔接

本仓库的 `sensors-view` 已通过驱动层统一 `open/read/probe`（含 Gello `GroupSyncRead`、夹爪读写测速、力觉帧计数等）。转发链路成熟后可以：

1. 在 AutoDL 上把 `/api/latest` 适配成 view 的 session tick 源；或  
2. 让 `server.py` 直接写入 view 可消费的环形缓冲 / Redis；或  
3. 仅把云端当「观测网关」，真机采样仍走本地，训练机订阅 HTTP。

测速与驱动细节见 `docs/rate-probe.md` 及 `docs/rate-probe-*.md`。

### 5.5 扩展时注意

- **带宽**：图像 / 高维触觉不要塞进同一 JSON POST；元数据走 HTTP，大块走专用通道。
- **时钟**：用客户端 `timestamp`，服务端另记 `recv_ts`，方便估延迟。
- **失败隔离**：某一 COM 掉线不应拖垮其它传感器线程。
- **安全**：AutoDL 公网 URL 相当于暴露端口，生产环境务必鉴权。

---

## 小结

| 步骤 | 动作 |
|---|---|
| 1 | AutoDL 开 6008，跑 `server.py` |
| 2 | Windows 配 `REMOTE_API`（双 `u` HTTPS），跑 `client.py` |
| 3 | 用 Dynamixel SyncRead 读 Gello，禁止当文本串口 `readline` |
| 4 | Session keep-alive + 合理 `POLL_HZ`，公网更稳 |
| 5 | 多传感器：统一信封 + 按 `sensor_id` 分桶 + 控制上行频率 |

相关代码：`client.py`、`server.py`。
