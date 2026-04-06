# Repo Cleanup Candidates (for open-source readiness)

更新时间：2026-04-06

本文件用于记录仓库中可能冗余、敏感或可归档的文件。

## 已处理（本次）

1. `test_api.py`
   - 问题：包含硬编码 API Key，且不在 `tests/` 体系内。
   - 动作：已删除。

2. `web/public/index.html`
   - 问题：Vite 项目中使用 `web/index.html` 作为入口，该文件属于历史残留（CRA 风格）。
   - 动作：已删除。

3. `web/src/index.css.newdesign`
   - 问题：未被任何入口文件引用，属于未接入样式草稿。
   - 动作：已删除。

4. `docs/adr/tutor-development-log.md`
   - 问题：与 `docs/dev-logs/tutor-development-log.md` 重复维护。
   - 动作：改为跳转说明，统一以 `docs/dev-logs/` 为主。

## 建议继续评估

1. `test_writeflow.py`
   - 现状：根目录手工脚本，不在标准测试路径中。
   - 建议：若仍需保留，迁移到 `scripts/` 并改名为 `smoke_writeflow.py`；否则删除。

2. `workflow_results/` 与 `workflow_results_real/`
   - 现状：都存放执行产物，可能有重复内容。
   - 建议：只保留一个目录作为样例，另一个改为 `.gitignore` 管理。

3. `.claude/`、`opencode.json`、`oh-my-openagent.jsonc`
   - 现状：偏本地代理工具配置。
   - 建议：若面向通用开源用户，考虑迁移到 `docs/tooling/` 或在 README 增加用途说明。
