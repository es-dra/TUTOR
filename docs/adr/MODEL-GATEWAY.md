# MODEL-GATEWAY - 模型网关模块详解

## 模块位置
`tutor/core/model/__init__.py`

## 核心类

### ModelConfig
配置数据类，存储：
- `provider`: 模型提供商 (openai/anthropic/local)
- `api_base`: API基础URL
- `api_key`: 认证密钥
- `models`: 角色到模型ID的映射

### ModelGateway
主要功能类，提供：
- `__init__(config_path)`: 加载配置，验证API Key
- `chat(model_name, messages, **kwargs)`: 同步对话调用
- `validate_connection()`: 连接健康检查

## 关键设计

### 错误处理层级
```
ModelError (自定义异常)
├── TimeoutError -> ModelError
├── HTTPError -> ModelError
└── InvalidResponse -> ModelError
```

### 配置加载
- 支持YAML格式
- API Key 从环境变量 `OPENAI_API_KEY` 优先读取
- 配置验证：必须包含 `api_key` 和 `models` 映射

### 日志策略
- `logger.info()`: 记录调用和响应摘要
- `logger.debug()`: 记录完整请求/响应内容
- 结构化日志，便于运维分析

## 代码示例

### 基本使用
```python
from tutor.core.model import ModelGateway

gateway = ModelGateway("config/config.yaml")

# 调用模型
response = gateway.chat(
    "debate_a",
    [{"role": "user", "content": "What is deep learning?"}]
)

print(response)
```

### 多角色调用
```python
responses = {}
for role in ["debate_a", "debate_b", "evaluator"]:
    responses[role] = gateway.chat(role, messages)
```

## 已知限制 (MVP)
- ❌ 不支持流式输出
- ❌ 无请求重试机制
- ❌ 不支持多provider并存（仅OpenAI兼容）
- ❌ 无速率限制处理
- ❌ 无请求缓存

## 测试覆盖

| 测试用例 | 场景 | 状态 |
|---------|------|------|
| test_init_with_valid_config | 正常初始化 | ✅ |
| test_init_missing_config_raises | 配置文件不存在 | ✅ |
| test_chat_success | 调用成功 | ✅ |
| test_chat_unknown_model_raises | 未知模型名 | ✅ |
| test_chat_timeout_raises_model_error | 超时处理 | ✅ |
| test_chat_http_error_raises_model_error | HTTP错误 | ✅ |
| test_chat_invalid_response_format_raises | 响应格式错误 | ✅ |
| test_validate_connection_success | 连接验证成功 | ✅ |
| test_validate_connection_failure | 连接验证失败 | ✅ |

覆盖率: 目标 >= 80%

## TODO (Post-MVP)
- [ ] 实现流式输出支持
- [ ] 添加请求重试（指数退避）
- [ ] 支持 Anthropic Claude 接入
- [ ] 实现模型选择策略（cost-aware routing）
- [ ] 添加请求缓存（Redis）

---

*最后更新: 2026-03-18*
