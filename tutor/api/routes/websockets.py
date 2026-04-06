"""WebSocket Routes - 角色实时互动

提供WebSocket端点，支持多角色实时对话和协作。
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel, Field

from tutor.core.project.v3_project import (
    Project,
    ProjectManager,
    RoleMessage,
    MessageType,
    get_role_by_id,
    DEFAULT_ROLES,
)
from tutor.core.project.role_orchestrator import RoleOrchestrator
from tutor.core.model import ModelGateway

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ws", tags=["websockets"])


class ConnectionManager:
    """WebSocket连接管理器
    
    管理多个项目的WebSocket连接，支持多客户端订阅。
    """
    
    def __init__(self):
        # project_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # project_id -> RoleOrchestrator
        self.active_orchestrators: Dict[str, RoleOrchestrator] = {}
    
    async def connect(self, project_id: str, websocket: WebSocket):
        """连接到项目"""
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = set()
        self.active_connections[project_id].add(websocket)
        logger.info(f"WebSocket connected to project {project_id}")
    
    def disconnect(self, project_id: str, websocket: WebSocket):
        """断开连接"""
        if project_id in self.active_connections:
            self.active_connections[project_id].discard(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        logger.info(f"WebSocket disconnected from project {project_id}")
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """发送个人消息"""
        await websocket.send_json(message)
    
    async def broadcast_to_project(self, project_id: str, message: Dict[str, Any]):
        """向项目所有连接广播消息"""
        if project_id not in self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections[project_id]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        # 清理断开的连接
        for connection in disconnected:
            self.disconnect(project_id, connection)
    
    def get_orchestrator(self, project_id: str) -> Optional[RoleOrchestrator]:
        """获取项目的角色编排器"""
        return self.active_orchestrators.get(project_id)
    
    def set_orchestrator(self, project_id: str, orchestrator: RoleOrchestrator):
        """设置项目的角色编排器"""
        self.active_orchestrators[project_id] = orchestrator
    
    def remove_orchestrator(self, project_id: str):
        """移除项目的角色编排器"""
        if project_id in self.active_orchestrators:
            del self.active_orchestrators[project_id]


# 全局连接管理器
manager = ConnectionManager()

# 全局项目管理器和模型网关（延迟初始化）
_project_manager: Optional[ProjectManager] = None
_model_gateway: Optional[ModelGateway] = None


def get_project_manager() -> ProjectManager:
    """获取项目管理器"""
    global _project_manager
    if _project_manager is None:
        from pathlib import Path
        storage_path = Path.cwd() / "data"
        _project_manager = ProjectManager(storage_path)
    return _project_manager


def get_model_gateway() -> ModelGateway:
    """获取模型网关"""
    global _model_gateway
    if _model_gateway is None:
        from tutor.api.routes.projects import get_model_gateway_config
        config = get_model_gateway_config()
        _model_gateway = ModelGateway(config)
    return _model_gateway


class ClientMessage(BaseModel):
    """客户端消息"""
    type: str = Field(..., description="消息类型")
    data: Dict[str, Any] = Field(default_factory=dict, description="消息数据")


class ServerMessage(BaseModel):
    """服务端消息"""
    type: str = Field(..., description="消息类型")
    data: Dict[str, Any] = Field(default_factory=dict, description="消息数据")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z")


@router.websocket("/projects/{project_id}")
async def websocket_project_endpoint(websocket: WebSocket, project_id: str):
    """项目WebSocket端点
    
    支持的客户端消息类型：
    - JOIN_PROJECT: 加入项目
    - SEND_MESSAGE: 发送用户消息
    - START_DEBATE: 启动角色辩论
    - STOP_DEBATE: 停止角色辩论
    - GET_HISTORY: 获取历史消息
    
    服务端广播消息类型：
    - ROLE_THINKING: 角色思考中
    - ROLE_SPOKE: 角色发言
    - USER_MESSAGE: 用户消息
    - DEBATE_STARTED: 辩论已开始
    - DEBATE_STOPPED: 辩论已停止
    - HISTORY: 历史消息
    - ERROR: 错误
    """
    await manager.connect(project_id, websocket)
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            
            try:
                client_msg = ClientMessage(**data)
                await handle_client_message(websocket, project_id, client_msg)
            except Exception as e:
                logger.error(f"Failed to handle message: {e}")
                error_msg = ServerMessage(
                    type="ERROR",
                    data={"message": str(e)}
                )
                await manager.send_personal_message(error_msg.dict(), websocket)
    
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(project_id, websocket)


async def handle_client_message(websocket: WebSocket, project_id: str, message: ClientMessage):
    """处理客户端消息"""
    msg_type = message.type.upper()
    
    if msg_type == "JOIN_PROJECT":
        await handle_join_project(websocket, project_id, message.data)
    elif msg_type == "SEND_MESSAGE":
        await handle_send_message(websocket, project_id, message.data)
    elif msg_type == "START_DEBATE":
        await handle_start_debate(websocket, project_id, message.data)
    elif msg_type == "STOP_DEBATE":
        await handle_stop_debate(websocket, project_id, message.data)
    elif msg_type == "GET_HISTORY":
        await handle_get_history(websocket, project_id, message.data)
    elif msg_type == "GET_ROLES":
        await handle_get_roles(websocket, project_id, message.data)
    else:
        raise ValueError(f"Unknown message type: {msg_type}")


async def handle_join_project(websocket: WebSocket, project_id: str, data: Dict[str, Any]):
    """处理加入项目"""
    project_mgr = get_project_manager()
    project = project_mgr.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 发送项目信息
    response = ServerMessage(
        type="PROJECT_JOINED",
        data={
            "project": project.to_dict(),
            "roles": [role.__dict__ for role in DEFAULT_ROLES]
        }
    )
    await manager.send_personal_message(response.dict(), websocket)


async def handle_send_message(websocket: WebSocket, project_id: str, data: Dict[str, Any]):
    """处理发送用户消息"""
    content = data.get("content", "")
    if not content:
        raise ValueError("Content is required")
    
    # 创建用户消息
    user_msg = RoleMessage(
        project_id=project_id,
        role_id="user",
        content=content,
        message_type=MessageType.SPEAK,
        metadata={
            "role_color": "#667EEA",
            "role_emoji": "👤"
        }
    )
    
    # 保存到项目
    project_mgr = get_project_manager()
    project = project_mgr.get_project(project_id)
    if project:
        project.add_role_message(user_msg)
        project_mgr.update_project(project)
    
    # 广播给所有连接
    response = ServerMessage(
        type="USER_MESSAGE",
        data=user_msg.to_dict()
    )
    await manager.broadcast_to_project(project_id, response.dict())


async def handle_start_debate(websocket: WebSocket, project_id: str, data: Dict[str, Any]):
    """处理启动辩论"""
    topic = data.get("topic", "")
    max_rounds = data.get("max_rounds", 3)
    
    if not topic:
        raise ValueError("Topic is required")
    
    # 获取项目
    project_mgr = get_project_manager()
    project = project_mgr.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 检查是否已有辩论在进行
    existing_orchestrator = manager.get_orchestrator(project_id)
    if existing_orchestrator:
        raise ValueError("Debate already in progress")
    
    # 创建角色编排器
    model_gateway = get_model_gateway()
    
    def on_message(msg: RoleMessage):
        """消息回调 - 广播给所有连接"""
        msg_type = "ROLE_THINKING" if msg.message_type == MessageType.THINK else "ROLE_SPOKE"
        response = ServerMessage(
            type=msg_type,
            data=msg.to_dict()
        )
        asyncio.create_task(manager.broadcast_to_project(project_id, response.dict()))
    
    orchestrator = RoleOrchestrator(
        project=project,
        model_gateway=model_gateway,
        on_message_callback=on_message
    )
    
    manager.set_orchestrator(project_id, orchestrator)
    
    # 广播辩论开始
    start_response = ServerMessage(
        type="DEBATE_STARTED",
        data={"topic": topic, "max_rounds": max_rounds}
    )
    await manager.broadcast_to_project(project_id, start_response.dict())
    
    # 在后台运行辩论
    async def run_debate():
        try:
            messages = orchestrator.start_debate(topic, max_rounds)
            
            # 保存到项目
            project_mgr.update_project(project)
            
            # 广播辩论完成
            complete_response = ServerMessage(
                type="DEBATE_COMPLETED",
                data={"message_count": len(messages)}
            )
            await manager.broadcast_to_project(project_id, complete_response.dict())
        except Exception as e:
            logger.error(f"Debate error: {e}")
            error_response = ServerMessage(
                type="ERROR",
                data={"message": str(e)}
            )
            await manager.broadcast_to_project(project_id, error_response.dict())
        finally:
            manager.remove_orchestrator(project_id)
    
    asyncio.create_task(run_debate())


async def handle_stop_debate(websocket: WebSocket, project_id: str, data: Dict[str, Any]):
    """处理停止辩论"""
    orchestrator = manager.get_orchestrator(project_id)
    if orchestrator:
        orchestrator.stop()
        manager.remove_orchestrator(project_id)
        
        response = ServerMessage(
            type="DEBATE_STOPPED",
            data={}
        )
        await manager.broadcast_to_project(project_id, response.dict())


async def handle_get_history(websocket: WebSocket, project_id: str, data: Dict[str, Any]):
    """处理获取历史消息"""
    project_mgr = get_project_manager()
    project = project_mgr.get_project(project_id)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    response = ServerMessage(
        type="HISTORY",
        data={
            "messages": [msg.to_dict() for msg in project.role_conversations]
        }
    )
    await manager.send_personal_message(response.dict(), websocket)


async def handle_get_roles(websocket: WebSocket, project_id: str, data: Dict[str, Any]):
    """处理获取角色列表"""
    response = ServerMessage(
        type="ROLES",
        data={
            "roles": [
                {
                    "id": role.id,
                    "name": role.name,
                    "emoji": role.emoji,
                    "color": role.color,
                    "persona": role.persona,
                    "goal": role.goal
                }
                for role in DEFAULT_ROLES
            ]
        }
    )
    await manager.send_personal_message(response.dict(), websocket)

