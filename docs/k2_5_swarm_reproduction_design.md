# SwarmFlight 复刻 Kimi K2.5 Agent Swarm 设计草案（评审稿）

## 1. 目标与范围

本设计的目标是：在开源工程里复刻 **K2.5 Agent Swarm 的方法论**（尤其是并行编排 + 资源约束 + 策略学习），而不是复刻 K2.5 模型本体。

### 1.1 in-scope

- 动态任务分解与子 agent 并行执行
- `create_subagent` / `assign_task` 类接口
- 基于依赖图的任务调度、重试、失败级联
- 关键路径近似指标（Critical Steps）与延迟/质量/成本联合评估
- 训练或在线学习的 orchestrator 策略（PARL-inspired）

### 1.2 out-of-scope

- K2.5 原始权重、预训练、多模态底座复刻
- 论文同规模 RL 训练资源（我们做可复现实验版）


## 2. 当前实现 vs 论文思想差距

当前 `v0.2` 已有：

- runtime：任务图依赖、重试、失败级联、mailbox、worker 抽象
- benchmark：single vs swarm 合成基准，输出 pass rate / critical steps / token cost / wall time

仍缺失的论文关键点：

1. **可学习 orchestrator**：目前是规则+轮询，不是学习策略。
2. **PARL 奖励闭环**：尚未实现 `r_parallel + r_finish + r_perf` 的训练信号与退火。
3. **冻结子策略池**：缺“固定 checkpoint 的 subagent 池”与采样策略。
4. **并行动作空间**：没有显式动作“是否并行、并行多少、如何拆分”。
5. **资源约束训练**：critical steps 目前仅评测指标，未进入优化目标。
6. **任务分布课程化**：缺 wide/deep prompt curriculum 与分布调度。
7. **上下文管理策略实验**：缺 context window 压力下的策略对比。


## 3. 设计原则

1. 模型无关：支持任意 LLM provider，不绑某家 API。
2. 先可测再智能：先保证可复现实验与指标可信，再做策略学习。
3. 分层解耦：`runtime / policy / benchmark / telemetry` 分离。
4. 可回放：每轮调度决策和结果都可追踪、复盘、再训练。


## 4. 目标架构（v0.3-v0.6）

## 4.1 核心组件

- **Orchestrator Runtime**
  - 职责：维护任务图、执行状态机、资源预算、失败策略
  - 输出：每个调度 step 的 observation + action + outcome

- **Policy Engine**
  - HeuristicPolicy（基线）
  - BanditPolicy（在线学习）
  - RLPolicy（离线训练，PARL-inspired）

- **Subagent Pool（Frozen）**
  - 多个固定能力档位（small/medium/large）
  - 执行轨迹不反向更新（符合论文 decoupled 思路）

- **Evaluation Harness**
  - wide-search / deep-search / mixed coding scenarios
  - 输出统一报告（质量、延迟、成本、稳定性）

- **Telemetry & Replay**
  - step trace（JSONL）
  - 回放器（replayer）
  - 训练样本导出（policy training dataset）


## 4.2 调度动作空间（Action Space）

每个 orchestrator step 动作定义为：

- `finish`: 结束并产出答案
- `tool_call(tool, args)`: 主 agent 直接执行工具
- `spawn(n, profile)`: 创建 n 个子 agent（profile 指能力档）
- `assign(subagent_id, subtask)`: 分配子任务
- `join(ids)`: 聚合子任务输出
- `replan(scope)`: 触发重分解

约束：

- 最大并发 subagents
- 最大 step / 最大 tool calls
- 预算（token/cost/time）


## 5. PARL-inspired 训练/学习方案

论文级 RL 难度高，采用三阶段渐进：

### Phase A（v0.3）：规则+日志

- 用启发式 policy 完整跑通动作空间
- 记录 `obs, action, reward_proxy, next_obs`
- 形成训练数据闭环

### Phase B（v0.4）：Bandit/Contextual Bandit

- 学习“并行度选择”和“何时 spawn”
- 奖励函数先用代理形式：
  - `r_perf`: 任务正确/覆盖
  - `r_latency`: critical steps 负值
  - `r_cost`: token/cost 负值

### Phase C（v0.5-v0.6）：轻量 RL（PARL-inspired）

- 引入：
  - `r_parallel`：避免 serial collapse
  - `r_finish`：避免无效并发
  - `r_perf`：结果质量主奖励
- 训练时退火：`lambda_parallel`, `lambda_finish` 逐步衰减
- 子 agent 参数冻结，仅更新 orchestrator policy


## 6. 指标体系（强制）

每次实验必须输出：

- 质量：`pass@1`, `item_f1`, `success_rate`
- 延迟：`critical_steps`, `wall_clock_ms`
- 成本：`tokens_in/out`, `estimated_cost`
- 稳定性：`retry_count`, `failure_rate`, `skip_rate`
- 并行行为：`avg_parallelism`, `spawn_count`, `subtask_finish_rate`

验收标准（初版）：

- 在 wide-search 基准上，swarm 相比 single：
  - 质量不下降（`pass_rate` 至少持平）
  - `critical_steps` 至少降低 30%


## 7. 里程碑计划

### v0.3（2周）

- 完成动作空间 API（spawn/assign/join/replan）
- 支持并发 worker 执行（线程或 asyncio）
- 输出标准化 trace 与 replay

### v0.4（2周）

- 接入 BanditPolicy
- 基准扩展为 wide/deep/mixed 三类
- 增加上下文预算压力测试

### v0.5（2-3周）

- 轻量 RLPolicy（离线训练+在线评估）
- 奖励退火策略
- frozen subagent profile 池

### v0.6（2周）

- 稳定性强化（超时、取消、死锁、backpressure）
- 公开 benchmark 报告模板与可复现实验脚本


## 8. 风险与规避

- 风险：并行后质量下降
  - 规避：引入 `join` 校验和再规划步骤，质量门控
- 风险：奖励黑客（无意义 spawn）
  - 规避：`r_finish` + spawn 成本惩罚 + 上限
- 风险：训练不稳定
  - 规避：先 bandit 后 RL，小步迭代
- 风险：工程复杂度失控
  - 规避：接口先定死，组件按里程碑解锁


## 9. 本次评审需要你确认的决策

1. 是否接受三阶段路线（Heuristic -> Bandit -> RL）而不是直接 RL？
2. v0.3 是否先使用 `asyncio` 并发模型（跨平台简单）？
3. v0.4 的主指标是否以 `critical_steps` 为主、`wall_clock` 为辅？
4. 是否优先做“研究基准可复现”，再做 IDE/CLI 体验增强？


## 10. 评审后立即可执行的下一步

- 新建 `runtime/policy.py` 与 `runtime/actions.py`
- 新建 `benchmarks/scenarios/`（wide/deep/mixed）
- 增加 `trace` 输出结构（JSONL）与 `replay` CLI 子命令
- 补一份 `docs/metrics.md` 定义所有指标计算方式
