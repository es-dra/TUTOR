# TUTOR 使用指南

## 系统架构

TUTOR 是一个智能科研自动化平台，采用 V3 项目驱动架构，支持四阶段科研工作流：

1. **Idea生成工作流**：文献分析、多角色辩论、想法评估
2. **实验设计工作流**：环境检测、实验设计、代码实现、实验执行
3. **论文撰写工作流**：大纲生成、章节撰写、语言润色、LaTeX格式转换
4. **论文评审工作流**：单角色初审、跨模型对抗评审、最终评审报告

### 核心组件

- **ModelGateway**：统一模型调用接口，支持 OpenAI、Anthropic、DeepSeek、Minimax 等API
- **WorkflowEngine**：工作流引擎，管理工作流的创建、执行和监控
- **ProjectManager**：项目管理器，统一管理科研项目和角色对话
- **RoleOrchestrator**：角色编排器，管理多角色实时对话和协作
- **WebSocket**：实时通信接口，支持角色辩论和实时状态更新

## 快速开始

### 1. 配置 API 密钥

#### 方法一：环境变量

```bash
# DeepSeek API
export DEEPSEEK_API_KEY=sk-xxx

# Minimax API
export MINIMAX_API_KEY=sk-xxx

# OpenAI API (可选)
export OPENAI_API_KEY=sk-xxx

# Anthropic API (可选)
export ANTHROPIC_API_KEY=sk-xxx
```

#### 方法二：配置文件

创建 `config/config.yaml` 文件：

```yaml
model:
  provider: deepseek
  api_key: sk-xxx
  api_base: https://api.deepseek.com
  models:
    default: deepseek-chat
    innovator: deepseek-chat
    synthesizer: deepseek-chat
    evaluator: deepseek-chat
    analyzer: deepseek-chat
    reviewer: deepseek-chat
```

### 2. 启动系统

#### 启动 API 服务

```bash
# 开发模式
uvicorn tutor.api.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn tutor.api.main:app --host 0.0.0.0 --port 8000
```

#### 启动前端服务

```bash
cd web
npm install
npm run dev
```

### 3. 使用 V3 工作台

1. 打开浏览器访问 `http://localhost:5173`
2. 点击 "v3工作台" 进入项目管理界面
3. 点击 "创建项目" 创建新的科研项目
4. 进入项目竞技场，开始工作流执行

## 工作流执行

### 使用命令行执行

```bash
# 执行完整的四阶段工作流
python run_real_workflows.py

# 执行单个工作流
python -m tutor.cli.idea
python -m tutor.cli.experiment
python -m tutor.cli.write
python -m tutor.cli.review
```

### 使用 API 执行

```bash
# 启动工作流
curl -X POST http://localhost:8000/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{"type": "idea", "config": {"topic": "AI for scientific research"}}'

# 查看工作流状态
curl http://localhost:8000/api/v1/runs/{run_id}
```

## 多角色辩论

1. 在项目竞技场中点击 "多角色辩论" 标签
2. 输入辩论主题，点击 "开始辩论"
3. 观察不同角色的实时发言和思考状态
4. 参与对话，与AI角色进行互动

## LaTeX 论文生成

1. 完成论文撰写工作流后，系统会自动生成 LaTeX 源码
2. 系统会尝试编译为 PDF 文件
3. 生成的文件位于 `workflow_results_real/latex/` 目录

## 系统配置

### 模型配置

在 `config/config.yaml` 中配置模型参数：

```yaml
model:
  provider: deepseek  # 可选: openai, anthropic, minimax
  api_key: sk-xxx
  api_base: https://api.deepseek.com
  models:
    default: deepseek-chat
    innovator: deepseek-chat
    synthesizer: deepseek-chat
    evaluator: deepseek-chat
    analyzer: deepseek-chat
    reviewer: deepseek-chat
  max_retries: 3
  retry_base_delay: 1.0
```

### 工作流配置

```yaml
workflow:
  type: idea
  steps: 6
  debate_rounds: 2
  cross_model_debate: false
  latex:
    authors: "Research Team"
    compile: true
```

## 故障排除

### 常见问题

1. **API 连接失败**
   - 检查 API 密钥是否正确
   - 检查网络连接
   - 检查 API 提供商的服务状态

2. **LaTeX 编译失败**
   - 安装 LaTeX：`sudo apt install texlive-latex-recommended texlive-fonts-recommended`
   - 检查 LaTeX 源码是否有语法错误

3. **WebSocket 连接失败**
   - 检查浏览器是否支持 WebSocket
   - 检查服务器是否启用了 WebSocket

4. **工作流执行超时**
   - 增加 `max_retries` 和 `retry_base_delay`
   - 检查模型 API 的响应时间

## 示例项目

### 示例 1：动态自适应思维链

**主题**：Dynamic Adaptive Chain-of-Thought: Efficient Reasoning for Large Language Models

**执行流程**：
1. Idea生成：分析相关文献，生成创新想法
2. 实验设计：设计实验验证方法效果
3. 论文撰写：生成完整的学术论文
4. 论文评审：进行跨模型对抗评审

**预期结果**：生成包含 LaTeX 源码和 PDF 的完整论文

### 示例 2：多模态科学研究助手

**主题**：Multi-modal Scientific Research Assistant with LLM

**执行流程**：
1. Idea生成：探索多模态在科研中的应用
2. 实验设计：设计多模态实验方案
3. 论文撰写：撰写研究论文
4. 论文评审：获取评审反馈

## 系统监控

### API 健康检查

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready
```

### 指标监控

系统集成了 Prometheus 指标，访问：
- `http://localhost:8000/api/v1/metrics`

## 开发指南

### 项目结构

```
TUTOR/
├── tutor/                 # 核心代码
│   ├── api/             # API 接口
│   ├── cli/             # 命令行工具
│   ├── config/          # 配置管理
│   ├── core/            # 核心功能
│   │   ├── model/       # 模型网关
│   │   ├── project/     # 项目管理
│   │   ├── workflow/    # 工作流引擎
│   │   └── providers/   # 模型提供商
├── web/                  # 前端代码
├── tests/                # 测试代码
├── config/               # 配置文件
└── workflow_results/     # 工作流结果
```

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单元测试
python -m pytest tests/unit/ -v

# 运行集成测试
python -m pytest tests/integration/ -v
```

## 版本历史

### V3 架构 (最新)
- 项目驱动架构
- 多角色实时协作
- WebSocket 实时通信
- 四阶段工作流集成
- 支持 DeepSeek 和 Minimax API

### V2 架构
- 工作流引擎
- 模型网关
- 基础工作流实现

### V1 架构
- 初始版本
- 基本科研助手功能

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交代码
4. 运行测试
5. 提交 Pull Request

## 许可证

Apache 2.0 License

---

**TUTOR** - Intelligent Research Automation Platform

© 2024 TUTOR Team