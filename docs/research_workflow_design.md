# TUTOR - AI 科研助手工作流系统

**版本：** v2.1
**日期：** 2026-04-05
**状态：** 完整实现文档

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
12. [外部服务集成](#12-外部服务集成)
13. [CLI 命令行工具](#13-cli-命令行工具)
14. [配置管理](#14-配置管理)
15. [测试体系](#15-测试体系)
16. [AI 赋能开发经验](#16-ai-赋能开发经验)
17. [评估与改进建议](#17-评估与改进建议)

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
| 后端框架 | FastAPI + Uvicorn (端口 8092) |
| 模型网关 | OpenAI API 兼容格式，支持多 Provider |
| 工作流引擎 | 自定义 (支持检查点/断点续跑) |
| 存储 | SQLite + 文件系统 |
| 前端 | React 18 + Vite (端口 3000) + Tailwind CSS |
| 认证 | JWT Token |
| 外部集成 | Zotero, Obsidian, DBLP, ArXiv |

### 1.3 四大工作流

| 工作流 | 入口 | 核心产出 |
|--------|------|----------|
| **IdeaFlow** | 论文/研究方向 | 经过辩论和审批的研究想法 |
| **ExperimentFlow** | 想法 | 实验方案 + 执行结果报告 |
| **ReviewFlow** | 论文/实验 | 多维度评分报告 |
| **WriteFlow** | 评审结果 | 论文初稿 |

### 1.4 系统特性

- **断点续跑**：每个步骤后自动保存检查点，支持 CRC32 校验
- **实时推送**：SSE 事件流实时推送工作流状态和日志
- **异步审批**：工作流可在指定节点暂停等待人工审批
- **多模型辩论**：支持跨模型辩论和五维评分
- **Token 预算**：80% 预警/95% 暂停两级预算控制

---

## 2. 项目架构

### 2.1 完整目录结构

```
D:\Projects\TUTOR\
├── tutor/                          # Python 主包
│   ├── __main__.py                 # 包入口
│   ├── api/                        # FastAPI Web 服务
│   │   ├── __init__.py
│   │   ├── main.py                 # 主应用，聚合所有路由
│   │   ├── health.py                # 健康检查
│   │   ├── prometheus.py            # Prometheus 指标
│   │   ├── models.py                # Pydantic 模型、响应格式
│   │   └── routes/                  # 路由模块
│   │       ├── __init__.py
│   │       ├── events.py            # SSE 事件路由
│   │       ├── projects.py           # 项目管理 API
│   │       ├── providers.py          # AI Provider 配置
│   │       ├── uploads.py            # 文件上传
│   │       └── users.py             # 用户管理
│   │
│   ├── cli/                        # CLI 命令行工具
│   │   ├── __init__.py             # Typer 应用入口
│   │   ├── api.py                   # API 服务命令
│   │   ├── backup.py                # 备份恢复
│   │   ├── config.py                # 配置管理
│   │   ├── experiment.py            # 实验命令
│   │   ├── health.py                # 健康检查
│   │   ├── idea.py                  # 想法生成命令
│   │   ├── migrate.py                # 数据库迁移
│   │   ├── review.py                # 评审命令
│   │   ├── ui.py                     # UI 相关
│   │   └── write.py                  # 写作命令
│   │
│   ├── config/                      # 配置管理
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   ├── providers.yaml            # Provider 配置
│   │   └── encrypt_api_keys.py       # API Key 加密
│   │
│   ├── core/                        # 核心业务逻辑
│   │   ├── auth/                    # 认证授权
│   │   │   ├── jwt.py               # JWT 令牌
│   │   │   ├── password.py           # 密码哈希
│   │   │   ├── security.py           # 安全工具
│   │   │   ├── session.py            # 会话管理
│   │   │   └── user.py              # 用户模型
│   │   │
│   │   ├── workflow/                # 工作流引擎
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # Workflow/Step/Context 基类
│   │   │   ├── idea.py              # IdeaFlow (70KB+)
│   │   │   ├── experiment.py        # ExperimentFlow
│   │   │   ├── review.py            # ReviewFlow
│   │   │   ├── write.py             # WriteFlow
│   │   │   ├── approval.py           # 审批步骤
│   │   │   ├── project_gate.py      # 项目门控
│   │   │   ├── debate_framework.py   # 辩论框架
│   │   │   ├── retry.py             # 重试策略
│   │   │   ├── paper_parser.py      # 论文解析
│   │   │   ├── figure.py             # 图表生成
│   │   │   ├── latex.py             # LaTeX 处理
│   │   │   └── steps/               # 工作流步骤
│   │   │       ├── __init__.py
│   │   │       ├── smart_input.py    # 智能输入 (560行)
│   │   │       ├── paper_loading.py  # 论文加载
│   │   │       └── zotero_literature.py # Zotero 文献
│   │   │
│   │   ├── model/                   # 模型网关 (24KB+)
│   │   │   └── __init__.py         # ModelGateway, ModelCallStats
│   │   │
│   │   ├── providers/              # LLM Provider 实现
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # ModelProvider 基类
│   │   │   ├── router.py           # Provider 路由器
│   │   │   ├── openai.py           # OpenAI
│   │   │   ├── deepseek.py         # DeepSeek
│   │   │   ├── anthropic.py        # Anthropic (Claude)
│   │   │   ├── azure.py            # Azure OpenAI
│   │   │   ├── local.py            # 本地 Ollama
│   │   │   └── minimax.py          # MiniMax
│   │   │
│   │   ├── debate/                 # 辩论系统
│   │   │   ├── __init__.py
│   │   │   ├── cross_model_debater.py # 跨模型辩论
│   │   │   └── model_config.py     # 模型配置
│   │   │
│   │   ├── review/                 # 评审系统
│   │   │   ├── __init__.py
│   │   │   ├── auto_reviewer.py    # 自动评审
│   │   │   └── cross_model_reviewer.py # 跨模型评审
│   │   │
│   │   ├── multiagent/            # 多智能体
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # 基础类
│   │   │   ├── message_bus.py      # 消息总线
│   │   │   └── orchestrator.py    # 编排器
│   │   │
│   │   ├── project/               # 项目管理
│   │   │   ├── __init__.py
│   │   │   ├── manager.py         # 项目管理器
│   │   │   ├── models.py          # 项目模型
│   │   │   └── storage.py         # 项目存储
│   │   │
│   │   ├── scheduling/            # 调度管理
│   │   │   ├── __init__.py
│   │   │   ├── idea_scheduler.py  # 想法调度器
│   │   │   └── experiment_manager.py # 实验管理器
│   │   │
│   │   ├── external/             # 外部服务集成
│   │   │   ├── __init__.py
│   │   │   ├── zotero.py         # Zotero API 客户端
│   │   │   ├── obsidian.py       # Obsidian Vault 同步
│   │   │   └── dblp.py           # DBLP 引用验证
│   │   │
│   │   ├── monitor/             # 资源监控
│   │   │   ├── __init__.py
│   │   │   ├── token_budget.py  # Token 预算
│   │   │   ├── cost_tracker.py   # 成本追踪
│   │   │   ├── resource_monitor.py # 资源监控
│   │   │   ├── quota.py          # 配额
│   │   │   ├── quotas.py         # 配额配置
│   │   │   ├── collector.py      # 指标采集
│   │   │   └── monitor.py        # 监控主模块
│   │   │
│   │   ├── storage/             # 存储层
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # StorageBackend 抽象
│   │   │   ├── manager.py       # StorageManager
│   │   │   ├── sqlite_backend.py # SQLite 后端
│   │   │   ├── file_backend.py  # 文件系统后端
│   │   │   ├── checkpoint_validation.py # 检查点验证
│   │   │   └── workflow_runs.py # 工作流运行存储
│   │   │
│   │   ├── deployment/          # 部署管理
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── exceptions.py
│   │   │   ├── remote_executor.py
│   │   │   └── ssh_client.py
│   │   │
│   │   ├── logging_config.py    # 日志配置
│   │   ├── secure_config.py    # 安全配置
│   │   └── migrate.py          # 数据迁移
│   │
│   └── core.egg-info/         # 包元数据
│
├── web/                        # React 前端
│   ├── src/
│   │   ├── App.jsx             # 主应用
│   │   ├── api.js              # API 调用封装
│   │   ├── index.css           # 全局样式
│   │   ├── setupTests.js       # 测试配置
│   │   └── pages/              # 页面组件
│   │       ├── Dashboard.jsx   # 仪表盘
│   │       ├── Workflows.jsx   # 工作流列表
│   │       ├── NewWorkflow.jsx  # 新建工作流
│   │       ├── WorkflowDetail.jsx # 工作流详情
│   │       ├── Approvals.jsx    # 审批管理
│   │       └── Settings.jsx     # 设置
│   ├── build/                  # 构建输出
│   ├── vite.config.js          # Vite 配置
│   ├── package.json
│   ├── tsconfig.json
│   ├── playwright.config.js     # E2E 测试配置
│   ├── tests/                  # E2E 测试
│   │   └── e2e/
│   │       └── app.spec.js
│   └── index.html
│
├── config/                     # 配置文件
│   ├── providers.yaml           # Provider 配置
│   ├── providers.yaml.example   # 配置模板
│   └── encrypt_api_keys.py
│
├── tests/                      # Python 测试
│   ├── conftest.py            # Pytest fixtures
│   ├── unit/                  # 单元测试
│   │   ├── test_model_gateway.py
│   │   └── test_workflow_engine.py
│   └── integration/            # 集成测试
│       └── test_api.py
│
├── docs/                      # 文档
│   └── research_workflow_design.md # 本文档
│
├── data/                      # 数据目录
├── test_results/              # 测试结果
├── scheduler_results/         # 调度结果
├── custom_results/            # 自定义结果
│
├── pyproject.toml             # 项目配置
├── pytest.ini                 # Pytest 配置
├── Makefile                   # 构建脚本
├── README.md                  # 项目说明
├── docker-compose.dev.yml     # Docker 开发环境
└── tutor.db                   # SQLite 数据库
```

### 2.2 关键依赖关系

```
API Routes (main.py)
    ↓
WorkflowEngine → Workflow → WorkflowStep
    ↓
WorkflowContext (状态管理, 检查点, 决策日志)
    ↓
ModelGateway (统一模型调用)
    ↓
ModelRouter → ModelProvider (OpenAI/DeepSeek/Anthropic/Azure/Local/MiniMax)

StorageManager
    ↓
SQLiteBackend + FileBackend
    ↓
WorkflowRunsStorage / CheckpointValidation
```

### 2.3 前端代理配置 (vite.config.js)

```javascript
server: {
  port: 3000,
  proxy: {
    '/api': { target: 'http://localhost:8092', changeOrigin: true },
    '/health': { target: 'http://localhost:8092', changeOrigin: true },
    '/run': { target: 'http://localhost:8092', changeOrigin: true },
    '/runs': { target: 'http://localhost:8092', changeOrigin: true },
    '/approvals': { target: 'http://localhost:8092', changeOrigin: true },
    '/metrics': { target: 'http://localhost:8092', changeOrigin: true },
    '/stats': { target: 'http://localhost:8092', changeOrigin: true },
    '/events': { target: 'http://localhost:8092', changeOrigin: true },
  }
}
```

---

## 3. 核心数据模型

### 3.1 工作流状态 (WorkflowStatus)

```python
class WorkflowStatus(str, Enum):
    PENDING = "pending"      # 等待执行
    RUNNING = "running"       # 执行中
    PAUSED = "paused"        # 暂停等待审批
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消
```

### 3.2 检查点数据 (CheckpointData)

```python
@dataclass
class CheckpointData:
    workflow_id: str
    workflow_type: str
    status: WorkflowStatus
    current_step: int          # 当前步骤索引
    total_steps: int
    step_name: str
    input_data: Dict[str, Any]   # 步骤输入
    output_data: Dict[str, Any]   # 步骤输出
    error: Optional[str]
    created_at: str
    updated_at: str
    _crc32: Optional[int]        # CRC32 校验

    def to_dict(self) -> Dict
    def from_dict(data: Dict) -> CheckpointData
    def save(path: Path) -> None
    def load(path: Path) -> CheckpointData
```

**检查点机制**：
- 每个步骤执行后自动保存
- 文件名格式：`step_{step_index:04d}_{timestamp}.json`
- 支持 CRC32 校验和自动修复
- 恢复时从最新有效检查点继续

### 3.3 工作流结果 (WorkflowResult)

```python
@dataclass
class WorkflowResult:
    workflow_id: str
    status: WorkflowStatus
    output: Dict[str, Any]       # 工作流输出
    error: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    decision_log: List[Dict]    # Orchestrator 决策日志
```

### 3.4 OrchestratorDecision (决策日志)

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

### 3.5 API 统一响应格式 (models.py)

```python
@dataclass
class ApiResponse:
    success: bool
    data: Optional[Any] = None
    error: Optional[Dict[str, str]] = None
    meta: Optional[Dict[str, Any]] = None

def success_response(data=None, meta=None) -> Dict:
    """构造成功响应 {"success": True, "data": ..., "meta": ...}"""

def error_response(code: str, message: str) -> Dict:
    """构造错误响应 {"success": False, "error": {"code": ..., "message": ...}}"""

def paginated_response(items, total, limit, offset) -> Dict:
    """构造分页响应"""
```

### 3.6 RunRequest / RunResponse

```python
class RunRequest(BaseModel):
    workflow_type: str = Field(..., description="idea/experiment/review/write")
    params: Dict[str, Any] = Field(default_factory=dict)
    config: Optional[Dict[str, Any]] = Field(default=None)

class RunResponse(BaseModel):
    run_id: str
    status: str
    workflow_type: str
    message: str

class RunStatusResponse(BaseModel):
    run_id: str
    workflow_type: str
    status: str
    params: Dict
    config: Dict
    started_at: str
    completed_at: Optional[str]
    result: Dict
    error: Optional[str]
    tags: List[str]
```

---

## 4. 工作流引擎

### 4.1 核心架构

```
Workflow (抽象基类)
├── build_steps() → List[WorkflowStep]  # 子类实现
├── initialize() → 构建步骤 + 检查点恢复
├── run() → WorkflowResult               # 执行流程
└── context: WorkflowContext              # 执行上下文

WorkflowStep (抽象基类)
├── name: str
├── description: str
├── execute(context) → Dict              # 步骤逻辑
├── validate(context) → List[str]        # 前置条件验证
└── rollback(context)                     # 可选回滚

WorkflowContext
├── workflow_id: str
├── config: Dict
├── storage_path: Path
├── model_gateway: ModelGateway
├── broadcaster: EventBroadcaster
├── _state: Dict                         # 内存状态
├── _current_step: int                   # 当前步骤索引
├── _decision_log: List                  # 决策日志
├── _token_tracker: WorkflowTokenTracker
├── save_checkpoint() → CheckpointData
├── get_state(key, default)
├── set_state(key, value)
├── get_all_state() → Dict
└── log_decision(...) → OrchestratorDecision

WorkflowEngine
├── storage_path: Path
├── model_gateway: ModelGateway
├── broadcaster: EventBroadcaster
├── active_workflows: Dict[str, Workflow]
├── create_workflow(workflow_class, workflow_id, config) → Workflow
├── get_workflow(workflow_id) → Optional[Workflow]
├── run_workflow(workflow_id) → WorkflowResult
├── resume_workflow(workflow_id) → WorkflowResult
├── is_workflow_paused(workflow_id) → bool
└── cancel_workflow(workflow_id) → bool
```

### 4.2 执行流程 (run 方法)

```python
def run(self) -> WorkflowResult:
    self._start_monitoring()

    while self._current_step_index < len(self.steps):
        step = self.steps[self._current_step_index]

        # 更新 context 中的步骤索引
        self.context._current_step = self._current_step_index

        # 前置条件验证
        errors = step.validate(self.context)
        if errors:
            raise ValueError(f"Step validation failed: {', '.join(errors)}")

        # 执行步骤（带重试）
        step_output = self._retry_manager.execute_with_retry(
            step, self.context, self.retry_policy, self.failure_strategy
        )

        # 保存检查点
        self.context.save_checkpoint(
            step=self._current_step_index,
            step_name=step.name,
            input_data=self.context.get_all_state(),
            output_data=step_output,
        )

        self._current_step_index += 1

    return WorkflowResult(..., decision_log=self.context.get_decision_log())
```

### 4.3 FailureStrategy 失败策略

```python
class FailureStrategy(Enum):
    ROLLBACK = "rollback"   # 回滚并停止
    STOP = "stop"          # 直接停止
    CONTINUE = "continue"  # 记录错误，继续执行
    PAUSE = "pause"        # 暂停等待人工决策
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
SmartInputStep → AutoArxivSearchStep → PaperLoadingStep →
PaperValidationStep → ZoteroLiteratureStep → LiteratureAnalysisStep →
IdeaDebateStep → IdeaApprovalGateStep → IdeaEvaluationStep →
FinalProposalStep → ProjectGateStep
```

**详细步骤**：

| 步骤 | 类名 | 职责 | 输出状态键 |
|------|------|------|----------|
| 1 | SmartInputStep | 解析用户输入，识别关键词/arXiv URL/本地文件 | paper_sources, research_keywords, auto_search_query, smart_input_processed |
| 2 | AutoArxivSearchStep | 根据关键词自动搜索 ArXiv 补充文献 | auto_search_results |
| 3 | PaperLoadingStep | 加载 PDF 或抓取 ArXiv 论文 | papers, load_errors, all_sources |
| 4 | PaperValidationStep | 验证论文质量（长度、摘要） | validated_papers, validation_errors |
| 5 | ZoteroLiteratureStep | 补充 Zotero 文献（可选） | zotero_papers, research_keywords |
| 6 | LiteratureAnalysisStep | AI 分析提取知识图谱 | literature_analysis, concepts, analysis_summary |
| 7 | IdeaDebateStep | 多角色辩论生成想法 | debate_ideas, final_ideas, debate_quality, debate_visualization |
| 8 | IdeaApprovalGateStep | **[介入点#1]** 辩论后审批 | approval_id, approval_status |
| 9 | IdeaEvaluationStep | 评估想法可行性和创新性 | evaluated_ideas, recommended_idea, weakest_dimension, routing_decision |
| 10 | FinalProposalStep | 生成研究提案文档 | final_proposal |
| 11 | ProjectGateStep | **[最终审批]** 项目完成前审批 | project_approval_id |

**SmartInputStep 详解**：

```python
class SmartInputStep(WorkflowStep):
    """智能输入处理步骤

    支持识别的输入格式：
    - arXiv URL: https://arxiv.org/abs/2301.00001
    - arXiv ID: 2301.00001
    - 本地文件路径: /path/to/paper.pdf, C:\Papers\xxx.pdf
    - 算法缩写: LLM, ViT, GAN, BERT, GPT
    - 领域关键词: NLP, CV, RL, ML
    - 自然语言描述: 基于Transformer的图像分割
    """

    # 识别的领域关键词 (35个)
    DOMAIN_KEYWORDS = {
        "cv": ["computer vision", ...],
        "nlp": ["natural language processing", ...],
        "rl": ["reinforcement learning", ...],
        # ... 中文关键词: 蒸馏, 剪枝, 量化, 联邦, 对抗, 优化
    }

    # 识别的算法关键词 (70+个)
    ALGORITHM_KEYWORDS = {
        "resnet": "ResNet: Deep Residual Learning...",
        "vit": "An Image is Worth 16x16 Words...",
        "bert": "BERT: Pre-training of Deep Bidirectional...",
        # ...
    }
```

**AutoArxivSearchStep 详解**：

```python
class AutoArxivSearchStep(WorkflowStep):
    """自动 ArXiv 文献搜索

    当用户只提供关键词时，自动搜索并补充相关文献。
    """

    def _search_arxiv(self, query: str) -> List[Dict[str, Any]]:
        """使用 ArXiv OpenSearch API 搜索"""
        # API: http://export.arxiv.org/api/query
        # 参数: search_query, start, max_results, sortBy, sortOrder
        # 返回: {title, abstract, url, arxiv_url, arxiv_id}
```

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

### 5.3 ReviewFlow (评审)

**文件**：`tutor/core/workflow/review.py`

**支持三种评审模式**：

| 模式 | 说明 |
|------|------|
| `single` | 单一模型评审 (MVP) |
| `cross_model` | 不同模型对抗式评审 |
| `auto_loop` | 迭代式改进直到收敛 |

**评审维度**：

| 维度 | 权重 |
|------|------|
| 创新性 (Novelty) | 30% |
| 方法严谨性 (Rigor) | 25% |
| 可行性 (Feasibility) | 20% |
| 领域贡献 (Contribution) | 15% |
| 表达完整性 (Clarity) | 10% |

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

### 6.5 WorkflowContext 状态管理

```python
class WorkflowContext:
    def get_state(self, key: str, default: Any = None) -> Any:
        """获取状态值"""
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """设置状态值"""
        self._state[key] = value

    def get_all_state(self) -> Dict[str, Any]:
        """获取所有状态"""
        return self._state.copy()

    def log_decision(self, step_name, decision_type, anomaly, decision, impact, success):
        """记录 Orchestrator 自主决策"""
        orch_decision = OrchestratorDecision(...)
        self._decision_log.append(orch_decision)
```

---

## 7. 辩论框架

### 7.1 多维辩论 (MultiDimensionalDebate)

**文件**：`tutor/core/workflow/debate_framework.py`

**五维评分**：

```python
class DimensionType(Enum):
    METHODOLOGY = "methodology"           # 方法论有效性
    DATA_SUPPORT = "data_support"         # 数据支持度
    GENERALIZABILITY = "generalizability" # 结论普适性
    INNOVATION = "innovation"            # 创新性
    REPRODUCIBILITY = "reproducibility"   # 可复现性
```

### 7.2 跨模型辩论 (CrossModelDebater)

**文件**：`tutor/core/debate/cross_model_debater.py`

**角色配置**：

| 角色 | 描述 |
|------|------|
| Innovator | 激进派，提出新颖想法 |
| Skeptic | 保守派，质疑可行性 |
| Pragmatist | 实用派，评估可行性 |
| Expert | 领域专家，提供背景知识 |

**配置示例**：
```yaml
cross_model_config:
  innovator: ["claude-sonnet-4"]
  skeptic: ["gpt-4o"]
  pragmatist: ["gemini-2-5-pro"]
```

---

## 8. 审批系统

### 8.1 审批状态

```python
class ApprovalStatus(str, Enum):
    PENDING = "pending"    # 等待审批
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已拒绝
    TIMEOUT = "timeout"    # 超时
    CANCELLED = "cancelled" # 已取消
```

### 8.2 审批管理器

```python
class ApprovalManager:
    _requests: Dict[str, ApprovalRequest]

    def create_request(...) -> ApprovalRequest
    def approve(approval_id, comment) -> bool
    def reject(approval_id, comment) -> bool
    def get_request(approval_id) -> Optional[ApprovalRequest]
    def list_pending(run_id) -> List[ApprovalRequest]
```

### 8.3 门控步骤

**IdeaApprovalGateStep**：辩论结束后的想法审批（介入点 #1）

```python
class IdeaApprovalGateStep(WorkflowStep):
    def execute(self, context):
        # 1. 从上下文获取辩论结果
        debate_ideas = context.get_state("debate_ideas", [])
        debate_quality = context.get_state("debate_quality", "unknown")
        final_ideas = context.get_state("final_ideas", [])

        # 2. 创建审批请求 ID
        approval_id = f"{context.workflow_id}_idea_approval"

        # 3. 检查是否已有审批结果
        manager = get_approval_manager()
        existing = manager.get_request(approval_id)

        if existing and existing.status.value in ("approved", "rejected"):
            return {"approval_status": existing.status.value, ...}

        # 4. 创建新审批请求
        manager.create_request(
            approval_id=approval_id,
            run_id=context.workflow_id,
            title="审批辩论产生的想法",
            description=f"辩论产生 {len(debate_ideas)} 个想法",
            context_data=approval_data,
        )

        # 5. 保存检查点
        context.save_checkpoint(...)

        # 6. 抛出暂停异常
        raise WorkflowPauseError(f"waiting for approval: {approval_id}")
```

**ProjectGateStep**：工作流结束前的最终审批

### 8.4 审批通过后恢复工作流

```python
@app.post("/approvals/{approval_id}/approve")
async def approve_request(approval_id: str, comment: str = ""):
    success = am.approve(approval_id, comment=comment or "")
    request = am.get_request(approval_id)

    # 触发工作流恢复
    if request and request.run_id:
        run = run_storage.get_run(request.run_id)
        if run and run.get("status") == "paused":
            from tutor.core.workflow.engine import WorkflowEngine
            engine = WorkflowEngine()
            asyncio.create_task(_resume_workflow_async(request.run_id, engine, None, None))

    return request.to_dict()
```

---

## 9. 监控与预算

### 9.1 资源监控

```python
class ResourceMonitor:
    def collect(self) -> ResourceSnapshot:
        # CPU, Memory, Disk, GPU

class QuotaManager:
    thresholds = {
        CPU: 90.0,      # %
        Memory: 80.0,
        Disk: 80.0,
        GPU: 80.0,
    }

    def check(self, snapshot) -> List[QuotaWarning]
```

### 9.2 配额管理

| 配额类型 | 阈值 | 动作 |
|----------|------|------|
| CPU | 90% | 警告 |
| Memory | 80% | 警告 |
| Disk | 80% | 警告 |
| GPU | 80% | 警告 |

### 9.3 成本追踪

```python
class CostTracker:
    def record(self, entry: CostEntry):
        # 记录到 SQLite

class CostEntry:
    timestamp: datetime
    run_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
```

---

## 10. API 路由

### 10.1 主应用路由 (main.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（兼容） |
| GET | `/health/live` | 存活探针 |
| GET | `/health/ready` | 就绪探针 |
| GET | `/metrics` | Prometheus 指标 |
| POST | `/run` | 启动工作流 |
| GET | `/runs/{run_id}` | 获取运行状态 |
| GET | `/runs` | 列出所有运行（分页） |
| GET | `/stats` | 获取工作流统计 |
| GET | `/runs/list/archived` | 列出已归档运行 |
| GET | `/runs/list/favorites` | 列出收藏运行 |
| DELETE | `/runs/{run_id}` | 删除运行 |
| POST | `/runs/{run_id}/retry` | 重试失败工作流 |
| POST | `/runs/batch-delete` | 批量删除 |
| DELETE | `/runs/cleanup` | 清理旧运行 |
| PATCH | `/runs/{run_id}/tags` | 更新标签（归档/收藏） |
| POST | `/runs/{run_id}/cancel` | 取消运行 |
| GET | `/events/{run_id}` | SSE 事件流 |
| GET | `/approvals` | 列出审批请求 |
| GET | `/approvals/pending` | 列出待审批请求 |
| GET | `/approvals/{approval_id}` | 获取审批详情 |
| POST | `/approvals/{approval_id}/approve` | 批准 |
| POST | `/approvals/{approval_id}/reject` | 拒绝 |
| POST | `/approvals/{approval_id}/cancel` | 取消 |

### 10.2 认证路由 (`/api/v1/auth`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/register` | 用户注册 |
| POST | `/login` | 用户登录 |
| POST | `/logout` | 用户登出 |
| POST | `/refresh` | 刷新 Token |

### 10.3 用户路由 (`/api/v1/users`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/me` | 获取当前用户信息 |
| PUT | `/me` | 更新当前用户信息 |

### 10.4 Provider 路由 (`/api/v1/providers`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 列出所有 Provider |
| GET | `/{provider_name}` | 获取 Provider 配置 |
| PUT | `/{provider_name}` | 更新 Provider 配置 |
| POST | `/{provider_name}/validate` | 验证连接 |
| GET | `/supported/models` | 列出支持的模型 |

**支持的 Provider**：openai, deepseek, anthropic, azure, local, minimax

### 10.5 项目路由 (`/api/v1/projects`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 创建项目 |
| GET | `/` | 列出所有项目 |
| GET | `/{project_id}` | 获取项目详情 |
| POST | `/{project_id}/approve` | 批准项目 |
| POST | `/{project_id}/reject` | 拒绝项目 |
| POST | `/{project_id}/iterate` | 迭代项目 |
| POST | `/{project_id}/select-idea` | 选择想法 |
| DELETE | `/{project_id}` | 删除项目 |

### 10.6 上传路由 (`/api/v1/uploads`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 上传单个文件 |
| POST | `/multiple` | 批量上传 |
| GET | `/` | 列出已上传文件 |
| DELETE | `/{file_id}` | 删除文件 |

**允许的扩展名**：.pdf, .txt, .md, .tex, .docx

---

## 11. 前端集成

### 11.1 页面结构

```
Dashboard        - 工作台总览（统计、最近工作流）
Workflows        - 工作流列表（筛选、批量操作、清理）
NewWorkflow      - 创建新工作流（独立/继续项目模式）
WorkflowDetail   - 工作流详情（SSE 日志、步骤进度、重试）
Approvals        - 审批管理（待审批、已审批列表）
Settings         - 系统设置（Provider API Key 配置）
```

### 11.2 API 调用封装 (api.js)

```javascript
const API_BASE = '';  // 相对路径，Vite 代理到后端

export const api = {
  // 健康检查
  health(),

  // 工作流
  startRun(workflowType, params, config),
  getRunStatus(runId),
  listRuns(status, workflowType, page, limit),
  deleteRun(runId),
  batchDeleteRuns(runIds),
  cleanupOldRuns(status, olderThanDays, dryRun),
  retryRun(runId),
  updateRunTags(runId, tags),

  // SSE 事件
  createEventSource(runId, onMessage, onError),

  // 文件上传
  uploadFile(file),
  uploadFiles(files),
  listUploadedFiles(),
  deleteUploadedFile(fileId),

  // 审批
  listApprovals(runId, status),
  approveRequest(approvalId, comment),
  rejectRequest(approvalId, comment),

  // 系统
  getMetrics(),
  getStats(),
}
```

### 11.3 前端状态管理

- React Context/Hooks 管理全局状态
- SSE EventSource 实时接收后端推送
- 轮询机制作为 SSE 的降级方案

### 11.4 SSE 事件类型

```javascript
// 工作流事件
{ type: "started", run_id, workflow_type }
{ type: "step_completed", run_id, step_name, status }
{ type: "log", run_id, level, message, timestamp }
{ type: "complete", run_id, status, result }

// 审批事件
{ type: "approval_created", approval_id, run_id }
{ type: "approval_resolved", approval_id, status }
```

---

## 12. 外部服务集成

### 12.1 Zotero 文献管理

**文件**：`tutor/core/external/zotero.py`

```python
class ZoteroClient:
    BASE_URL = "https://api.zotero.org"

    def __init__(self, api_key=None, library_id=None, library_type="user"):
        """初始化客户端"""

    @property
    def is_configured(self) -> bool:
        """检查 API 是否已配置"""

    def search_items(self, query, item_type=None, limit=25) -> List[Dict]:
        """搜索文献（标题、作者、标签）"""

    def get_item(self, item_key) -> Dict:
        """获取单个文献详情"""

    def get_collections(self) -> List[Dict]:
        """获取所有集合"""

    def get_collection_items(self, collection_key, limit=25) -> List[Dict]:
        """获取集合中的文献"""

    def export_bibtex(self, item_key) -> str:
        """导出单条文献为 BibTeX 格式"""

    def export_multiple_bibtex(self, item_keys) -> str:
        """批量导出 BibTeX"""

    def search_and_format(self, query, limit=5) -> str:
        """搜索并格式化结果（便捷方法）"""
```

### 12.2 Obsidian 笔记同步

**文件**：`tutor/core/external/obsidian.py`

```python
class ObsidianSync:
    """Obsidian Vault 同步工具"""

    def __init__(self, vault_path: str, default_folder: str = "TUTOR"):
        self.vault_path = Path(vault_path)
        self.default_folder = default_folder

    def initialize(self) -> None:
        """创建必要的文件夹结构:
        TUTOR/Research, Decisions, Experiments, Reviews
        """

    def sync_note(self, title, content, folder=None, tags=None, ...):
        """同步笔记到 Obsidian vault（自动添加 YAML frontmatter）"""

    def sync_workflow_result(self, workflow_type, run_id, result_summary, tags=None):
        """同步工作流运行结果到 TUTOR/Experiments"""

    def sync_decision(self, adr_id, title, context, decision, consequences, tags=None):
        """同步架构决策记录(ADR)到 TUTOR/Decisions"""

    def list_notes(self, folder=None, tag=None) -> List[Dict]:
        """列出 vault 中的笔记"""
```

### 12.3 DBLP 引用验证

**文件**：`tutor/core/external/dblp.py`

```python
@dataclass
class ReferenceMatch:
    input_title: str
    found: bool
    confidence: float  # 0.0 ~ 1.0
    matched_title: Optional[str] = None
    matched_authors: Optional[List[str]] = None
    matched_year: Optional[int] = None
    matched_venue: Optional[str] = None
    citation_count: Optional[int] = None
    sources: List[str] = field(default_factory=list)

    @property
    def is_verified(self) -> bool:
        return self.found and self.confidence >= 0.7

class ReferenceVerifier:
    """多源引用验证器 (Semantic Scholar + arXiv)"""

    SEMANTIC_SCHOLAR_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
    ARXIV_API = "https://export.arxiv.org/api/query"

    def verify_single(self, title, authors=None, year=None) -> ReferenceMatch:
        """验证单条引用"""

    def verify_batch(self, references, concurrency=1) -> BatchVerifyResult:
        """批量验证引用（顺序执行，避免限流）"""

    @staticmethod
    def _title_similarity(a: str, b: str) -> float:
        """最长公共子序列相似度 (LCS)"""

    @staticmethod
    def _author_overlap(input_authors, matched_authors) -> float:
        """作者重叠度（基于姓氏匹配）"""
```

---

## 13. CLI 命令行工具

### 13.1 主命令入口

```bash
tutor --help
tutor version
tutor status
```

### 13.2 命令组

#### tutor idea - 研究想法生成

```bash
tutor idea generate <input>      # 生成研究想法（完整工作流）
tutor idea list                  # 列出所有已生成的 idea
tutor idea show <idea_id>        # 显示单个 idea 的详细信息
tutor idea schedule <topics_file> # 批量调度多个 IdeaFlow 工作流
```

#### tutor experiment - 实验执行

```bash
tutor experiment run <research_question>  # 运行完整实验流程
tutor experiment list                     # 列出所有实验记录
tutor experiment show <experiment_id>   # 显示实验详细信息
```

#### tutor review - 论文审核

```bash
tutor review review <draft_path>   # 执行论文审核
```

#### tutor write - 论文撰写

```bash
tutor write start <idea_source>   # 开始论文撰写
tutor write polish <draft_path>   # 对论文草稿进行语言润色
tutor write list                  # 列出所有已生成的论文草稿
```

#### tutor api - Web API 服务器

```bash
tutor api serve                   # 启动 TUTOR Web API 服务器
tutor api openapi                # 生成 OpenAPI 规范 (JSON)
```

#### tutor health - 健康检查

```bash
tutor health check              # 执行健康检查
tutor health metrics            # 显示系统指标（JSON 格式）
tutor health vacuum             # 执行 SQLite VACUUM
```

#### tutor backup - 备份与恢复

```bash
tutor backup create              # 创建完整备份
tutor backup restore <backup_file> # 恢复备份
tutor backup list_backups         # 列出所有可用备份
```

#### tutor migrate - 数据库迁移

```bash
tutor migrate upgrade             # 升级数据库到指定版本
tutor migrate downgrade           # 降级数据库
tutor migrate history            # 显示迁移历史
tutor migrate current            # 显示当前数据库版本
tutor migrate init               # 初始化迁移环境
tutor migrate export             # 导出数据库（SQL 格式）
tutor migrate import <backup_file> # 从 SQL 文件导入数据库
```

---

## 14. 配置管理

### 14.1 项目依赖 (pyproject.toml)

```toml
[project]
name = "tutor"
version = "0.1.0"
requires-python = ">=3.9"

dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "sqlalchemy>=2.0.0",
    "pydantic>=2.0.0",
    "redis>=5.0.0",
    "celery>=5.3.0",
    "structlog>=23.0.0",
    "httpx>=0.25.0",
    "python-multipart>=0.0.6",
    "websockets>=12.0",
    "prometheus-client>=0.19.0",
    "psycopg2-binary>=2.9.0",
    "pyyaml>=6.0",
    "click>=8.1.0",
    "typer[all]>=0.9.0",
    "rich>=13.0.0",
]
```

### 14.2 Provider 配置 (providers.yaml)

支持以下 AI Provider：

| Provider | 配置项 |
|----------|--------|
| OpenAI | openai_api_base, openai_api_key |
| DeepSeek | deepseek_api_base, deepseek_api_key |
| Anthropic | anthropic_api_base, anthropic_api_key |
| Azure | azure_api_base, azure_api_key, azure_deployment_name |
| Local | local_api_base (Ollama) |
| MiniMax | minimax_api_base, minimax_api_key |

### 14. CLI 入口点

```toml
[project.scripts]
tutor = "tutor.cli:app"
tutor-gateway = "tutor.core.gateway:run"
```

---

## 15. 测试体系

### 15.1 测试结构

```
tests/
├── conftest.py                  # Pytest fixtures
├── unit/
│   ├── test_model_gateway.py   # ModelGateway 单元测试
│   └── test_workflow_engine.py # 工作流引擎单元测试
└── integration/
    └── test_api.py             # API 集成测试
```

### 15.2 前端 E2E 测试

```
web/
├── playwright.config.js
└── tests/
    └── e2e/
        └── app.spec.js
```

---

## 16. AI 赋能开发经验

### 16.1 迭代式开发策略

1. **先有骨架**：先实现工作流引擎和基本步骤
2. **渐进增强**：逐步添加辩论、评估、审批等复杂功能
3. **每步可运行**：每个功能点完成后立即测试

### 16.2 检查点设计的重要性

**问题**：长工作流执行中一旦失败，从头开始代价高昂。

**解决方案**：
- 每个步骤后自动保存检查点
- 支持 CRC32 校验防止数据损坏
- 恢复时自动定位最新有效检查点

### 16.3 状态与执行分离

```python
# WorkflowContext 负责状态存储
context.get_state("key")
context.set_state("key", value)

# 步骤只返回输出字典
return {"papers": [...], "errors": [...]}
```

### 16.4 可选功能的优雅降级

```python
class ZoteroLiteratureStep(WorkflowStep):
    def validate(self, context):
        client = self._get_client()
        if not client:
            return ["Zotero not configured"]
        return []

    def execute(self, context):
        if not self._get_client():
            return {"skipped": True, "reason": "Zotero not configured"}
        # 正常逻辑
```

### 16.5 多模型灵活切换

```python
class ModelGateway:
    def chat(self, role, messages, temperature, max_tokens):
        # 根据 role 解析实际模型
        # 统一错误处理和重试
        return self._call_api(model_id, messages, ...)
```

### 16.6 决策日志的透明度

```python
class WorkflowContext:
    def log_decision(self, step_name, decision_type, anomaly, decision, impact):
        orch_decision = OrchestratorDecision(...)
        self._decision_log.append(orch_decision)
```

---

## 17. 评估与改进建议

### 17.1 已实现的核心功能

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
| SmartInputStep | ✅ | 关键词/arXiv/文件识别 |
| AutoArxivSearchStep | ✅ | ArXiv API 搜索 |
| Zotero 集成 | ✅ | 文献搜索导出 |
| Obsidian 同步 | ✅ | 笔记双向同步 |
| DBLP 引用验证 | ✅ | 多源验证 |
| JWT 认证 | ✅ | 用户认证 |
| 文件上传 | ✅ | PDF/TXT/MD/TEX |

### 17.2 已知限制

| 限制 | 说明 | 建议改进 |
|------|------|----------|
| ArXiv 网络 | 国内可能超时 | 增加重试和本地缓存 |
| Token 计数 | 使用字符估算 | 从 API 响应获取实际 usage |
| 单机存储 | 检查点存本地文件 | V2 考虑分布式存储 |
| 中文支持 | 部分模块中文关键词有限 | 扩展 DOMAIN_KEYWORDS |

### 17.3 建议的优先级改进

**P0 - 必须修复**：
1. ArXiv 网络超时处理（增加重试）
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
| `tutor/core/workflow/base.py` | Workflow, WorkflowContext, WorkflowStep, WorkflowEngine |
| `tutor/core/workflow/idea.py` | IdeaFlow, IdeaDebateStep, IdeaEvaluationStep, IdeaApprovalGateStep |
| `tutor/core/workflow/steps/smart_input.py` | SmartInputStep, AutoArxivSearchStep |
| `tutor/core/workflow/experiment.py` | ExperimentFlow, EnvironmentCheckStep |
| `tutor/core/workflow/review.py` | ReviewFlow |
| `tutor/core/workflow/write.py` | WriteFlow |
| `tutor/core/workflow/approval.py` | ApprovalManager |
| `tutor/core/workflow/debate_framework.py` | MultiDimensionalDebate |
| `tutor/core/debate/cross_model_debater.py` | CrossModelDebater |
| `tutor/core/model/__init__.py` | ModelGateway |
| `tutor/core/monitor/token_budget.py` | TokenBudget, WorkflowTokenTracker |
| `tutor/core/storage/workflow_runs.py` | RunStorage |
| `tutor/api/main.py` | 所有 API 端点 |
| `tutor/api/routes/projects.py` | 项目管理 API |
| `tutor/core/external/zotero.py` | ZoteroClient |
| `tutor/core/external/obsidian.py` | ObsidianSync |
| `tutor/core/external/dblp.py` | ReferenceVerifier |

---

*本文档版本 v2.1，完整记录 TUTOR 系统架构与设计决策。*
