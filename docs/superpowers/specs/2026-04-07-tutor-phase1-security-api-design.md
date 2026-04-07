# TUTOR Phase 1: 安全 + API 架构改进设计

**日期:** 2026-04-07
**状态:** 已批准
**范围:** 安全修复 + API 路由统一 + main.py 拆分

---

## 1. 背景与目标

### 1.1 背景

TUTOR 项目经过一段时间的开发，存在以下问题需要解决：

1. **安全漏洞:** `.env` 文件可能包含真实 API Key，存在泄露风险
2. **双轨路由:** legacy 端点 (`/run`) 与新 API (`/api/v1/workflows`) 并存
3. **响应格式不统一:** 不同端点返回格式不一致
4. **main.py 过大:** 727 行，难以维护

### 1.2 目标

- [ ] 消除 API Key 泄露风险
- [ ] 统一 API 路由到 `/api/v1/` 前缀
- [ ] 统一响应格式 (`ApiResponse` envelope)
- [ ] 拆分 main.py 为模块化结构
- [ ] 添加安全中间件

---

## 2. 安全改进

### 2.1 API Key 泄露处理

#### 现状问题
- `.env` 文件包含真实 API Key
- Key 比较使用 `==` 而非 timing-safe 比较

#### 修复方案

**1. 创建 `.env.example`**
```bash
# 创建模板文件，不包含真实值
OPENAI_API_KEY=your-api-key-here
ANTHROPIC_API_KEY=your-api-key-here
DEEPSEEK_API_KEY=your-api-key-here
TUTOR_API_KEY=your-api-key-here
TUTOR_MASTER_KEY=your-master-key-here  # 新增：用于加密存储
REDIS_URL=redis://localhost:6379
DATABASE_URL=sqlite:///./data/tutor.db
```

**2. 修改 API Key 验证 (tutor/core/auth.py)**
```python
# Before (不安全)
if api_key != expected_key:
    raise HTTPException(status_code=401)

# After (安全)
import hmac
if not hmac.compare_digest(api_key, expected_key):
    raise HTTPException(status_code=401)
```

**3. 添加密钥轮换支持**
- 使用 `TUTOR_MASTER_KEY` 加密存储敏感配置
- 支持多组 API Key 兼容

### 2.2 新增安全中间件

```python
# tutor/api/middleware/security.py
from helmet import HelmetMiddleware
from cors import CORSMiddleware

app.add_middleware(HelmetMiddleware)  # 安全响应头
app.add_middleware(
    CORSMiddleware,
    allowed_origins=["http://localhost:3000"],  # 严格配置
    allow_credentials=True,
    ...
)
```

### 2.3 Rate Limiting with Redis

**现状:** 内存实现 `RateLimiter` 类，未使用 Redis

**目标:** 实现 Redis-based 分布式限流

```python
# tutor/api/middleware/rate_limit.py
class RedisRateLimiter:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    async def check_rate_limit(self, key: str, limit: int, window: int):
        # 使用 Redis INCR + EXPIRE 实现滑动窗口
        ...
```

---

## 3. API 架构统一

### 3.1 路由合并

#### 现状
| 端点 | 文件 | 状态 |
|------|------|------|
| `/run` | main.py | Legacy |
| `/runs` | main.py | Legacy |
| `/api/v1/workflows` | workflows.py | New |
| `/api/v1/workflows/{id}` | workflows.py | New |

#### 目标
统一到 `/api/v1/` 前缀，legacy 端点标记为 `@deprecated`

```python
# tutor/api/routes/legacy.py
@router.get("/run", deprecated=True)
async def legacy_run(...):
    # 重定向到新端点或返回 deprecation warning
    warnings.warn("Legacy /run endpoint is deprecated", DeprecationWarning)
```

### 3.2 响应格式统一

#### 统一响应模型
```python
# tutor/api/models/response.py
from pydantic import BaseModel
from typing import Any, Generic, TypeVar

T = TypeVar('T')

class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: str | None = None
    meta: dict | None = None  # pagination, etc.

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool
```

