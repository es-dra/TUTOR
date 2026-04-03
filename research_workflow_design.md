# TUTOR - AI 科研助手工作流系统

**版本：** v2.0
**日期：** 2026-04-03
**状态：** 已实现的核心功能文档

---

## 目录

1. [系统概述](#1-系统概述)
2. [项目架构](#2-项目架构)
3. [核心数据模型](#3-核心数据模型)
4. [工作流引擎](#4-工作流引擎)
5. [四大工作流实现](#5-四大工作流实现)
6. [关键机制详解](#6-关键机制详解)
7. [辩论框架](#7-辩论框架)
8. [审批系统](#8-审批系统)
9. [监控与预算](#9-监控与预算)
10. [API 路由](#10-api-路由)
11. [前端集成](#11-前端集成)
12. [AI 赋能开发经验](#12-ai-赋能开发经验)
13. [评估与改进建议](#13-评估与改进建议)

---

## 1. 系统概述

### 1.1 目标定位

TUTOR 是一个基于大模型的**科研自动化工作流系统**，旨在帮助研究人员：
- 自动加载和分析学术论文
- 通过多 Agent 辩论生成创新性研究想法
- 自动设计和执行实验
- 辅助评审和论文撰写

### 1.2 核心技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 模型网关 | OpenAI API (兼容格式) |
| 工作流引擎 | 自定义 (支持检查点/断点续跑) |
| 存储 | SQLite + 文件系统 |
| 前端 | React + Tailwind CSS |

### 1.3 四大工作流

| 工作流 | 入口 | 核心产出 |
|--------|------|----------|
| **IdeaFlow** | 论文/研究方向 | 经过辩论和审批的研究想法 |
| **ExperimentFlow** | 想法 | 实验方案 + 执行结果报告 |
| **ReviewFlow** | 论文/实验 | 多维度评分报告 |
| **WriteFlow** | 评审结果 | 论文初稿 |

---

## 2. 项目架构

### 2.1 目录结构

```
D:\Projects\TUTOR\
├── tutor/                          # 主代码库
│   ├── api/                        # FastAPI 路由层
│   │   ├── routes/
│   │   │   ├── projects.py         # 项目管理 API
│   │   │   ├── workflows.py        # 工作流执行 API
│   │   │   ├── events.py           # SSE 事件推送
│   │   │   ├── auth.py             # 认证
│   │   │   └── providers.py        # 模型提供商
│   │   └── models/                 # Pydantic 模型
│   │
│   ├── core/                       # 核心业务逻辑
│   │   ├── workflow/               # 工作流实现
│   │   │   ├── base.py            # Workflow 基类、Context、Step
│   │   │   ├── idea.py            # IdeaFlow (含辩论、评估)
│   │   │   ├── experiment.py       # ExperimentFlow (环境检测→代码获取→执行→报告)
│   │   │   ├── review.py          # ReviewFlow (多角色评审)
│   │   │   ├── write.py           # WriteFlow (论文撰写)
│   │   │   ├── approval.py         # 审批系统
│   │   │   ├── project_gate.py    # 项目门控步骤
│   │   │   ├── debate_framework.py # 多维辩论框架
│   │   │   ├── retry.py          # 重试与回滚机制
│   │   │   └── steps/            # 工作流步骤
│   │   │       ├── paper_loading.py    # 论文加载
│   │   │       └── zotero_literature.py # Zotero 文献补充
│   │   │
│   │   ├── model/                 # 模型网关
│   │   │   └── __init__.py       # ModelGateway 类
│   │   │
│   │   ├── monitor/              # 监控系统
│   │   │   ├── token_budget.py  # Token 预算管理
│   │   │   ├── cost_tracker.py   # 成本追踪
│   │   │   ├── resource_monitor.py # 资源监控
│   │   │   ├── quotas.py         # 配额管理
│   │   │   └── collector.py     # 指标采集
│   │   │
│   │   ├── storage/              # 存储层
│   │   │   ├── manager.py       # StorageManager
│   │   │   ├── workflow_runs.py # 工作流运行记录
│   │   │   └── checkpoint_validation.py # 检查点校验
│   │   │
│   │   ├── debate/               # 辩论系统
│   │   │   └── cross_model_debater.py # 跨模型辩论
│   │   │
│   │   ├── review/               # 评审系统
│   │   │   ├── auto_reviewer.py
│   │   │   └── cross_model_reviewer.py
│   │   │
│   │   └── providers/            # 模型提供商
│   │       ├── openai.py
│   │       ├── anthropic.py
│   │       ├── deepseek.py
│   │       └── azure.py
│   │
│   └── config/                    # 配置
│
├── web/                           # React 前端
│   ├── src/
│   │   ├── App.js               # 主应用
│   │   ├── api.js              # API 调用
│   │   └── pages/              # 页面组件
│   │       ├── Dashboard.js
│   │       ├── Workflows.js
│   │       ├── NewWorkflow.js
│   │       ├── WorkflowDetail.js
│   │       └── Approvals.js
│   └── build/                   # 构建输出
│
└── research_workflow_design.md   # 本文档
```

### 2.2 关键依赖关系

```
API Routes (projects.py, workflows.py)
    ↓
WorkflowEngine → Workflow → WorkflowStep
    ↓
WorkflowContext (状态管理, 检查点)
    ↓
ModelGateway (统一模型调用)
    ↓
Providers (OpenAI, Anthropic, DeepSeek, Azure)
```

---

## 3. 核心数据模型

### 3.1 WorkflowStatus 枚举

```python
class WorkflowStatus(str, Enum):
    PENDING = "pending"      # 等待执行
    RUNNING = "running"      # 执行中
    PAUSED = "paused"       # 暂停等待审批
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"       # 失败
    CANCELLED = "cancelled" # 已取消
```

### 3.2 CheckpointData

```python
@dataclass
class CheckpointData:
    workflow_id: str
    workflow_type: str
    status: str
    current_step: int        # 当前步骤索引
    total_steps: int
    step_name: str
    input_data: Dict[str, Any]   # 步骤输入
    output_data: Dict[str, Any]  # 步骤输出
    error: Optional[str]
    created_at: str
    updated_at: str
```

**检查点机制**：
- 每个步骤执行后自动保存
- 文件名格式：`step_{step_index:04d}.json`
- 支持 CRC32 校验和自动修复
- 恢复时从最新有效检查点继续

### 3.3 WorkflowResult

```python
@dataclass
class WorkflowResult:
    workflow_id: str
    status: str
    output: Dict[str, Any]       # 工作流输出
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    decision_log: List[Dict]    # Orchestrator 决策日志
```

### 3.4 OrchestratorDecision

```python
@dataclass
class OrchestratorDecision:
    timestamp: str
    workflow_id: str
    step_name: str
    decision_type: str   # partial_result_accept, step_timeout_retry 等
    anomaly: str         # 异常描述
    decision: str        # 做出的决策
    impact: str          # 影响评估
    success: bool
```

---

## 4. 工作流引擎

### 4.1 核心架构

```
Workflow (抽象基类)
├── build_steps() → List[WorkflowStep]  # 子类实现
├── run() → WorkflowResult               # 执行流程
└── context: WorkflowContext              # 执行上下文

WorkflowStep (抽象基类)
├── execute(context) → Dict              # 步骤逻辑
├── validate(context) → List[str]       # 前置条件验证
└── rollback(context)                   # 可选回滚

WorkflowContext
├── workflow_id: str
├── config: Dict
├── _state: Dict                       # 内存状态
├── _current_step: int                # 当前步骤索引
├── _decision_log: List                # 决策日志
├── _token_tracker                      # Token 追踪器
├── save_checkpoint() → CheckpointData
├── get_state(key, default)
└── set_state(key, value)
```

### 4.2 执行流程 (run 方法)

```python
def run(self) -> WorkflowResult:
    self._start_monitoring()

    while self._current_step_index < len(self.steps):
        step = self.steps[self._current_step_index]

        # 更新 context 中的步骤索引（供 gate steps 使用）
        self.context._current_step = self._current_step_index

        # 前置条件验证
        errors = step.validate(self.context)
        if errors:
            raise ValueError(f"Step validation failed: {', '.join(errors)}")

        # 执行步骤（带重试）
        step_output = self._retry_manager.execute_with_retry(...)

        # 保存检查点
        self.context.save_checkpoint(
            step=self._current_step_index,
            step_name=step.name,
            input_data=step_input,
            output_data=step_output,
        )

        # 更新状态
        self.context.update_state(step_output)

        self._current_step_index += 1

    return WorkflowResult(..., decision_log=self.context.get_decision_log())
```

### 4.3 FailureStrategy 失败策略

```python
class FailureStrategy(Enum):
    ROLLBACK = "rollback"  # 回滚并停止
    STOP = "stop"         # 直接停止
    CONTINUE = "continue"  # 记录错误，继续执行
    PAUSE = "pause"       # 暂停等待人工决策
```

### 4.4 重试机制

```python
class RetryPolicy:
    max_attempts: int = 3
    backoff: str = "exponential"  # 指数退避
    base_delay: float = 1.0
    max_delay: float = 60.0
```

---

## 5. 四大工作流实现

### 5.1 IdeaFlow (想法生成)

**文件**：`tutor/core/workflow/idea.py`

**步骤流程**：
```
paper_loading → paper_validation → zotero_literature →
literature_analysis → idea_debate → idea_approval_gate →
idea_evaluation → final_proposal → project_gate_idea
```

**详细步骤**：

| 步骤 | 类名 | 职责 | 输出状态键 |
|------|------|------|----------|
| 1 | PaperLoadingStep | 加载 PDF/ArXiv URL | papers, load_errors |
| 2 | PaperValidationStep | 验证论文质量（长度、摘要） | validated_papers |
| 3 | ZoteroLiteratureStep | 补充 Zotero 文献 | zotero_papers, research_keywords |
| 4 | LiteratureAnalysisStep | AI 分析提取知识图谱 | literature_analysis, concepts |
| 5 | IdeaDebateStep | 多角色辩论生成想法 | debate_ideas, final_ideas, debate_quality |
| 6 | IdeaApprovalGateStep | **[介入点#1]** 辩论后审批 | approval_status |
| 7 | IdeaEvaluationStep | 评估想法可行性和创新性 | evaluated_ideas, recommended_idea, weakest_dimension, routing_decision |
| 8 | FinalProposalStep | 生成研究提案文档 | final_proposal |
| 9 | ProjectGateStep | **[最终审批]** 项目完成前审批 | - |

**关键特性**：
- 支持 ArXiv URL 和本地 PDF 两种来源
- 支持跨模型辩论模式 (`cross_model_debate: true`)
- 辩论质量评估 (`genuine_conflict` / `weak_conflict` / `false_consensus`)
- 评分路由决策（创新性不足 → retry_w1，方法论问题 → proceed_w2）

### 5.2 ExperimentFlow (实验执行)

**文件**：`tutor/core/workflow/experiment.py`

**步骤流程**：
```
environment_check → code_fetch → dependency_install →
experiment_execution → results_analysis → comparison_evaluation →
experiment_report → project_gate_experiment
```

**详细步骤**：

| 步骤 | 类名 | 职责 |
|------|------|------|
| 1 | EnvironmentCheckStep | 检测 GPU、磁盘空间、内存 |
| 2 | CodeFetchStep | 获取相关代码仓库 |
| 3 | DependencyInstallStep | 安装依赖 |
| 4 | ExperimentExecutionStep | 执行实验 |
| 5 | ResultsAnalysisStep | 分析实验结果 |
| 6 | ComparisonEvaluationStep | 与基线对比 |
| 7 | ExperimentReportStep | 生成实验报告 |

**配置参数**：
```yaml
workflow:
  type: experiment
  timeout_minutes: 30
  execution_mode: local  # local | remote
```

### 5.3 ReviewFlow (评审)

**文件**：`tutor/core/workflow/review.py`

**支持三种评审模式**：

| 模式 | 说明 |
|------|------|
| `single` | 单一模型评审 (MVP) |
| `cross_model` | 不同模型对抗式评审 |
| `auto_loop` | 迭代式改进直到收敛 |

**评审维度**：
- 创新性 (Novelty) - 30%
- 方法严谨性 (Rigor) - 25%
- 可行性 (Feasibility) - 20%
- 领域贡献 (Contribution) - 15%
- 表达完整性 (Clarity) - 10%

### 5.4 WriteFlow (论文撰写)

**文件**：`tutor/core/workflow/write.py`

**步骤流程**：
```
outline_generation → introduction_writing → related_work_writing →
methodology_writing → experiments_writing → conclusion_writing →
polishing
```

---

## 6. 关键机制详解

### 6.1 检查点与断点续跑

**保存时机**：每个步骤执行成功后

**恢复逻辑**：
```python
latest_checkpoint = self.context.get_latest_checkpoint()
if latest_checkpoint:
    if latest_checkpoint.status == WorkflowStatus.PAUSED:
        self._current_step_index = latest_checkpoint.current_step
    else:
        self._current_step_index = latest_checkpoint.current_step + 1
    self.context.update_state(latest_checkpoint.output_data)
```

**CRC32 校验**：
- 保存时计算 `zlib.crc32` 并附加到文件
- 加载时验证，不匹配则尝试更早的检查点

### 6.2 辩论质量评估

**评估方法**：`_assess_debate_quality()`

**输出值**：
- `genuine_conflict` - 真正的辩论，Skeptic 提出实质质疑
- `weak_conflict` - 存在一些质疑但不够充分
- `false_consensus` - Skeptic 基本上被说服

**评估逻辑**：
```python
# 检查 Skeptic 回复中的质疑关键词
challenge_patterns = ['but', 'however', 'problem', 'flaw', 'risk', ...]
# 检查认同关键词
agreement_patterns = ['agree', 'good', 'valid', 'strong', ...]

# 决策
if challenge_count >= 2 and avg_length > 100:
    return "genuine_conflict"
if challenge_count == 0 and agreement_count >= 2:
    return "false_consensus"
```

### 6.3 评分路由决策

**评估方法**：`_compute_routing()`

```python
def _compute_routing(self, evaluated_ideas):
    weakest = min(scores, key=scores.get)

    if weakest == "innovation" and scores[weakest] < 0.5:
        return "retry_w1_new_ideas"  # 创新性不足，退回 W1
    elif weakest in ("feasibility", "clarity"):
        return "proceed_w2_keep_idea"  # 方法论问题，保留想法继续
    else:
        return "proceed"
```

### 6.4 Token 预算管理

**文件**：`tutor/core/monitor/token_budget.py`

```python
class TokenBudget:
    DEFAULT_SESSION_BUDGET = 100000  # 100K tokens
    WARNING_THRESHOLD = 0.80        # 80% 预警
    PAUSE_THRESHOLD = 0.95         # 95% 暂停

class WorkflowTokenTracker:
    def record_api_call(self, messages, max_tokens, step_name):
        estimated = self.estimate_prompt_tokens(messages, max_tokens)
        self.budget.add_cost(estimated, step_name)
```

---

## 7. 辩论框架

### 7.1 多维辩论 (MultiDimensionalDebate)

**文件**：`tutor/core/workflow/debate_framework.py`

**五维评分**：
```python
class DimensionType(Enum):
    METHODOLOGY = "methodology"       # 方法论有效性
    DATA_SUPPORT = "data_support"     # 数据支持度
    GENERALIZABILITY = "generalizability"  # 结论普适性
    INNOVATION = "innovation"        # 创新性
    REPRODUCIBILITY = "reproducibility"  # 可复现性
```

### 7.2 跨模型辩论 (CrossModelDebater)

**文件**：`tutor/core/debate/cross_model_debater.py`

**角色配置**：
- Innovator - 激进派，提出新颖想法
- Skeptic - 保守派，质疑可行性
- Pragmatist - 实用派，评估可行性
- Expert - 领域专家，提供背景知识

**配置示例**：
```yaml
cross_model_config:
  innovator: ["claude-sonnet-4"]
  skeptic: ["gpt-4o"]
  pragmatist: ["gemini-2-5-pro"]
```

### 7.3 辩论角色定义

```python
DEBATER_B_PROMPT = """
你是一位极其严苛的科研评审者。你的核心任务是找出对方论点中的漏洞，
而不是被说服。即使对方的论证听起来有道理，你也必须从更高标准审视...
"""
```

---

## 8. 审批系统

### 8.1 审批状态

```python
class ApprovalStatus(str, Enum):
    PENDING = "pending"    # 等待审批
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"   # 已拒绝
    TIMEOUT = "timeout"     # 超时
    CANCELLED = "cancelled" # 已取消
```

### 8.2 审批管理器

```python
class ApprovalManager:
    _requests: Dict[str, ApprovalRequest]

    def create_request(...) -> ApprovalRequest
    def approve(approval_id, by, comment) -> bool
    def reject(approval_id, by, comment) -> bool
    def get_request(approval_id) -> Optional[ApprovalRequest]
    def list_pending(run_id) -> List[ApprovalRequest]
```

### 8.3 门控步骤

**ProjectGateStep**：工作流结束前的最终审批

**IdeaApprovalGateStep**：辩论结束后的想法审批（介入点 #1）

**设计模式**：
```python
class ProjectGateStep(WorkflowStep):
    def execute(self, context):
        # 1. 创建审批请求
        manager.create_request(approval_id=..., ...)

        # 2. 保存检查点
        context.save_checkpoint(...)

        # 3. 抛出暂停异常
        raise WorkflowPauseError("waiting for approval")
```

**恢复时跳过**：如果已有审批结果，直接跳过步骤。

---

## 9. 监控与预算

### 9.1 资源监控

```python
class ResourceMonitor:
    def collect(self) -> ResourceSnapshot:
        # CPU, Memory, Disk, GPU
```

### 9.2 配额管理

```python
class QuotaManager:
    thresholds = {
        CPU: 90.0,      # %
        Memory: 80.0,
        Disk: 80.0,
        GPU: 80.0,
    }

    def check(self, snapshot) -> List[QuotaWarning]
```

### 9.3 成本追踪

```python
class CostTracker:
    def record(self, entry: CostEntry):
        # 记录到 SQLite
```

---

## 10. API 路由

### 10.1 工作流 API

**文件**：`tutor/api/routes/workflows.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/{workflow_name}/run` | 启动工作流 |
| GET | `/{run_id}` | 获取运行状态 |

### 10.2 项目 API

**文件**：`tutor/api/routes/projects.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 列出所有项目 |
| POST | `/` | 创建项目 |
| GET | `/{project_id}` | 获取项目详情 |
| POST | `/{project_id}/run` | 为项目运行工作流 |
| POST | `/{project_id}/approve` | 审批项目 |

### 10.3 SSE 事件

```python
emit_workflow_started(run_id, workflow_name, started_at)
emit_step_completed(run_id, step_name, status)
emit_workflow_finished(run_id, status, result)
emit_log(run_id, level, message)
```

---

## 11. 前端集成

### 11.1 页面结构

```
Dashboard      - 工作台总览
Workflows      - 工作流列表
NewWorkflow    - 创建新工作流
WorkflowDetail - 工作流详情
Approvals      - 审批管理
Settings       - 系统设置
```

### 11.2 实时更新

使用 **Server-Sent Events (SSE)** 接收后端推送：
- 工作流状态变更
- 步骤完成通知
- 日志输出

### 11.3 状态管理

React Context / Hooks 管理：
- 项目列表
- 当前工作流状态
- 审批请求

---

## 12. AI 赋能开发经验

### 12.1 迭代式开发策略

1. **先有骨架**：先实现工作流引擎和基本步骤
2. **渐进增强**：逐步添加辩论、评估、审批等复杂功能
3. **每步可运行**：每个功能点完成后立即测试

### 12.2 检查点设计的重要性

**问题**：长工作流执行中一旦失败，从头开始代价高昂。

**解决方案**：
- 每个步骤后自动保存检查点
- 支持 CRC32 校验防止数据损坏
- 恢复时自动定位最新有效检查点

**代码示例**：
```python
# 保存
checkpoint.save(path)

# 恢复时验证
data = validate_checkpoint_file(path, repair=True)
if data is None:
    continue  # 尝试更早的检查点
```

### 12.3 状态与执行分离

**问题**：步骤既需要读取上下文，又需要保存输出。

**设计**：
```python
# WorkflowContext 负责状态存储
context.get_state("key")
context.set_state("key", value)

# 步骤只返回输出字典
return {"papers": [...], "errors": [...]}
```

### 12.4 可选功能的优雅降级

**问题**：Zotero、ArXiv 等外部服务可能不可用。

**解决方案**：
```python
class ZoteroLiteratureStep(WorkflowStep):
    def validate(self, context):
        client = self._get_client()
        if not client:
            return ["Zotero not configured"]  # 前置条件失败
        return []

    def execute(self, context):
        if not self._get_client():
            return {"skipped": True, "reason": "Zotero not configured"}
        # 正常逻辑
```

### 12.5 多模型灵活切换

**问题**：不同模型提供商 API 格式不同。

**解决方案**：ModelGateway 统一接口
```python
class ModelGateway:
    def chat(self, role, messages, temperature, max_tokens):
        # 根据 role 解析实际模型
        # 统一错误处理和重试
        return self._call_api(model_id, messages, ...)
```

### 12.6 决策日志的透明度

**问题**：自主决策后用户不知情，难以追溯问题。

**解决方案**：
```python
class WorkflowContext:
    def log_decision(self, step_name, decision_type, anomaly, decision, impact):
        orch_decision = OrchestratorDecision(...)
        self._decision_log.append(orch_decision)

    def get_decision_log(self):
        return [d.to_dict() for d in self._decision_log]
```

---

## 13. 评估与改进建议

### 13.1 已实现的核心功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 工作流引擎 | ✅ | 完整实现 |
| 四大工作流 | ✅ | Idea/Experiment/Review/Write |
| 检查点恢复 | ✅ | CRC32 校验 |
| 审批系统 | ✅ | 异步审批 |
| 辩论框架 | ✅ | 多维 + 跨模型 |
| 辩论质量评估 | ✅ | genuine/weak/false |
| 决策日志 | ✅ | OrchestratorDecision |
| Token 预算 | ✅ | 80%/95% 阈值 |
| 模型网关 | ✅ | OpenAI 兼容 |
| SSE 实时推送 | ✅ | 状态更新 |

### 13.2 已知限制

| 限制 | 说明 | 建议改进 |
|------|------|----------|
| Token 计数估算 | 使用字符估算，不精确 | 可从 API 响应获取实际 usage |
| 外部服务依赖 | ArXiv 国内可能超时 | 增加本地 PDF 备选 |
| 单机存储 | 检查点存本地文件 | V2 考虑分布式存储 |
| 前端界面 | 基本可用，待美化 | 参考设计文档的 UI |

### 13.3 建议的优先级改进

**P0 - 必须修复**：
1. ArXiv 网络超时处理（已有限制提示）
2. Token 计数精确化（需 API 支持）

**P1 - 高优先级**：
1. 完善前端审批界面
2. 增加 ExperimentFlow 远程执行

**P2 - 中优先级**：
1. ReviewFlow 自动循环模式
2. WriteFlow 完整实现

**P3 - 低优先级**：
1. 多会话并行
2. 用户偏好学习

---

## 附录：关键文件索引

| 文件 | 关键类/函数 |
|------|-------------|
| `tutor/core/workflow/base.py` | Workflow, WorkflowContext, CheckpointData |
| `tutor/core/workflow/idea.py` | IdeaFlow, LiteratureAnalysisStep, IdeaDebateStep, IdeaEvaluationStep |
| `tutor/core/workflow/experiment.py` | ExperimentFlow, EnvironmentCheckStep |
| `tutor/core/workflow/review.py` | ReviewFlow |
| `tutor/core/workflow/write.py` | WriteFlow, OutlineGenerationStep |
| `tutor/core/workflow/approval.py` | ApprovalManager, ApprovalStep |
| `tutor/core/workflow/debate_framework.py` | MultiDimensionalDebate, DimensionType |
| `tutor/core/model/__init__.py` | ModelGateway |
| `tutor/core/monitor/token_budget.py` | TokenBudget, WorkflowTokenTracker |
| `tutor/api/routes/projects.py` | run_workflow, approve_project |

---

*本文档版本 v2.0，完整记录已实现的 TUTOR 系统架构与设计决策。*
