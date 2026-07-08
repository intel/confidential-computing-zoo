# OpenViking Service 示例

本目录包含一个示例适配器，演示 OpenViking 如何与 Agent-CC 集成作为机密 Agent memory 服务。

## 概述

OpenViking 是专为 AI 智能体设计的开源上下文数据库，提供基于证明的上下文存储和检索。本示例展示 OpenViking 如何使用 Agent-CC 的核心服务进行可信上下文传输。

## 上下文网关操作

OpenViking 暴露的上下文操作均基于证明：

| 操作 | 描述 | 需要证明 |
|------|------|----------|
| `observe` | 读取上下文元数据（不物化） | 是 |
| `recall` | 物化上下文以供处理 | 是 |
| `commit` | 存储带证明绑定的上下文 | 是 |
| `privacy_restore` | 恢复加密上下文 | 是 |

## OpenClaw 集成

OpenViking 通过 verify-skill trust gate 与 OpenClaw 配合工作：

- OpenClaw 在发送上下文前调用本地 verify skill
- Verify skill 验证 OpenViking 或网关证明
- 当验证失败或不可用时，上下文传输被拒绝

详见 [OpenViking Trusted Context Gate 规范](../../openspec/specs/openviking-trusted-context-gate/spec.md)。

## 部署模式

### 1. Python Demo 模式

`openviking_service.py` 提供内存态演示，用于验证 trust-gate 流程：

```bash
# 内存态演示（自动退出）
python3 openviking_service.py

# HTTP 服务模式
python3 openviking_service.py --serve
```

> **注意**：Demo 模式（`openviking_service.py`）在内存中运行，无真实 TDX quote。
> 要进行生产或完整证明验证，请使用 `run_openclaw_openviking_e2e.sh`。

### 2. tc-api 管理模式

通过 tc-api 管理的 Docker 启动路径运行时，Argus claims 才能带出 tc-api 元数据：

1. `configs/docker-compose.tc-api.yml`：启动本地 registry、tc-api，以及 Argus Evidence Provider
2. `configs/Dockerfile.tc-api-workload`：打包 `openviking_service.py --serve` 成真正的 service workload 镜像
3. `scripts/launch_openviking_via_tc_api.sh`：构建镜像、推送到本地 registry，并提交 deploy-launch 请求

### 2.1 使用 LUKS 做 OpenViking 落盘保护（推荐）

`openviking_service.py` 现在会把 context 持久化到 `OPENVIKING_DATA_DIR`（默认
`/mnt/encrypted/openviking`）。要避免明文落盘，建议先在宿主机挂载 LUKS，
再通过 `launch_openviking_via_tc_api.sh` 绑定到 workload 容器。

1. 在 OpenViking 宿主机创建并挂载 LUKS 存储：

```bash
cd ../../../../openclaw-cc/luks_tools
./create_encrypted_vfs.sh 10G /root/vfs-openviking.img
# 记录脚本输出的 LOOP_DEVICE，然后挂载
./mount_encrypted_vfs.sh <LOOP_DEVICE> format openviking_luks /home/encrypted_storage
```

2. 启动 OpenViking（默认已开启 LUKS 检查）：

```bash
cd ../agent-cc/adapters/OpenViking/scripts
export OPENVIKING_USE_LUKS=1
export OPENVIKING_LUKS_MOUNT_ROOT=/home/encrypted_storage
export OPENVIKING_LUKS_SUBDIR=openviking
export OPENVIKING_CONTAINER_DATA_DIR=/mnt/encrypted/openviking
./launch_openviking_via_tc_api.sh
```

当 `OPENVIKING_USE_LUKS=1` 时，脚本会检查 `OPENVIKING_LUKS_MOUNT_ROOT`
是否为已挂载目录；若未挂载会直接失败，避免写到未加密路径。

3. 仅本地调试时可关闭 LUKS 强制：

```bash
export OPENVIKING_USE_LUKS=0
./launch_openviking_via_tc_api.sh
```

### 2.2 真实落盘的配置机制与环境变量

OpenViking 的“真实落盘”不是靠内存态配置，而是以下链路共同生效：

