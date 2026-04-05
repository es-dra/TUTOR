---
name: tutor-dev
description: TUTOR 项目开发规范。智能研究自动化工作流平台，FastAPI + React 全栈应用。包含工作流引擎、多 Provider 路由、SSE 事件推送、SQLite 存储等模块。
origin: TUTOR
---

# TUTOR 项目开发规范

## 项目概览

**TUTOR** (Thinking, Understanding, Testing, Optimizing, Refining) 是一个智能研究自动化工作流平台。

- **后端**: Python 3.9+, FastAPI, SQLAlchemy, Typer CLI
- **前端**: React 18, Vite 5, Zustand, Lucide React
- **数据库**: SQLite (data/tutor_runs.db)
- **工作流**: idea / experiment / review / write 四种类型
- **AI Provider**: OpenAI, Anthropic, DeepSeek, Azure, Minimax, Ollama/LM Studio

## 何时激活

- 修改或新增任何 TUTOR 项目代码时
- 设计新的工作流、步骤、Provider 或 API 端点时
- 编写或修改测试时
- 重构代码时

---

## 架构总览

```
tutor/
  core/
    workflow/       # 工作流引擎 (ABC), 步骤定义, 辩论框架
    model/          # ModelGateway 统一 AI 调用门面
    providers/      # 多 Provider 抽象 + 路由策略
    storage/        # SQLite 仓储模式
    config/         # YAML 配置加载器 + 环境变量替换
    debate/         # 跨模型辩论系统
    multiagent/     # 多智能体编排
    monitor/        # 资源监控、Token 预算、成本追踪
    auth/           # JWT 认证、密码哈希、会话管理
    scheduling/     # 实验调度、想法调度
    deployment/     # 远程执行、SSH 客户端
    external/       # 外部集成 (DBLP, Obsidian, Zotero)
    project/        # 项目管理
    review/         # 自动评审、跨模型评审
  api/
    main.py         # FastAPI 应用工厂
    models.py       # Pydantic 模型 + 统一响应信封
    prometheus.py   # Prometheus 指标
    routes/         # 模块化路由组 (auth, users, providers, projects, uploads, events)
    sse/            # SSE 事件广播系统
  cli/              # Typer CLI 子命令组
  config/           # 应用配置 (config.yaml)
config/
  providers.yaml    # Provider 配置 (gitignored)
web/
  src/
    App.jsx         # React 应用 (状态路由)
    api.js          # Fetch API 客户端 + SSE 支持
    pages/          # 页面组件
tests/
  conftest.py       # 共享 pytest fixtures
  unit/             # 单元测试 (mock 驱动)
  integration/      # 集成测试 (TestClient 驱动)
```

---

## 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 类名 | PascalCase | `WorkflowEngine`, `ModelGateway`, `RunStorage` |
| 函数/方法 | snake_case | `save_checkpoint`, `get_run_status` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRIES`, `DEBOUNCE_DELAY_MS` |
| 私有成员 | `_leading_underscore` | `_state`, `_current_step_index` |
| 模块/文件 | snake_case.py | `workflow_runs.py`, `model_gateway.py` |
| 目录 | snake_case | `core/workflow/`, `api/routes/` |
| 异常类 | PascalCase + Error 后缀 | `ModelError`, `ProviderError`, `ConfigError` |
| 枚举值 | UPPER_SNAKE_CASE | `PENDING`, `RUNNING`, `COMPLETED` |
| CLI 子命令 | snake_case + _app 后缀 | `idea_app`, `config_app` |
| 前端组件 | PascalCase.jsx | `Dashboard.jsx`, `WorkflowDetail.jsx` |

---

## 工作流引擎规范

### 核心类层次

```python
WorkflowStatus (str, Enum)          # 状态机: PENDING, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED
CheckpointData (dataclass)          # 检查点数据 + CRC32 完整性校验
WorkflowResult (dataclass)          # 执行结果
WorkflowContext(Generic[T])         # 跨步骤共享状态容器
WorkflowStep(ABC)                   # 抽象步骤
Workflow(ABC)                       # 抽象工作流
WorkflowEngine                      # 生命周期管理器
```

### 新增工作流步骤模板

```python
from tutor.core.workflow.base import WorkflowStep, WorkflowContext

