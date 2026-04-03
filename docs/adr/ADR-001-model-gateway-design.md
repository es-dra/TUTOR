# ADR-001: Model Gateway 统一接口设计

## Status
🟢 Accepted

## Context
TUTOR系统需要调用多种模型完成不同工作流（Debate、Evaluation、Writing等）。每个工作流可能使用不同角色和模型，但调用方式相似。需要统一接口来管理：
- API密钥和配置
- 模型选择（不同角色对应不同模型）
- 错误处理和重试
- 连接验证

## Decision
采用 **Model Gateway 模式**：
- 创建单一 `ModelGateway` 类，封装所有模型调用
- 通过配置文件映射角色名到具体模型ID
- 提供 `chat(model_name, messages)` 统一接口
- MVP 仅支持 OpenAI 兼容接口，不实现流式输出

## Alternatives Considered
1. **每个模块独立调用** - 导致配置分散，重复代码
2. **工厂模式** - 过于复杂，MVP不需要
3. **策略模式** - 预留扩展性，但MVP过度设计

## Consequences

### ✅ Positive
- 集中管理API密钥和配置
- 易于切换模型和调试
- 单一错误处理逻辑
- 便于后续扩展多provider

### ⚠️ Negative
- 所有调用通过单点，可能成为瓶颈（后续可优化）
- MVP不支持流式输出，长文本需等待全部生成

### 🔄 Neutral
- 配置使用YAML格式，需要PyYAML依赖
- 测试需要mock requests，增加测试复杂度

## References
- [[MODEL-GATEWAY]] - 实现细节
- [[DEV-LOG-2026-03-18]] - 开发日志

---

*创建时间: 2026-03-18*
*作者: TutorClaw*
