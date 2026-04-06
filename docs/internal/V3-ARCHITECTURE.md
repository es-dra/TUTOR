# TUTOR v3 架构设计 - Project驱动的多角色协作平台

## 1. 核心概念

### 1.1 Project（科研项目）
**Project** 是TUTOR v3的核心概念，统一管理：
- Idea生成
- Experiment执行
- Paper撰写
- Review评审

### 1.2 多角色系统（特色功能）
可视化科研协作角色，实时互动：
- **Innovator** 🎨 创新者 - 提出创意，突破思维
- **Skeptic** 🔍 质疑者 - 挑战假设，识别风险
- **Pragmatist** 🛠️ 实践者 - 评估可行性，关注落地
- **Expert** 📚 领域专家 - 提供专业知识，关联文献
- **Synthesizer** 🔗 综合者 - 整合各方观点，形成最终方案

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TUTOR v3 - 用户界面层                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                   多角色实时协作 UI (React + WebSocket)         │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │  │
│  │  │ Project Hub  │  │ Roles Arena  │  │ Workflow View│        │  │
│  │  │ (项目管理)   │  │ (角色互动)   │  │ (工作流视图)  │        │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│                         WebSocket/SSE 层                              │
│         ┌──────────────────────────────────────────────┐              │
│         │  角色实时消息广播 | 工作流状态推送          │              │
│         └──────────────────────────────────────────────┘              │
├─────────────────────────────────────────────────────────────────────────┤
│                        应用核心层 (FastAPI)                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │  Project Manager│  │  Role Orchestrator│  │  Workflow Engine │   │
│  │  (项目管理)     │  │  (角色编排)     │  │  (工作流引擎)   │   │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘   │
├─────────────────────────────────────────────────────────────────────────┤
│                        服务层                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │ ModelGateway│  │StorageManager│  │Token Tracker │  │Ext Tools │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

## 3. Project数据模型

```python
class Project:
    id: str
    name: str
    description: str
    status: ProjectStatus  # (IDEA, EXPERIMENT, WRITING, REVIEW, COMPLETED)
    created_at: datetime
    updated_at: datetime
    
    # 关联的工作流
    idea: Optional[Idea]
    experiment: Optional[Experiment]
    paper: Optional[Paper]
    reviews: List[Review]
    
    # 角色对话历史
    role_conversations: List[RoleMessage]
    
    # 元数据
    metadata: Dict[str, Any]
```

## 4. 多角色系统

### 4.1 角色定义

```python
@dataclass
class ResearchRole:
    id: str
    name: str
    emoji: str
    color: str
    persona: str
    goal: str
    model_config: str

# 预定义角色
ROLES = [
    ResearchRole(
        id="innovator",
        name="创新者",
        emoji="🎨",
        color="#FF6B6B",
        persona="创意无限的研究者，喜欢探索新颖想法和突破性方法",
        goal="提出创新且雄心勃勃的研究想法",
        model_config="gpt-4o"
    ),
    ResearchRole(
        id="skeptic",
        name="质疑者",
        emoji="🔍",
        color="#4ECDC4",
        persona="批判性思考者，挑战假设并识别潜在缺陷",
        goal="批评想法并识别风险或弱点",
        model_config="claude-3-opus"
    ),
    ResearchRole(
        id="pragmatist",
        name="实践者",
        emoji="🛠️",
        color="#45B7D1",
        persona="务实的研究者，专注于可行性和实施",
        goal="评估可行性并提出实用改进",
        model_config="gemini-2.5-pro"
    ),
    ResearchRole(
        id="expert",
        name="专家",
        emoji="📚",
        color="#96CEB4",
        persona="领域专家，具有深厚的专业知识",
        goal="确保想法基于当前研究并识别相关文献",
        model_config="claude-3-sonnet"
    ),
    ResearchRole(
        id="synthesizer",
        name="综合者",
        emoji="🔗",
        color="#FFEAA7",
        persona="综合各方观点，形成最终方案",
        goal="整合所有角色的最佳观点，形成一致的方案",
        model_config="gpt-4o"
    )
]
```

### 4.2 角色实时消息

```python
@dataclass
class RoleMessage:
    id: str
    project_id: str
    role_id: str
    content: str
    timestamp: datetime
    message_type: str  # (THINK, SPEAK, REACT, PROPOSE)
    metadata: Dict[str, Any]
```

## 5. WebSocket/SSE事件

```typescript
// 客户端事件
type ClientEvent = 
  | { type: 'JOIN_PROJECT'; projectId: string }
  | { type: 'SEND_MESSAGE'; roleId: string; content: string }
  | { type: 'START_WORKFLOW'; workflowType: string }
  | { type: 'INTERRUPT_ROLE'; roleId: string }

// 服务端事件
type ServerEvent =
  | { type: 'ROLE_THINKING'; roleId: string }
  | { type: 'ROLE_SPOKE'; message: RoleMessage }
  | { type: 'WORKFLOW_STATUS'; status: WorkflowStatus }
  | { type: 'PROJECT_UPDATED'; project: Project }
  | { type: 'ERROR'; message: string }
```

## 6. UI设计原则

### 6.1 视觉风格
- **现代化**：卡片式布局、平滑动画、渐变色彩
- **专业科研**：清晰的数据展示、图表可视化、引用格式
- **角色特色**：每个角色有独特的颜色和动画

### 6.2 核心界面
1. **Project Hub** - 项目仪表盘，展示所有项目
2. **Roles Arena** - 多角色实时互动舞台
3. **Workflow View** - 工作流执行视图
4. **Paper Editor** - 论文编辑器

## 7. 工作流串联

```
Project (新项目)
    ↓
IdeaFlow + 多角色辩论
    ↓ (用户批准)
ExperimentFlow
    ↓ (完成)
WriteFlow
    ↓ (初稿)
ReviewFlow + 多角色评审
    ↓ (修改)
Project COMPLETED
```