class MyStep(WorkflowStep):
    """步骤描述。"""

    def validate(self, context: WorkflowContext) -> bool:
        """验证前置条件。"""
        errors = []
        if not context.get_state("required_key"):
            errors.append("Missing required_key")
        return len(errors) == 0, errors

    def execute(self, context: WorkflowContext) -> dict:
        """执行步骤逻辑。"""
        model_gateway = context.model_gateway
        broadcaster = context.broadcaster

        # 调用 AI 模型
        result = model_gateway.chat(
            model_name="default",
            messages=[{"role": "user", "content": "prompt here"}],
            temperature=0.7,
            max_tokens=2000,
        )

        # 发出 SSE 事件
        if broadcaster:
            broadcaster.emit(context.get_state("run_id"), "step_progress", {
                "step": "my_step",
                "data": result,
            })

        return {"output": result}

    def rollback(self, context: WorkflowContext) -> None:
        """回滚逻辑（可选）。"""
        pass
```

### 新增工作流类型模板

```python
from tutor.core.workflow.base import Workflow, WorkflowStep

class MyFlow(Workflow):
    """我的工作流。"""

    def build_steps(self) -> list[WorkflowStep]:
        return [
            StepOne(),
            StepTwo(),
            StepThree(),
        ]

    def initialize(self) -> dict:
        """初始化上下文。"""
        return {"initial_key": "initial_value"}
```

### 失败策略

- `ROLLBACK` — 触发回滚链
- `STOP` — 立即停止，标记为 FAILED
- `CONTINUE` — 记录决策日志，继续执行
- `PAUSE` — 抛出 `WorkflowPauseError`，等待人工干预

### 注册新工作流

在 `tutor/api/main.py` 的 `_WORKFLOW_CLASSES` 映射中添加，或通过 `_load_workflow_classes()` 自动发现。

---

## API 规范

### 响应信封

所有 API 响应遵循统一信封格式：

```python
# 成功响应
{
    "success": True,
    "data": {...},
    "meta": {"total": 100, "page": 1, "limit": 20}  # 可选
}

# 错误响应
{
    "success": False,
    "error": {
        "code": "validation_error",
        "message": "Request validation failed",
        "details": [...]  # 可选
    }
}
```

### 使用辅助函数

```python
from tutor.api.models import success_response, error_response, paginated_response

# 成功
return success_response(data={"id": "abc-123"})

# 错误
return error_response(code="not_found", message="Run not found")

# 分页
return paginated_response(items=runs, total=100, limit=20, offset=0)
```

### HTTP 状态码

| 状态码 | 用途 |
|--------|------|
| 200 | GET/PUT/PATCH 成功 |
| 201 | POST 创建资源 |
| 204 | DELETE 成功 |
| 400 | 请求格式错误 |
| 401 | 认证失败 (X-API-Key) |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 422 | 验证失败 |
| 429 | 限流 (带 Retry-After 头) |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

### 新增路由模块

在 `tutor/api/routes/` 下创建新模块：

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/my-resource", tags=["my-resource"])

@router.get("/")
async def list_resources():
    ...

@router.post("/")
async def create_resource():
    ...
```

然后在 `tutor/api/main.py` 的 `create_app()` 中注册：

```python
from tutor.api.routes.my_resource import router as my_resource_router
app.include_router(my_resource_router)
```

### 限流

使用 `RateLimiter` 中间件，返回 429 + `Retry-After` 头。

### SSE 事件广播

```python
from tutor.api.main import broadcaster

broadcaster.emit(run_id, "step_progress", {"step": "name", "data": {...}})
broadcaster.emit_complete(run_id, result)
```

---

## ModelGateway 规范

### 调用 AI 模型

```python
from tutor.core.model import ModelGateway, ModelConfig

# 创建网关
gateway = ModelGateway(config_path="config/providers.yaml")
# 或直接传 API key
gateway = ModelGateway("sk-xxx")

# 调用
result = gateway.chat(
    model_name="default",       # 或具体模型名/角色名
    messages=[{"role": "user", "content": "..."}],
    temperature=0.7,
    max_tokens=2000,
)
```

### 角色分层

```python
# 获取角色层级
tier = gateway.get_role_tier("innovator")  # "high" / "medium" / "low"

# 自动分配
assignments = gateway.assign_models_by_tier()

# 获取角色对应模型
model = gateway.get_model_for_role("evaluator")
```

### 重试与回退

- 可重试错误：超时、429 限流、5xx 服务器错误
- 指数退避：`delay = retry_base_delay * (2 ** retry_count)`
- 回退链：主模型失败后按配置顺序尝试备用模型
- 全部耗尽后抛出 `ModelError`

---

## Provider 路由规范

### 路由策略

