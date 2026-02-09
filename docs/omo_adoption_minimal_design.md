# SwarmFlight 借鉴 Oh My OpenCode 的最小落地设计（v0.4-v0.6）

## 1. 背景

SwarmFlight 当前 `v0.3` 已具备：

- 任务依赖图执行（`Orchestrator`）
- 失败重试与失败级联（`FAILED -> SKIPPED`）
- trace 记录与 replay
- single vs swarm 合成基准

与下一阶段目标相比，仍缺 3 个关键能力：

1. 真正的并发执行内核（目前主要是同步轮询）
2. 可恢复执行状态（重启后续跑）
3. 可插拔策略/守护机制（而非把所有逻辑写死在 orchestrator）

Oh My OpenCode（以下简称 OMO）在工程机制上有可复用思路，适合做“最小借鉴”，不照搬其产品形态。


## 2. 借鉴点映射（做什么，不做什么）

| OMO 机制 | SwarmFlight 借鉴方式 | 优先级 |
|---|---|---|
| 计划/执行分层 | 保留 `Policy` 和 `Orchestrator` 分层，补齐 action 驱动执行 | P0 |
| 持久化任务状态 | 增加 task state 存储 + 原子写 + 文件锁 | P0 |
| boulder 式续跑 | 增加 run checkpoint + `resume` CLI | P0 |
| 并发配额层级（model/provider/default） | 增加 `ConcurrencyManager`，支持 worker profile 配额 | P0 |
| 后台任务状态机与超时回收 | 增加 pending/running/completed/failed/cancelled/stale 状态治理 | P1 |
| hook 机制（truncation/recovery/reminder） | 先做最小事件总线 + 3 个核心 hook | P1 |
| 多人设 agent 生态 | 不做（与 SwarmFlight 当前目标不匹配） | Out |
| 大量 CLI 工作流命令 | 不做（先稳 runtime） | Out |


## 3. 目标与非目标

### 3.1 目标

- 在不破坏现有 API 的前提下，补齐可并发、可恢复、可扩展三件事。
- 保持 benchmark 可复现，并在 wide/deep/mixed 上对比增量收益。
- 保持实现简单，优先落在 runtime 层，不先做重 UI/交互。

### 3.2 非目标

- 不在本阶段引入复杂 RL 训练框架。
- 不实现 OMO 的完整插件生态与代理人格体系。
- 不引入远程服务依赖，先保持本地可复现实验闭环。


## 4. 分阶段方案

## 4.1 Phase A（v0.4）：并发执行内核

### 交付

- `WorkerPool`：并发执行任务，支持 worker profile。
- `ConcurrencyManager`：配额优先级 `task.profile > provider > default`。
- `TaskRuntimeState`：`pending/running/completed/failed/skipped/cancelled/stale`。
- `stale_timeout_ms` 与 `max_runtime_ms` 守护。

### 最小接口草图

```python
class Orchestrator:
    def run_tick(self) -> list[TaskResult]:
        """执行一个调度 tick，可能触发 0..N 个任务并发执行。"""

    def run_until_idle(self) -> list[TaskResult]:
        """持续运行直到 ready 队列清空且无 running 任务。"""
```

```python
class ConcurrencyManager:
    def acquire(self, profile: str) -> bool: ...
    def release(self, profile: str) -> None: ...
    def limit_for(self, profile: str) -> int: ...
```


## 4.2 Phase B（v0.5）：可恢复执行

### 交付

- `RunCheckpointStore`：周期性保存运行状态。
- CLI 新增 `swarmflight resume <checkpoint.json>`。
- `TraceRecorder` 与 checkpoint 对齐（同一 `run_id`）。

### checkpoint 示例

