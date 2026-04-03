# TUTOR 架构设计文档

## 1. 整体架构

### 1.1 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                       Interface Layer                       │
│  ┌─────────────┐               ┌─────────────┐            │
│  │     CLI     │               │     REST    │ (MVP延后)  │
│  │  (Typer)    │               │   (FastAPI) │            │
│  └─────────────┘               └─────────────┘            │
├─────────────────────────────────────────────────────────────┤
│                    Application Core                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Workflow Engine                         │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │  │
│  │  │ IdeaFlow    │  │ ExpFlow     │  │ ReviewFlow  │ │  │
│  │  │ (workflow1) │  │ (workflow2) │  │ (workflow3) │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘ │  │
│  │  ┌─────────────┐                                      │  │
│  │  │ WriteFlow   │ (workflow4)                          │  │
│  │  └─────────────┘                                      │  │
│  └──────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                     Service Layer                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │   Model     │  │   Storage   │  │   Utils     │       │
│  │  Gateway    │  │  Manager    │  │             │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 设计原则
- **单一职责**：每个模块只做一件事
- **依赖倒置**：高层模块不依赖低层细节
- **配置驱动**：行为通过配置文件控制
- **本地优先**：所有数据本地存储，无强制云依赖

---

## 2. 核心模块设计

### 2.1 Workflow Engine（工作流引擎）

**职责**：
- 定义工作流的步骤编排
- 管理执行状态和中间结果
- 处理超时、重试和错误恢复

**设计**：
```python
class WorkflowEngine:
    def __init__(self, config: dict, model_gateway, storage_manager):
        self.config = config
        self.model = model_gateway
        self.storage = storage_manager
        
    def run(self, workflow_name: str, inputs: dict) -> WorkflowResult:
        """执行指定工作流"""
        workflow = self._load_workflow(workflow_name)
        state = WorkflowState(workflow.steps)
        
        for step in workflow.steps:
            try:
                result = self._execute_step(step, state, inputs)
                state.update(step, result)
                self.storage.save_checkpoint(workflow_name, state)
            except Exception as e:
                state.mark_failed(step, str(e))
                raise
                
        return state.final_result()
```

**MVP实现**：
- 每个工作流独立实现为单独类
- 不使用通用DSL，直接硬编码流程
- 状态保存为JSON文件

---

### 2.2 Model Gateway（模型网关）

**职责**：
- 统一接口调用不同模型提供商
- 管理API密钥和配置
- 实现fallback和负载均衡（MVP暂不实现）

**接口设计**：
```python
class ModelGateway:
    def __init__(self, config: dict):
        self.provider = config['provider']
        self.api_base = config['api_base']
        self.api_key = config['api_key']
        self.models = config['models']
        
    def chat(self, model_name: str, messages: list, **kwargs) -> str:
        """调用模型进行对话"""
        # MVP: 直接调用OpenAI兼容接口
        # 后续可扩展为多provider适配
        response = requests.post(
            f"{self.api_base}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.models[model_name],
                "messages": messages,
                **kwargs
            }
        )
        return response.json()["choices"][0]["message"]["content"]
        
    def stream_chat(self, model_name: str, messages: list, **kwargs):
        """流式对话（MVP延后）"""
        raise NotImplementedError("Streaming not implemented in MVP")
```

**MVP限制**：
- 仅支持OpenAI兼容接口
- 不支持流式输出
- 无fallback机制

---

### 2.3 Storage Manager（存储管理）

**职责**：
- 管理项目数据（idea、实验、论文）的增删改查
- 版本控制和快照
- 文件系统和SQLite元数据管理

**设计**：
```python
class StorageManager:
    def __init__(self, config: dict):
        self.project_dir = Path(config['project_dir'])
        self.db_path = Path(config['database'].replace('sqlite:///', ''))
        self._init_db()
        
    def _init_db(self):
        """初始化SQLite数据库"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                metadata JSON
            )
        """)
        # 其他表：ideas, experiments, papers
        
    def save_idea(self, project_id: str, idea_data: dict) -> str:
        """保存Idea"""
        idea_id = str(uuid.uuid4())
        # 存储到文件系统和数据库
        self.conn.execute(
            "INSERT INTO ideas VALUES (?, ?, ?, ?, ?)",
            (idea_id, project_id, json.dumps(idea_data), now(), now())
        )
        return idea_id
        
    def load_project(self, project_id: str) -> dict:
        """加载项目所有数据"""
        # 返回项目、ideas、experiments、papers的聚合数据
        pass
```

**MVP存储格式**：
```
projects/
├── project_001/
│   ├── ideas/
│   │   ├── idea_001.json
│   │   └── idea_002.json
│   ├── experiments/
│   │   ├── exp_001/
│   │   │   ├── config.yaml
│   │   │   ├── logs/
│   │   │   └── results/
│   │   └── exp_002/
│   └── papers/
│       ├── draft_001.md
│       └── final_001.md
└── tutor.db  # SQLite元数据
```

---

## 3. 数据模型