| 策略 | 行为 |
|------|------|
| `priority` | 使用最高优先级 Provider，失败时回退 |
| `failover` | 尝试主 Provider，然后依次尝试所有其他 |
| `loadbalance` | 轮询分配请求 |
| `cost-optimize` | 当前等同于 priority |

### 注册新 Provider

```python
from tutor.core.providers.base import BaseProvider, ProviderRouter
from tutor.core.providers.base import ProviderConfig, ChatMessage, ChatResponse

@ProviderRouter.register_provider("myprovider")
class MyProvider(BaseProvider):
    def chat(self, messages, model, temperature, max_tokens) -> ChatResponse:
        ...

    def validate_connection(self) -> bool:
        ...
```

### 异常层次

```
ProviderError
  -> ProviderConnectionError
  -> ProviderRateLimitError
  -> ProviderAuthenticationError
```

---

## 存储层规范

### RunStorage 使用

```python
from tutor.core.storage.workflow_runs import RunStorage

storage = RunStorage(db_path="data/tutor_runs.db")

# CRUD
storage.create_run(run_id, workflow_type, params, config)
run = storage.get_run(run_id)
storage.update_status(run_id, status="completed", result=...)
storage.list_runs(status="running", limit=20, offset=0)
storage.delete_run(run_id)

# 事件
storage.add_event(run_id, "step_progress", {"step": "name"})
events = storage.get_events(run_id)

# 统计
stats = storage.get_stats()
```

### 数据库约定

- JSON 列使用 `json.dumps(..., ensure_ascii=False)` 存储
- 时间戳使用 ISO 8601 + `Z` 后缀
- 线程安全：`threading.Lock` 保护 SQLite 连接
- 自动迁移：`_migrate_missing_columns()` 添加缺失列

---

## 配置规范

### 配置加载

```python
from tutor.config import load_config

config = load_config()  # 自动搜索路径
config = load_config("/path/to/config.yaml")  # 指定路径
```

### 环境变量替换

配置文件中支持 `${VAR_NAME}` 语法，加载时自动替换：

```yaml
providers:
  openai:
    api_key: "${OPENAI_API_KEY}"
    api_base: "${TUTOR_API_BASE:-https://api.openai.com/v1}"
```

### 配置搜索顺序

1. 显式传入路径
2. `TUTOR_CONFIG` 环境变量
3. `config/config.yaml`
4. `config.yaml`
5. 包相对路径

---

## CLI 规范

### 新增子命令

```python
from typer import Typer

app = Typer()

@app.command()
def my_command(arg: str, verbose: bool = False):
    """命令描述。"""
    if verbose:
        typer.echo(f"Processing {arg}")
```

然后在 `tutor/cli/__init__.py` 中注册：

```python
from .my_command import app as my_command_app
app.add_typer(my_command_app, name="my-command")
```

### 优雅降级

```python
try:
    from .my_module import app as my_app
except ImportError:
    my_app = Typer()
    @my_app.command()
    def _():
        typer.echo("This command requires optional dependencies.")
```

---

## 前端规范

### 技术栈

- React 18 (函数组件 + Hooks)
- Vite 5 (构建工具)
- 原生 `fetch` API (不使用 axios)
- 状态路由 (不使用 React Router)
- Lucide React (图标)

### API 调用

```javascript
import api from './api';

// 启动工作流
const result = await api.startRun('idea', { papers: [...] });

// 获取状态
const status = await api.getRunStatus(runId);

// SSE 监听
api.createEventSource(runId,
  (data) => console.log('event:', data),
  (error) => console.error('sse error:', error)
);
```

### 页面组件

```jsx
export function MyPage({ onViewRun }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.someCall().then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) return <div>Loading...</div>;

  return <div>{data}</div>;
}
```

### 路由注册

在 `web/src/App.jsx` 的 `switch(currentPage)` 中添加新页面。

---

## 测试规范

### 单元测试

```python
import pytest
from unittest.mock import Mock, patch

class TestMyClass:
    @patch('tutor.core.module.requests.post')
    def test_success(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response

        result = my_function()
        assert result == "ok"

    def test_failure(self):
        with pytest.raises(ModelError, match="Timeout"):
            raise ModelError("Timeout")
```

### 集成测试

```python
import pytest
from fastapi.testclient import TestClient
from tutor.api.main import create_app

class TestMyEndpoints:
    def setup_method(self):
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_health(self):
        response = self.client.get("/health")
        assert response.status_code == 200
```

### 共享 Fixtures

