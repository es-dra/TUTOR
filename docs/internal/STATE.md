# TUTOR 状态管理文档

## 1. 状态管理概述

TUTOR系统使用状态机来管理各个工作流的执行过程。每个工作流都有明确的开始、中间状态和结束状态，确保：
- 状态转换合法且可追踪
- 支持断点续传（从最近检查点恢复）
- 异常状态可诊断和恢复

---

## 2. 工作流状态机定义

### 2.1 Idea生成工作流 (IdeaFlow)

#### 状态枚举
```python
class IdeaFlowState(Enum):
    INIT = "init"                       # 初始化
    LOADING_PAPERS = "loading_papers"   # 加载参考文献
    DEBATE_ROUND_1 = "debate_1"        # 第一轮辩论
    DEEP_THINKING = "deep_thinking"    # 深度思考
    DEBATE_ROUND_2 = "debate_2"        # 第二轮辩论
    IDEA_GENERATION = "generating"     # Idea池生成
    EVALUATION = "evaluation"          # 导师审批
    SORTING = "sorting"                # 综合排序
    COMPLETED = "completed"            # 完成
    FAILED = "failed"                  # 失败
```

#### 状态转换图
```
[INIT] → [LOADING_PAPERS] → [DEBATE_ROUND_1] → [DEEP_THINKING]
                                           ↓
                                    [DEBATE_ROUND_2]
                                           ↓
                                    [IDEA_GENERATION]
                                           ↓
                                      [EVALUATION]
                                           ↓
                                       [SORTING]
                                           ↓
                                      [COMPLETED]

任意状态 → [FAILED]  (异常触发)
```

#### 状态数据模型
```python
@dataclass
class IdeaFlowStateData:
    workflow_id: str
    project_id: str
    current_state: IdeaFlowState
    inputs: dict  # 初始输入（研究方向、参考文献等）
    intermediate_results: dict  # 各步骤中间结果
    debate_history: list  # 辩论记录
    ideas: list  # 生成的idea列表
    scores: dict  # 评分结果
    started_at: datetime
    last_checkpoint: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
```

---

### 2.2 实验工作流 (ExperimentFlow)

#### 状态枚举
```python
class ExperimentFlowState(Enum):
    INIT = "init"
    ENV_CHECK = "env_check"           # 环境检测
    CODE_DOWNLOAD = "code_download"   # 代码获取
    DEPENDENCIES_INSTALL = "install"  # 依赖安装
    RUNNING = "running"               # 实验执行
    ANALYSIS = "analysis"             # 结果分析
    COMPARISON = "comparison"         # 对比评估
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    FAILED = "failed"
```

#### 状态转换
```
[INIT] → [ENV_CHECK] → [CODE_DOWNLOAD] → [DEPENDENCIES_INSTALL]
                                              ↓
                                        [RUNNING]
                                              ↓
                                        [ANALYSIS]
                                              ↓
                                        [COMPARISON]
                                              ↓
                                        [COMPLETED]

[RUNNING] --超时→ [TIMEOUT]
任意状态 --异常→ [FAILED]
```

#### 状态数据模型
```python
@dataclass
class ExperimentFlowStateData:
    workflow_id: str
    project_id: str
    idea_id: str
    current_state: ExperimentFlowState
    config: dict  # 实验配置
    env_info: dict  # 环境信息（Python版本、GPU等）
    code_source: str  # 代码来源（GitHub URL等）
    logs: list  # 日志片段
    metrics: dict  # 性能指标
    plots: list  # 图表文件路径
    started_at: datetime
    last_checkpoint: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
```

---

### 2.3 论文审核工作流 (ReviewFlow)

#### 状态枚举
```python
class ReviewFlowState(Enum):
    INIT = "init"
    THEORETICAL_REVIEW = "theoretical"   # 理论导师审核
    ENGINEERING_REVIEW = "engineering"   # 工程导师审核
    ACADEMIC_REVIEW = "academic"         # 学术导师审核
    AGGREGATING = "aggregating"         # 汇总反馈
    COMPLETED = "completed"
    FAILED = "failed"
```

#### 状态转换
```
[INIT] → [THEORETICAL_REVIEW] → [ENGINEERING_REVIEW] → [ACADEMIC_REVIEW]
                                                          ↓
                                                    [AGGREGATING]
                                                          ↓
                                                    [COMPLETED]
```

#### 状态数据模型
```python
@dataclass
class ReviewFlowStateData:
    workflow_id: str
    project_id: str
    paper_id: str
    current_state: ReviewFlowState
    reviews: dict  # 各角色审核报告
    aggregated_feedback: dict  # 汇总反馈
    scores: dict  # 各维度评分
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
```

---

### 2.4 论文撰写工作流 (WriteFlow)