1. 宿主机启动脚本 `launch_openviking_via_tc_api.sh` 读取 LUKS/目录相关变量。
2. 脚本生成 `dockercmd`，通过 tc-api `POST /api/deploy-launch` 下发给运行时。
3. `dockercmd` 在容器启动时注入：
    - 环境变量 `OPENVIKING_DATA_DIR=<容器内目录>`
    - 挂载 `-v <宿主机目录>:<容器内目录>`
4. `openviking_service.py` 启动后读取 `OPENVIKING_DATA_DIR`，并把 context 文件持久化到
    `<OPENVIKING_DATA_DIR>/contexts/`。

变量说明（按作用域）：

| 变量名 | 作用域 | 默认值 | 作用 |
|---|---|---|---|
| `OPENVIKING_USE_LUKS` | 宿主机启动脚本 | `1` | 是否强制使用已挂载的 LUKS 目录。`1` 时未挂载即失败。 |
| `OPENVIKING_LUKS_MOUNT_ROOT` | 宿主机启动脚本 | `/home/encrypted_storage` | LUKS 挂载根目录（必须是 mountpoint）。 |
| `OPENVIKING_LUKS_SUBDIR` | 宿主机启动脚本 | `openviking` | 在挂载根目录下用于 OpenViking 数据的子目录。 |
| `OPENVIKING_CONTAINER_DATA_DIR` | 宿主机启动脚本 | `/mnt/encrypted/openviking` | 容器内数据目录；同时用于 `-e OPENVIKING_DATA_DIR` 和 `-v` 目标路径。 |
| `OPENVIKING_DATA_DIR` | 容器内服务进程 | `/mnt/encrypted/openviking` | `openviking_service.py` 实际读取的落盘目录。 |

可以把它理解为：
`OPENVIKING_* (宿主机)` -> 生成 `dockercmd` -> 注入 `OPENVIKING_DATA_DIR (容器)` ->
服务写入 `${OPENVIKING_DATA_DIR}/contexts/*.json`。

最小自检：

```bash
# 1) 看容器内环境变量
docker exec <openviking_container> printenv OPENVIKING_DATA_DIR

# 2) 看容器内文件
docker exec <openviking_container> ls -l ${OPENVIKING_CONTAINER_DATA_DIR}/contexts

# 3) 看宿主机对应目录（应与容器内一致）
ls -l ${OPENVIKING_LUKS_MOUNT_ROOT}/${OPENVIKING_LUKS_SUBDIR}/contexts
```

OpenViking 本身不启动 Argus Evidence Provider。预期流程是只在
OpenViking 一侧使用 `ARGUS_WORKLOAD_IDENTITY=openviking-cmem` 启动 provider，
而 OpenClaw 一侧运行自己的本地 Guard，并通过 `EVIDENCE_ENDPOINT` 指向
这个远端 provider。

如果希望在 Argus claims 中带出 `image_digest`、`launch_id` 和 Rekor 标识符，
provider 还需要设置 `ARGUS_SERVICE_ID` 和 `TC_API_WORKLOAD_ID`，并且
这两个值必须与 tc-api 为 OpenViking Docker workload 分配或接收的 workload ID 一致。

可运行示例默认采用 `STRICT_MODE=false`。在当前 live TSM 路径下，只要
quote 结构校验和请求绑定校验通过，Argus 就会返回 `TCB Status: UpToDate`。
这个状态可以满足示例里的默认策略流转，但它仍然不代表已经完成
collateral-backed 的 TCB 新鲜度判定。

## 运行步骤

**完整端到端测试请参考 [OpenClaw Scripts README](../../OpenClaw/scripts/README.md)**

该文档包含：
- 前置条件检查
- 环境验证步骤
- 构建说明
- 完整 e2e 测试运行命令

## Provider 一侧环境变量示例

```bash
cd <work_dir>/confidential-computing-zoo/cczoo/agent-cc/core/argus
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
export ARGUS_SERVICE_ID=openviking-cmem
export TC_API_WORKLOAD_ID=openviking-cmem
export TC_API_URL=http://127.0.0.1:8000
./start_argus.sh start-provider
```

## 另请参阅

- [OpenViking Trusted Context Gate 规范](../../openspec/specs/openviking-trusted-context-gate/spec.md)
- [Argus Verifier](../../core/argus/README.md) - TDX quote 验证
- [TC-API Service](../../core/tc-api/README.md) - 构建到运行时的信任