`tests/conftest.py` 提供：
- `temp_db_path` — 隔离的 SQLite DB
- `temp_data_dir` — 隔离的数据目录

### 运行测试

```bash
pytest tests/ -v                          # 全部测试
pytest tests/unit/ -v                     # 仅单元测试
pytest tests/integration/ -v              # 仅集成测试
pytest tests/ --cov=tutor --cov-report=html  # 覆盖率
```

---

## 错误处理规范

### 自定义异常层次

每个领域有独立的异常基类：

```python
# Model
class ModelError(Exception): ...

# Providers
class ProviderError(Exception): ...
class ProviderConnectionError(ProviderError): ...
class ProviderRateLimitError(ProviderError): ...
class ProviderAuthenticationError(ProviderError): ...

# Config
class ConfigError(Exception): ...

# Workflow
class WorkflowPauseError(Exception): ...
```

### API 错误处理

```python
from fastapi import HTTPException

raise HTTPException(status_code=404, detail="Run not found")
raise HTTPException(status_code=400, detail="Invalid workflow type")
```

### 后台任务错误

```python
try:
    # 执行工作流
    ...
except Exception as e:
    logger.error("Workflow failed", exc_info=True)
    run_storage.update_status(run_id, status="failed", error=str(e))
finally:
    # 清理资源
    ...
```

### 优雅降级

```python
try:
    from fastapi import FastAPI
except ImportError:
    FastAPI = None  # Stub for environments without FastAPI
```

---

## 导入规范

### 顺序

1. 标准库
2. 第三方库
3. 本地模块

### 相对导入

兄弟模块使用相对导入：

```python
from .retry import RetryPolicy, FailureStrategy
from .base import WorkflowStep, WorkflowContext
```

### 延迟导入

避免循环依赖时在函数内导入：

```python
def _start_monitoring(self):
    from tutor.core.monitor.resource_monitor import ResourceMonitor
    self._monitor = ResourceMonitor()
```

### 别名导入

提高可读性：

```python
from tutor.api.routes.auth import router as auth_router
from .idea import app as idea_app
```

---

## 代码风格

### 格式化

- **Black**: line-length = 88
- **isort**: profile = "black"
- **mypy**: 严格模式 (disallow_untyped_defs = true)

### 注释

- 解释 **WHY** 而非 **WHAT**
- 公共 API 使用 JSDoc/Google-style docstring
- 允许中英混杂，但保持上下文一致

### 函数长度

- 单个函数不超过 50 行
- 超过则拆分为更小的函数

### 避免深层嵌套

使用 early return 替代多层 if：

```python
# BAD
if user:
    if user.is_admin:
        if market:
            ...

# GOOD
if not user:
    return
if not user.is_admin:
    return
if not market:
    return
...
```

---

## 常见问题与陷阱

### 循环依赖

- 使用延迟导入 (函数内 import)
- 使用 `as` 别名避免命名冲突
- 模块级常量在导入时求值，注意顺序

### 双重 EventBroadcaster

- `tutor/api/main.py` 中的 `EventBroadcaster` — 按 run_id 订阅
- `tutor/api/sse/events.py` 中的 `EventBroadcaster` — 全局广播
- 两者不连通，注意使用场景

### 重复的 QuotaManager

- `tutor/core/monitor/quota.py` — 预算导向
- `tutor/core/monitor/quotas.py` — 资源阈值导向
- 注意导入来源，避免混淆

### 硬编码值

- CORS: `allow_origins=["*"]` (main.py:293)
- Run ID: `str(uuid.uuid4())[:8]` 有碰撞风险 (main.py:377)
- 存储路径: `Path(os.getcwd()) / "test_results"` (main.py:787)

---

## 快速参考

### 启动服务

```bash
# API (开发模式)
uvicorn tutor.api.main:app --reload --port 8080

# Web UI
cd web && npm start

# CLI
tutor status
tutor idea --papers "https://arxiv.org/abs/2301.00001"
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 |
| `TUTOR_API_BASE` | API 基础 URL (可选) |
| `TUTOR_CONFIG` | 配置文件路径 (可选) |

### API 端点

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/run` | 启动工作流 |
| GET | `/runs` | 列出所有运行 |
| GET | `/runs/{id}` | 获取运行状态 |
| GET | `/events/{id}` | SSE 事件流 |
| GET | `/approvals` | 列出审批 |
| POST | `/approvals/{id}/approve` | 批准 |
| POST | `/approvals/{id}/reject` | 拒绝 |