### 3.1 Idea 数据模型
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "title": "研究标题",
  "description": "详细描述",
  "innovation_points": ["创新点1", "创新点2"],
  "scores": {
    "innovation": 8.5,
    "feasibility": 7.2,
    "insight": 6.8
  },
  "total_score": 7.5,
  "debate_history": [
    {"round": 1, "model_a": "...", "model_b": "..."}
  ],
  "created_at": "timestamp"
}
```

### 3.2 Experiment 数据模型
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "idea_id": "uuid",
  "config": {
    "dataset": "...",
    "hyperparams": {...}
  },
  "status": "running|completed|failed",
  "logs": ["log1", "log2"],
  "results": {
    "metrics": {...},
    "plots": ["plot1.png", ...]
  },
  "started_at": "timestamp",
  "completed_at": "timestamp"
}
```

### 3.3 Paper 数据模型
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "experiment_id": "uuid",
  "title": "论文标题",
  "abstract": "...",
  "sections": {
    "introduction": "...",
    "methodology": "...",
    "experiments": "...",
    "conclusion": "..."
  },
  "format": "markdown",
  "reviews": [
    {"role": "theoretical", "feedback": "...", "score": 8}
  ],
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

---

## 4. CLI 设计

### 4.1 命令结构
```
tutor/
├── idea
│   ├── generate     # 生成新idea
│   ├── list         # 列出项目ideas
│   └── show <id>    # 显示idea详情
├── experiment
│   ├── run <idea_id>   # 运行实验
│   ├── logs <exp_id>   # 查看实验日志
│   └── results <exp_id> # 查看结果
├── review
│   ├── paper <paper_id> # 审核论文
│   └── feedback <exp_id> # 查看反馈
├── write
│   ├── start <exp_id>   # 开始撰写
│   ├── edit <paper_id>  # 编辑论文
│   └── export <paper_id> # 导出
└── config
    ├── show           # 显示当前配置
    ├── set <key> <val> # 设置配置
    └── validate       # 验证配置
```

### 4.2 CLI 实现（Typer示例）
```python
import typer
from tutor.cli.idea import idea_app
from tutor.cli.experiment import exp_app
from tutor.cli.review import review_app
from tutor.cli.write import write_app

app = typer.Typer(name="tutor", help="TUTOR 科研自动化工作流系统")
app.add_typer(idea_app, name="idea")
app.add_typer(exp_app, name="experiment")
app.add_typer(review_app, name="review")
app.add_typer(write_app, name="write")

@app.command()
def config(
    action: str = typer.Argument(..., help="show|set|validate"),
    key: str = typer.Option(None, "--key", "-k"),
    value: str = typer.Option(None, "--value", "-v")
):
    """配置管理"""
    # 实现配置命令
    pass

if __name__ == "__main__":
    app()
```

---

## 5. 状态管理

### 5.1 工作流状态机

#### Idea生成状态
```
[START] → [LOADING_PAPERS] → [DEBATE_ROUND_1] → [DEBATE_ROUND_2]
   ↓
[IDEA_GENERATION] → [EVALUATION] → [COMPLETED] / [FAILED]
```

#### 实验执行状态
```
[INIT] → [ENV_CHECK] → [CODE_DOWNLOAD] → [DEPENDENCIES_INSTALL]
   ↓
[RUNNING] → [ANALYSIS] → [COMPLETED] / [TIMEOUT] / [ERROR]
```

### 5.2 状态持久化
- 每个工作流实例保存在 `projects/{id}/workflow_state.json`
- 每完成一步立即保存检查点
- 支持从最近检查点恢复（断点续传）

---

## 6. 错误处理策略

### 6.1 分类处理
- **可恢复错误**（网络超时、API限流）：自动重试（最多3次）
- **用户错误**（配置错误、文件不存在）：明确提示，等待用户修复
- **系统错误**（代码bug）：记录完整上下文，建议用户提交issue

### 6.2 日志规范
- 所有操作记录到 `tutor.log`（RotatingFileHandler）
- 工作流状态变更必须记录：timestamp、step、input/output摘要
- 异常必须记录完整stack trace

### 6.3 用户反馈
- CLI命令失败时，输出清晰错误信息和建议操作
- 提供 `tutor logs` 命令查看详细日志
- 开发日志系统自动记录调试信息

---

## 7. 扩展性设计

### 7.1 插件机制（预留）
```
plugins/
├── __init__.py
├── base.py        # Plugin基类
├── model_ext/     # 模型提供者插件
├── workflow_ext/  # 自定义工作流插件
└── output_ext/    # 输出格式插件
```

### 7.2 配置驱动
- 所有工作流参数通过YAML配置文件控制
- 支持profile（开发/生产）切换
- 动态加载配置，支持热重载

---

## 8. 安全考虑

### 8.1 敏感信息
- API密钥不硬编码，从环境变量或配置文件读取
- 配置文件模板提交到Git，实际配置通过`.env`管理
- 数据库文件权限限制为当前用户

### 8.2 数据隐私
- 所有数据存储在本机，无强制云端同步
- 用户可选择是否发送匿名使用统计（默认关闭）

### 8.3 代码安全
- 依赖包来源验证（仅PyPI官方源）
- 定期更新依赖以修复安全漏洞
- 用户提供的代码执行时限制权限（沙箱，MVP不实现）

---

*架构版本：v1.0-MVP*
*更新日期：2026-03-18*
