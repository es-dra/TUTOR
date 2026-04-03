# TutorClaw Platform Makefile
# 简化开发和工作流命令

.PHONY: help setup dev-up dev-down test lint format build deploy clean logs shell

# 默认目标
.DEFAULT_GOAL := help

help: ## 显示此帮助信息
	@echo "TutorClaw Platform - 可用命令:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============ 环境设置 ============

setup: ## 首次环境设置 (安装依赖, 初始化配置)
	@echo "🔧 设置TutorClaw开发环境..."
	uv pip install -e ".[dev]"
	cp .env.example .env
	@echo "✅ 环境设置完成！"
	@echo "⚠️  请编辑 .env 文件设置必要的配置"
	@echo "📖 查看 README.md 了解详情"

# ============ 开发环境 ============

dev-up: ## 启动开发环境 (Docker Compose)
	@echo "🚀 启动开发环境..."
	docker-compose -f docker-compose.dev.yml up -d
	@echo "⏳ 等待服务就绪..."
	@sleep 5
	@echo "✅ 服务已启动:"
	@echo "   📡 API文档: http://localhost:8080/docs"
	@echo "   🌐 Web界面: http://localhost:3000"
	@echo "   📊 监控: http://localhost:3001 (admin/admin)"
	@echo "   📈 指标: http://localhost:9090"
	@echo ""
	@echo "运行 'make logs' 查看日志"

dev-down: ## 停止开发环境
	@echo "🛑 停止开发环境..."
	docker-compose -f docker-compose.dev.yml down
	@echo "✅ 已停止"

dev-restart: dev-down dev-up ## 重启开发环境

dev-logs: ## 查看开发环境日志
	docker-compose -f docker-compose.dev.yml logs -f

logs: dev-logs ## 别名

# ============ 代码质量 ============

test: ## 运行所有测试
	@echo "🧪 运行测试..."
	pytest tests/ -v --cov=tutor --cov-report=term --cov-report=html
	@echo "✅ 测试完成！查看 htmlcov/index.html 查看覆盖率报告"

test-unit: ## 仅运行单元测试
	pytest tests/unit -v

test-integration: ## 仅运行集成测试
	pytest tests/integration -v

test-e2e: ## 仅运行E2E测试
	pytest tests/e2e -v

lint: ## 代码检查 (black, isort, mypy)
	@echo "🔍 检查代码..."
	black --check tutor/
	isort --check-only tutor/
	mypy tutor/
	@echo "✅ 代码检查通过！"

format: ## 代码格式化
	@echo "🎨 格式化代码..."
	black tutor/
	isort tutor/
	@echo "✅ 格式化完成！"

# ============ 构建部署 ============

build: ## 构建Docker镜像
	@echo "🔨 构建Docker镜像..."
	docker-compose -f docker-compose.dev.yml build
	@echo "✅ 构建完成！"

build-prod: ## 构建生产镜像
	@echo "🔨 构建生产镜像..."
	docker-compose -f docker-compose.prod.yml build
	@echo "✅ 生产镜像构建完成！"

deploy: build-prod ## 部署到生产环境
	@echo "🚢 部署到生产环境..."
	docker-compose -f docker-compose.prod.yml up -d
	@echo "✅ 部署完成！"

# ============ 数据库 ============

db-migrate: ## 执行数据库迁移
	@echo "🗃️  执行数据库迁移..."
	alembic upgrade head
	@echo "✅ 迁移完成！"

db-downgrade: ## 回滚数据库迁移
	@echo "🗃️  回滚数据库..."
	alembic downgrade -1
	@echo "✅ 回滚完成！"

db-shell: ## 连接数据库Shell
	docker-compose -f docker-compose.dev.yml exec postgres psql -U tutor -d tutor

# ============ 监控维护 ============

monitor: ## 查看应用状态
	@echo "📊 应用状态:"
	@curl -s http://localhost:8080/health || echo "❌ Gateway 未运行"
	@curl -s http://localhost:8080/admin/health || echo "❌ 健康检查失败"
	@echo ""
	@echo "📈 Prometheus: http://localhost:9090"
	@echo "📊 Grafana: http://localhost:3001"

monitor-logs: ## 查看结构化日志
	docker-compose -f docker-compose.dev.yml logs -f gateway | jq -r '.msg' 2>/dev/null || tail -f logs/gateway.log

# ============ 清理 ============

clean: ## 清理构建文件和临时数据
	@echo "🧹 清理..."
	rm -rf .coverage htmlcov/ dist/ build/ *.egg-info
	rm -rf logs/* tmp/*
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	docker system prune -f
	@echo "✅ 清理完成！"

clean-docker: ## 清理Docker资源 (镜像、容器、卷)
	@echo "🧹 清理Docker资源..."
	docker-compose -f docker-compose.dev.yml down -v
	docker rmi tutor_* -f 2>/dev/null || true
	@echo "✅ Docker清理完成！"

# ============ 工具 ============

shell: ## 进入gateway容器Shell
	docker-compose -f docker-compose.dev.yml exec gateway bash

shell-db: ## 进入postgres容器Shell
	docker-compose -f docker-compose.dev.yml exec postgres bash

shell-redis: ## 进入redis容器Shell
	docker-compose -f docker-compose.dev.yml exec redis bash

# 创建一个新的迁移文件
migration: ## 创建新的数据库迁移 (使用 message="...")
	alembic revision --autogenerate -m "$(message)"

# 备份数据库
backup: ## 备份数据库
	@echo "💾 备份数据库..."
	docker-compose -f docker-compose.dev.yml exec postgres pg_dump -U tutor tutor > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "✅ 备份完成！"

# 生成API客户端
gen-client: ## 生成API客户端 (OpenAPI)
	@echo "🔧 生成API客户端..."
	openapi-generator generate \
		-i http://localhost:8080/openapi.json \
		-g python \
		-o clients/python
	@echo "✅ 客户端生成完成！"

# 初始化知识库
notes-init: ## 初始化Obsidian知识库
	@echo "📚 初始化知识库..."
	mkdir -p notes/"{01%20-%20Project%20Overview,02%20-%20ADRs,03%20-%20Workflow%20Specs,04%20-%20Technical%20Notes,05%20-%20Test%20Strategy,06%20-%20Examples}"
	@echo "✅ 知识库结构创建完成！"

# 运行Rot-E示例实验
exp-rot-e: ## 运行Rot-E ASISR示例实验
	@echo "🔬 启动Rot-E实验..."
	cd experiments/rot-e-asisr && \
	uv run python scripts/train.py --config configs/train_rot_e_full.yaml
	@echo "✅ 实验完成！结果保存在 experiments/rot-e-asisr/results/"

# CI模拟 (本地运行所有检查)
ci: lint test ## 模拟CI流水线
	@echo "✅ CI检查全部通过！"

# 一次性设置 (首次使用)
first-time: setup notes-init dev-up ## 首次完整设置
	@echo ""
	@echo "🎉 TutorClaw平台已就绪！"
	@echo ""
	@echo "下一步:"
	@echo "  1. 访问 http://localhost:3000 使用Web界面"
	@echo "  2. 运行 'tutor --help' 探索CLI命令"
	@echo "  3. 查看 docs/ 目录了解详细文档"
	@echo "  4. 运行 'make test' 验证安装"
	@echo ""
	@echo "需要帮助? 运行 'make help'"
