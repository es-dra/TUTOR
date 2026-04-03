# V3 生产就绪发布计划 (Updated 2026-03-25)

## 1. 质量加固 (QA & Testing)
- [x] ExperimentFlow 环境检测测试 (22%)
- [x] ReviewFlow 全链路测试 (90%)
- [ ] WriteFlow 章节生成测试 (Target: 50%)
- [ ] SSE 事件推送集成测试 (TestClient)

## 2. 功能增强 (Enhancements)
- [x] Python 3.13 兼容性修复 (Standardized timezone.utc)
- [x] PAUSE 熔断机制 (Fatal resource limit triggers PAUSE)
- [x] Vacuum 清理命令 (StorageManager.vacuum)
- [ ] Web UI 交互: 增加 "Resume from PAUSE" API 接口

## 3. 部署优化 (DevOps)
- [ ] 优化 Dockerfile.latex (Layer caching for faster builds)
- [ ] 验证 PostgreSQL/Redis 生产堆栈连接
- [ ] 编写 ADMIN_GUIDE.md (监控告警与数据迁移)

## 4. 改进空间
- 异步化: 考虑将 ExperimentFlow.run 改为异步，防止阻塞 API 事件循环。
- 插件市场: 开放 FigureGenerationStep 的自定义模板接口。