#### 状态枚举
```python
class WriteFlowState(Enum):
    INIT = "init"
    OUTLINE_GENERATION = "outline"     # 大纲生成
    DRAFT_WRITING = "drafting"        # 初稿撰写
    FORMAT_CHECK = "format_check"     # 格式检查
    EXPERT_REVIEW = "expert_review"   # 专家审核
    LANGUAGE_POLISH = "polish"        # 语言润色
    PLAGIARISM_CHECK = "plagiarism"  # 查重检测（MVP跳过）
    FINAL_REVIEW = "final_review"     # 最终审核
    COMPLETED = "completed"
    FAILED = "failed"
```

#### 状态转换
```
[INIT] → [OUTLINE_GENERATION] → [DRAFT_WRITING] → [FORMAT_CHECK]
                                                ↓
                                          [EXPERT_REVIEW]
                                                ↓
                                          [LANGUAGE_POLISH]
                                                ↓
                                          [FINAL_REVIEW]
                                                ↓
                                          [COMPLETED]
```

#### 状态数据模型
```python
@dataclass
class WriteFlowStateData:
    workflow_id: str
    project_id: str
    experiment_id: str
    current_state: WriteFlowState
    outline: dict  # 论文大纲
    sections: dict  # 各章节内容
    format_issues: list  # 格式问题
    reviews: list  # 审核意见
    final_version: str  # 最终版本路径
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
```

---

## 3. 状态持久化

### 3.1 存储位置
```
projects/{project_id}/
├── workflow_states/
│   ├── idea_{id}.json
│   ├── experiment_{id}.json
│   ├── review_{id}.json
│   └── write_{id}.json
├── checkpoints/
│   ├── idea_{id}_ckpt_001.json
│   └── ...
└── (其他数据文件)
```

### 3.2 序列化格式
- 使用JSON格式，便于人类阅读和调试
- 包含完整状态数据（inputs、intermediate_results等）
- 每次状态变更立即写入文件

### 3.3 检查点策略
- 每个主要步骤完成后创建检查点
- 检查点命名：`{workflow_id}_ckpt_{step_index}_{timestamp}.json`
- 保留最近5个检查点，自动清理旧检查点

---

## 4. 状态恢复机制

### 4.1 自动恢复
当工作流异常中断后，下次启动时：
1. 查找最新的检查点文件
2. 加载状态数据，恢复 `current_state`
3. 从失败或中断的步骤继续执行
4. 记录恢复日志

### 4.2 手动恢复
```bash
# 查看工作流状态
tutor status --workflow <id>

# 从指定检查点恢复
tutor resume --checkpoint <ckpt_file>
```

### 4.3 恢复策略
- **可恢复错误**（网络超时、API限流）：自动重试并恢复
- **不可恢复错误**（配置错误、数据损坏）：停止并提示用户手动干预
- **用户主动停止**：保存当前状态，等待用户手动恢复

---

## 5. 状态监控

### 5.1 CLI状态查看
```bash
# 查看项目所有工作流状态
tutor project status <project_id>

# 查看具体工作流详情
tutor workflow status <workflow_id>
```

输出示例：
```
工作流: IdeaFlow-abc123
状态: DEBATE_ROUND_1 (进行中)
启动时间: 2026-03-18 10:30:00
最后检查点: 2026-03-18 10:32:15 (DEBATE_ROUND_1)
已生成Idea: 3/10
预计剩余时间: ~2分钟
```

### 5.2 Web仪表盘（MVP延后）
- 实时显示各工作流状态
- 可视化进度条
- 查看检查点快照

---

## 6. 状态转换规则

### 6.1 转换约束
| 当前状态 | 允许的下一个状态 | 条件 |
|---------|----------------|------|
| INIT | LOADING_PAPERS | 输入有效 |
| LOADING_PAPERS | DEBATE_ROUND_1 | 文献加载成功 |
| DEBATE_ROUND_1 | DEEP_THINKING | 辩论完成 |
| DEBATE_ROUND_1 | DEBATE_ROUND_1 | 需要额外辩论轮次（MVP不支持） |
| DEEP_THINKING | DEBATE_ROUND_2 | 思考完成 |
| ... | ... | ... |
| 任意状态 | FAILED | 发生不可恢复错误 |

### 6.2 非法转换处理
- 拒绝非法状态转换，抛出 `InvalidStateTransitionError`
- 记录转换尝试和拒绝原因
- CLI输出清晰错误信息，提示可用操作

---

## 7. 状态数据清理

### 7.1 自动清理策略
- 已完成的工作流状态保留30天
- 失败的工作流状态保留7天（供调试）
- 检查点保留最近5个，旧检查点自动删除

### 7.2 手动清理
```bash
# 清理指定项目的工作流状态
tutor cleanup --project <project_id> --days 30

# 清理所有失败的workflow
tutor cleanup --failed-only
```

---

*文档版本：v1.0-MVP*
*更新日期：2026-03-18*
