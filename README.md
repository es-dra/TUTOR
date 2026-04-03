# TUTOR - 智能研究自动化平台

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-red)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.2+-61DAFB.svg)](https://reactjs.org/)

**TUTOR** 是一个智能研究自动化工作流平台，支持从研究想法生成到论文撰写的完整流程。

## 当前实现状态

### ✅ 已完成
- **CLI 命令行界面** - `tutor` 命令
- **REST API** (FastAPI) - `/run`, `/runs`, `/events` 等端点
- **Web UI** (React) - 工作流仪表盘和监控
- **工作流引擎** - 状态机 + 检查点 + 重试机制
- **4种工作流类型**:
  - `idea` - 研究想法生成
  - `experiment` - 实验执行
  - `review` - 论文评审
  - `write` - 论文撰写
- **ModelGateway** - OpenAI 兼容 API 统一调用
- **限流和监控** - 速率限制 + Prometheus 指标
- **单元测试 + CI/CD** - GitHub Actions

### 🚧 开发中
- 多智能体协作框架（规划中）
- 完整的前端界面

### ✅ 数据库持久化
- **SQLite存储** - `tutor/core/storage/workflow_runs.py`
- **RunStorage类** - 支持创建、查询、更新、删除工作流运行记录
- **事件历史** - `run_events`表存储SSE事件历史
- **统计接口** - `get_stats()`提供按状态/类型统计

## 项目结构

```
tutor/
├── api/                    # FastAPI Web 服务
│   ├── main.py            # 主应用（限流、SSE、审批路由）
│   └── prometheus.py       # 指标导出
├── cli/                   # CLI 命令行工具
│   ├── idea.py            # 想法生成命令
│   ├── experiment.py      # 实验执行命令
│   ├── review.py          # 论文评审命令
│   └── write.py           # 论文撰写命令
├── core/
│   ├── model/             # ModelGateway 模型调用
│   ├── workflow/          # 工作流定义
│   │   ├── base.py        # 引擎基类
│   │   ├── idea.py        # IdeaFlow
│   │   ├── experiment.py  # ExperimentFlow
│   │   ├── review.py      # ReviewFlow
│   │   └── write.py       # WriteFlow
│   ├── scheduling/         # 调度器
│   ├── storage/            # 存储后端
│   │   └── workflow_runs.py  # SQLite持久化
│   ├── monitor/            # 监控指标
│   └── external/          # 外部服务集成
├── config/                # 配置文件
└── tests/                # 测试套件

web/                      # React Web 应用
├── src/
│   ├── App.js            # 主应用
│   ├── api.js            # API 客户端
│   └── pages/            # 页面组件
└── package.json
```

## 快速开始

### 1. 安装依赖

```bash
# Python 后端
pip install -e ".[dev]"

# Node.js 前端
cd web && npm install
```

### 2. 配置环境变量

```bash
export OPENAI_API_KEY=sk-your-api-key
export TUTOR_API_BASE=https://api.openai.com/v1  # 可选
```

### 3. 启动 API 服务

```bash
# 开发模式（热重载）
uvicorn tutor.api.main:app --reload --port 8080

# 生产模式
python -m tutor.api.main
```

### 4. 启动 Web UI

```bash
cd web
npm start
# 访问 http://localhost:3000
```

### 5. 使用 CLI

```bash
# 查看状态
tutor status

# 创建想法生成工作流
tutor idea --papers "https://arxiv.org/abs/2301.00001"
```

## API 端点

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/run` | 启动工作流 |
| GET | `/runs` | 列出所有运行 |
| GET | `/runs/{id}` | 获取运行状态 |
| GET | `/events/{id}` | SSE 事件流 |
| GET | `/approvals` | 列出审批请求 |
| POST | `/approvals/{id}/approve` | 批准 |
| POST | `/approvals/{id}/reject` | 拒绝 |

### 启动工作流示例

```bash
curl -X POST http://localhost:8080/run \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_type": "idea",
    "params": {
      "papers": ["https://arxiv.org/abs/2301.00001"]
    }
  }'
```

## 工作流

### IdeaFlow - 研究想法生成

```
论文加载 → 验证 → 文献分析 → 想法辩论 → 评估 → 提案
```

### ExperimentFlow - 实验执行

```
环境检测 → 代码获取 → 依赖安装 → 实验运行 → 结果分析 → 报告生成
```

### ReviewFlow - 论文评审

```
论文加载 → 结构化分析 → 多维度评分 → 改进建议
```

### WriteFlow - 论文撰写

```
大纲生成 → 章节撰写 → 格式检查 → 专家审核 → 语言润色 → 导出
```

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 带覆盖率
pytest tests/ --cov=tutor --cov-report=html

# 只跑单元测试
pytest tests/unit/ -v
```

## 监控

- **Prometheus 指标**: `GET /metrics`
- **健康检查**: `GET /health/ready`

## 路线图

- [x] 数据库持久化（SQLite）
- [ ] 多智能体协作框架
- [ ] 更完善的前端界面
- [ ] Docker 一键部署
- [ ] Kubernetes 支持

## 许可证

Apache 2.0