#### 迁移步骤
1. 创建 `ApiResponse` 和 `PaginatedResponse` 模型
2. 逐步修改各端点返回新格式
3. 添加自动化测试验证格式一致性

### 3.3 main.py 拆分

#### 现状
`main.py` (727 行) 包含：
- 应用初始化
- 路由定义
- 中间件配置
- 事件处理器

#### 目标结构
```
tutor/api/
├── main.py                 # 应用入口 (~100 行)
├── routes/
│   ├── __init__.py
│   ├── workflows.py        # 工作流 CRUD + 执行
│   ├── projects.py         # V3 项目管理
│   ├── events.py           # SSE 事件
│   └── health.py           # 健康检查
├── middleware/
│   ├── __init__.py
│   ├── security.py         # Helmet + CORS
│   └── rate_limit.py       # Redis 限流
└── models/
    ├── __init__.py
    └── response.py         # ApiResponse
```

#### 拆分步骤
1. 创建 `routes/` 和 `middleware/` 目录结构
2. 提取健康检查到 `routes/health.py`
3. 提取工作流路由到 `routes/workflows.py`
4. 提取 SSE 事件到 `routes/events.py`
5. 提取中间件到 `middleware/`
6. 简化 `main.py` 为应用初始化

---

## 4. 文件变更清单

### 4.1 新增文件
| 文件 | 说明 |
|------|------|
| `.env.example` | 环境变量模板 |
| `tutor/api/middleware/__init__.py` | Middleware 包 |
| `tutor/api/middleware/security.py` | 安全中间件 |
| `tutor/api/middleware/rate_limit.py` | Redis 限流 |
| `tutor/api/models/__init__.py` | Models 包 |
| `tutor/api/models/response.py` | 统一响应模型 |

### 4.2 修改文件
| 文件 | 变更 |
|------|------|
| `.env` | 移除真实 API Key 或添加到 .gitignore |
| `tutor/core/auth.py` | timing-safe 比较 |
| `tutor/api/main.py` | 简化为入口文件 |
| `tutor/api/routes/__init__.py` | 路由注册 |
| `tutor/api/routes/workflows.py` | 扩展支持 legacy 兼容 |

### 4.3 删除文件
| 文件 | 条件 |
|------|------|
| (无) | Phase 1 不删除任何文件，仅标记 deprecated |

---

## 5. 测试策略

### 5.1 单元测试
```python
tests/unit/test_auth.py
tests/unit/test_api_response.py
tests/unit/test_rate_limiter.py
```

### 5.2 集成测试
```python
tests/integration/test_api.py  # 扩展覆盖新格式
```

### 5.3 验证清单
- [ ] API Key 验证使用 timing-safe 比较
- [ ] 所有端点返回 `ApiResponse` 格式
- [ ] Legacy 端点返回 deprecation warning
- [ ] CORS 配置正确
- [ ] Rate limiter 使用 Redis

---

## 6. 实施顺序

```
Step 1: 创建 .env.example，修改 auth.py (安全)
Step 2: 创建 ApiResponse 模型 (API 格式)
Step 3: 创建 middleware/ 目录和中间件
Step 4: 拆分 main.py 到 routes/
Step 5: 统一工作流路由
Step 6: 添加测试
Step 7: 验证和清理
```

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Breaking Changes | 现有客户端可能无法工作 | 提供迁移指南，保留 legacy 端点 |
| Redis 依赖 | 部署复杂度增加 | 提供 Redis 可选的 fallback |
| 测试覆盖不足 | 回归风险 | 添加自动化测试 |

---

## 8. 后续阶段预览

- **Phase 2:** 存储层重构 (Repository 模式)
- **Phase 3:** 工作流引擎拆分 (idea.py 1900+ 行)
- **Phase 4:** 前端优化

---

**审批状态:** 用户已批准 2026-04-07