```json
{
  "run_id": "run_20260209_001",
  "created_at": "2026-02-09T10:00:00Z",
  "ready_queue": ["task-3", "task-5"],
  "blocked": ["task-9"],
  "running": ["task-4"],
  "tasks": {
    "task-1": {"status": "completed", "attempts": 1},
    "task-4": {"status": "running", "attempts": 1}
  },
  "results": {
    "task-1": {"ok": true, "attempt": 1}
  },
  "scheduler": {"cursor": 3}
}
```


## 4.3 Phase C（v0.6）：策略与 hook 插件化

### 交付

- `EventBus`：统一发布 runtime 事件。
- `Hook` 接口：支持前后置钩子。
- 首批 3 个 hook：
  1) `retry_backoff_hook`（重试退避）
  2) `output_truncation_hook`（大输出截断）
  3) `stability_guard_hook`（异常状态恢复建议）

### 事件草图

```python
class RuntimeEvent(TypedDict):
    kind: str
    run_id: str
    task_id: str | None
    payload: dict[str, Any]
```

事件最小集合：

- `task_submitted`
- `task_scheduled`
- `task_attempt`
- `task_retrying`
- `task_terminal`
- `checkpoint_saved`


## 5. 数据结构建议

```python
@dataclass(slots=True)
class TaskExecutionMeta:
    profile: str = "default"
    queued_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    stale_timeout_ms: int | None = None

@dataclass(slots=True)
class Checkpoint:
    run_id: str
    ready_queue: list[str]
    blocked: list[str]
    running: list[str]
    scheduler_cursor: int
    tasks: dict[str, dict[str, Any]]
    results: dict[str, dict[str, Any]]
```


## 6. 与现有文件的对齐修改建议

- `src/swarmflight/runtime/orchestrator.py`
  - 增加并发 tick 执行路径与 running 集合管理
  - 将 policy action 从“记录”升级为“驱动行为”
- `src/swarmflight/runtime/models.py`
  - 扩展任务执行元数据（profile/timeouts）
- `src/swarmflight/runtime/trace.py`
  - 增加 `run_id`，并记录 checkpoint 事件
- `src/swarmflight/cli.py`
  - 新增 `resume` 子命令
- `src/swarmflight/benchmarks/harness.py`
  - 补充新指标：`avg_parallelism`、`stale_count`


## 7. 验收标准

## 7.1 功能正确性

- 重启后可通过 checkpoint 恢复，结果与不中断运行等价（同随机种子）。
- 依赖失败级联行为保持不变。
- 重试/跳过/失败统计不回归。

## 7.2 性能与稳定性

- wide 场景下，`critical_steps` 对 v0.3 至少再下降 20%。
- 出现 worker 卡住时，能被 `stale_timeout` 正确回收。
- 并发配额生效，无超配执行。

## 7.3 可观测性

- trace 能还原每次调度决策和尝试。
- replay 输出新增 checkpoint 与并发相关统计项。


## 8. 测试计划

- 单测：
  - `ConcurrencyManager` 限流与释放
  - checkpoint 序列化/反序列化
  - resume 后状态一致性
  - stale 回收与取消语义
- 集成：
  - `bench` + `resume` 断点续跑
  - single/swarm 在 wide/deep/mixed 的指标不回归
- 回归：
  - 现有 `tests/test_orchestrator.py`、`tests/test_benchmarks.py` 全绿


## 9. 风险与规避

- 风险：并发引入竞态，结果顺序不稳定
  - 规避：terminal result 顺序单独维护，输出按任务 ID 稳定排序
- 风险：checkpoint 过大影响性能
  - 规避：增量 checkpoint + 可配置保存间隔
- 风险：hook 过多影响可调试性
  - 规避：默认仅启用 3 个核心 hook，全部可关闭


## 10. 建议执行顺序（可直接开工）

1. 先实现 `ConcurrencyManager` 与 `run_tick`，跑通并发内核。
2. 再实现 `CheckpointStore` 与 `resume` CLI，跑通中断恢复。
3. 最后接入 `EventBus + Hook`，先上 3 个核心 hook。

该顺序可以在每一阶段都保持“可运行、可测试、可回滚”。
