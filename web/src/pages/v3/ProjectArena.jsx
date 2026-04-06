import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Brain, FlaskConical, PenTool, SearchCheck, Users, MessageSquare, Activity, Zap, Shield, ChevronRight, ChevronLeft, X, RefreshCw } from 'lucide-react';
import api from '../../api.js';

function ProjectArena() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [debateState, setDebateState] = useState({
    messages: [],
    isRunning: false,
    currentRole: null,
    progress: 0
  });
  const [workflowState, setWorkflowState] = useState({
    steps: [
      { id: 'idea', name: 'Idea生成', status: 'pending', icon: Brain },
      { id: 'experiment', name: '实验设计', status: 'pending', icon: FlaskConical },
      { id: 'writing', name: '论文撰写', status: 'pending', icon: PenTool },
      { id: 'review', name: '论文评审', status: 'pending', icon: SearchCheck }
    ],
    currentStep: null
  });
  const [roles, setRoles] = useState([
    {
      id: 'innovator',
      name: 'Innovator',
      avatar: '🎨',
      status: 'idle',
      lastMessage: null,
      color: '#6366F1'
    },
    {
      id: 'skeptic',
      name: 'Skeptic',
      avatar: '🔍',
      status: 'idle',
      lastMessage: null,
      color: '#EF4444'
    },
    {
      id: 'pragmatist',
      name: 'Pragmatist',
      avatar: '🛠️',
      status: 'idle',
      lastMessage: null,
      color: '#10B981'
    },
    {
      id: 'expert',
      name: 'Expert',
      avatar: '📖',
      status: 'idle',
      lastMessage: null,
      color: '#F59E0B'
    }
  ]);
  const [websocket, setWebsocket] = useState(null);
  const [showChat, setShowChat] = useState(false);
  const [userMessage, setUserMessage] = useState('');
  
  const canvasRef = useRef(null);

  useEffect(() => {
    if (projectId) {
      loadProject();
    }
  }, [projectId]);

  useEffect(() => {
    // 创建真实的WebSocket连接
    if (project?.id) {
      const ws = api.createWebSocket(project.id, {
        onOpen: () => {
          console.log('WebSocket connected');
          // 加入项目
          ws.send('JOIN_PROJECT', {});
          // 获取历史消息
          ws.send('GET_HISTORY', {});
          // 获取角色列表
          ws.send('GET_ROLES', {});
        },
        onMessage: (message) => {
          handleWebSocketMessage(message);
        },
        onError: (error) => {
          console.error('WebSocket error:', error);
        },
        onClose: () => {
          console.log('WebSocket disconnected');
        }
      });
      setWebsocket(ws);
      
      return () => {
        if (ws) {
          ws.close();
        }
      };
    }
  }, [project?.id]);

  const loadProject = async () => {
    try {
      const response = await api.getV3Project(projectId);
      setProject(response.data);
    } catch (error) {
      console.error('Failed to load project:', error);
    }
  };

  const handleWebSocketMessage = (message) => {
    switch (message.type) {
      case 'ROLE_THINKING':
        setRoles(prev => prev.map(role => 
          role.id === message.data.role_id 
            ? { ...role, status: 'thinking' }
            : role
        ));
        break;
        
      case 'ROLE_SPOKE':
        setDebateState(prev => ({
          ...prev,
          messages: [...prev.messages, {
            role: message.data.role_id,
            content: message.data.content,
            timestamp: message.data.timestamp
          }]
        }));
        
        setRoles(prev => prev.map(role => 
          role.id === message.data.role_id 
            ? { ...role, status: 'active', lastMessage: message.data.content }
            : { ...role, status: 'listening' }
        ));
        break;
        
      case 'USER_MESSAGE':
        setDebateState(prev => ({
          ...prev,
          messages: [...prev.messages, {
            role: 'user',
            content: message.data.content,
            timestamp: message.data.timestamp
          }]
        }));
        break;
        
      case 'DEBATE_STARTED':
        setDebateState(prev => ({ ...prev, isRunning: true, progress: 0 }));
        break;
        
      case 'DEBATE_COMPLETED':
        setDebateState(prev => ({ ...prev, isRunning: false, currentRole: null }));
        setRoles(prev => prev.map(role => ({ ...role, status: 'idle' })));
        break;
        
      case 'HISTORY':
        if (message.data.messages) {
          setDebateState(prev => ({
            ...prev,
            messages: message.data.messages.map(msg => ({
              role: msg.role_id,
              content: msg.content,
              timestamp: msg.timestamp
            }))
          }));
        }
        break;
        
      case 'ROLES':
        if (message.data.roles) {
          setRoles(message.data.roles.map(role => ({
            id: role.id,
            name: role.name,
            avatar: role.emoji,
            status: 'idle',
            lastMessage: null,
            color: role.color
          })));
        }
        break;
        
      case 'ERROR':
        console.error('WebSocket error:', message.data.message);
        break;
    }
  };

  const startDebate = () => {
    if (websocket) {
      // 通过WebSocket启动辩论
      websocket.send('START_DEBATE', {
        topic: project?.description || 'AI辅助科研工作流优化',
        max_rounds: 3
      });
    }
  };

  const startWorkflow = (stepId) => {
    // 这里可以实现真实的工作流启动逻辑
    setWorkflowState(prev => {
      const newSteps = prev.steps.map(step => 
        step.id === stepId ? { ...step, status: 'running' } : step
      );
      return {
        ...prev,
        steps: newSteps,
        currentStep: stepId
      };
    });

    // 模拟工作流执行
    setTimeout(() => {
      setWorkflowState(prev => {
        const newSteps = prev.steps.map(step => 
          step.id === stepId ? { ...step, status: 'completed' } : step
        );
        return {
          ...prev,
          steps: newSteps,
          currentStep: null
        };
      });
    }, 3000);
  };

  const sendMessage = () => {
    if (!userMessage.trim()) return;
    
    if (websocket) {
      // 通过WebSocket发送消息
      websocket.send('SEND_MESSAGE', {
        content: userMessage
      });
    }
    
    setUserMessage('');
  };

  const getStatusColor = (status) => {
    const colors = {
      running: '#3B82F6',
      completed: '#10B981',
      pending: '#6B7280',
      failed: '#EF4444'
    };
    return colors[status] || '#6B7280';
  };

  const getRoleStatusColor = (status) => {
    const colors = {
      active: '#10B981',
      listening: '#3B82F6',
      thinking: '#F59E0B',
      idle: '#6B7280'
    };
    return colors[status] || '#6B7280';
  };

  return (
    <div className="project-arena">
      {/* Header */}
      <div className="arena-header">
        <div className="header-left">
          <button 
            className="btn btn-ghost btn-icon" 
            onClick={() => navigate('/')}
            style={{ marginRight: '1rem' }}
          >
            <ChevronLeft size={20} />
          </button>
          <div>
            <h1 className="arena-title">{project?.name || 'Project Arena'}</h1>
            {project?.description && (
              <p className="arena-subtitle">{project.description}</p>
            )}
          </div>
        </div>
        <div className="header-right">
          <button 
            className="btn btn-secondary" 
            style={{ marginRight: '0.75rem' }}
          >
            <RefreshCw size={16} />
            刷新
          </button>
          <button className="btn btn-primary">
            <Zap size={16} />
            运行工作流
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="arena-tabs">
        <button 
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <Activity size={18} />
          概览
        </button>
        <button 
          className={`tab ${activeTab === 'workflow' ? 'active' : ''}`}
          onClick={() => setActiveTab('workflow')}
        >
          <FlaskConical size={18} />
          工作流
        </button>
        <button 
          className={`tab ${activeTab === 'debate' ? 'active' : ''}`}
          onClick={() => setActiveTab('debate')}
        >
          <MessageSquare size={18} />
          多角色辩论
        </button>
        <button 
          className={`tab ${activeTab === 'team' ? 'active' : ''}`}
          onClick={() => setActiveTab('team')}
        >
          <Users size={18} />
          角色管理
        </button>
      </div>

      {/* Content */}
      <div className="arena-content">
        {activeTab === 'overview' && (
          <div className="overview-section">
            {/* Project Stats */}
            <div className="stats-grid">
              <div className="stat-card primary">
                <div className="stat-icon">
                  <Brain size={24} />
                </div>
                <div className="stat-value">{project?.id || 'N/A'}</div>
                <div className="stat-label">项目ID</div>
              </div>
              <div className="stat-card success">
                <div className="stat-icon">
                  <SearchCheck size={24} />
                </div>
                <div className="stat-value">
                  {workflowState.steps.filter(s => s.status === 'completed').length}
                </div>
                <div className="stat-label">已完成步骤</div>
              </div>
              <div className="stat-card warning">
                <div className="stat-icon">
                  <Activity size={24} />
                </div>
                <div className="stat-value">
                  {workflowState.steps.filter(s => s.status === 'running').length}
                </div>
                <div className="stat-label">进行中</div>
              </div>
              <div className="stat-card danger">
                <div className="stat-icon">
                  <Shield size={24} />
                </div>
                <div className="stat-value">4</div>
                <div className="stat-label">AI角色</div>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="quick-actions">
              <h3>快速操作</h3>
              <div className="action-buttons">
                <button className="btn btn-primary" onClick={startDebate}>
                  <MessageSquare size={16} />
                  开始多角色辩论
                </button>
                <button className="btn btn-secondary">
                  <PenTool size={16} />
                  生成论文大纲
                </button>
                <button className="btn btn-secondary">
                  <FlaskConical size={16} />
                  设计实验
                </button>
              </div>
            </div>

            {/* Workflow Progress */}
            <div className="workflow-progress">
              <h3>工作流进度</h3>
              <div className="step-timeline">
                {workflowState.steps.map((step, index) => {
                  const Icon = step.icon;
                  return (
                    <div key={step.id} className="step-item">
                      <div className="step-connector">
                        <div 
                          className={`step-icon ${step.status === 'completed' ? 'completed' : step.status === 'running' ? 'current' : 'pending'}`}
                        >
                          <Icon size={16} />
                        </div>
                        {index < workflowState.steps.length - 1 && (
                          <div className={`step-line ${step.status === 'completed' ? '' : 'pending'}`} />
                        )}
                      </div>
                      <div className="step-content">
                        <div className="step-name">
                          {step.name}
                          <span 
                            className={`step-status ${step.status}`}
                            style={{ backgroundColor: `${getStatusColor(step.status)}20`, color: getStatusColor(step.status) }}
                          >
                            {step.status === 'running' ? '运行中' : step.status === 'completed' ? '已完成' : '待开始'}
                          </span>
                        </div>
                        {step.status === 'pending' && (
                          <button 
                            className="btn btn-sm btn-secondary" 
                            style={{ marginTop: '0.5rem' }}
                            onClick={() => startWorkflow(step.id)}
                          >
                            开始
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'workflow' && (
          <div className="workflow-section">
            <h3>工作流管理</h3>
            <div className="workflow-cards">
              {workflowState.steps.map(step => {
                const Icon = step.icon;
                return (
                  <div key={step.id} className="workflow-card">
                    <div className="workflow-card-header">
                      <div className="workflow-type">
                        <Icon size={16} />
                        &nbsp;{step.name}
                      </div>
                      <span 
                        className="status-badge-workflow"
                        style={{ backgroundColor: `${getStatusColor(step.status)}20`, color: getStatusColor(step.status) }}
                      >
                        {step.status === 'running' ? '运行中' : step.status === 'completed' ? '已完成' : '待开始'}
                      </span>
                    </div>
                    <div className="workflow-card-body">
                      <p>这是{step.name}工作流的详细描述。</p>
                      {step.status === 'pending' && (
                        <button 
                          className="btn btn-primary" 
                          style={{ marginTop: '1rem' }}
                          onClick={() => startWorkflow(step.id)}
                        >
                          开始工作流
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {activeTab === 'debate' && (
          <div className="debate-section">
            <div className="debate-header">
              <h3>多角色辩论</h3>
              <button 
                className="btn btn-primary" 
                onClick={startDebate}
                disabled={debateState.isRunning}
              >
                {debateState.isRunning ? '辩论中...' : '开始辩论'}
              </button>
            </div>
            
            {debateState.isRunning && (
              <div className="debate-progress">
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar" 
                    style={{ width: `${debateState.progress}%` }}
                  />
                  <span className="progress-text">{Math.round(debateState.progress)}%</span>
                </div>
                {debateState.currentRole && (
                  <p className="current-speaker">
                    当前发言: {roles.find(r => r.id === debateState.currentRole)?.name}
                  </p>
                )}
              </div>
            )}

            <div className="debate-messages">
              {debateState.messages.map((msg, index) => {
                const roleInfo = roles.find(r => r.id === msg.role) || { name: '用户', avatar: '👤', color: '#6B7280' };
                return (
                  <div key={index} className="message-item">
                    <div className="message-avatar" style={{ backgroundColor: `${roleInfo.color}20`, color: roleInfo.color }}>
                      {roleInfo.avatar}
                    </div>
                    <div className="message-content">
                      <div className="message-header">
                        <span className="message-author">{roleInfo.name}</span>
                        <span className="message-time">
                          {new Date(msg.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <div className="message-text">{msg.content}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="message-input">
              <input
                type="text"
                className="form-input"
                value={userMessage}
                onChange={e => setUserMessage(e.target.value)}
                placeholder="输入您的观点..."
                onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
              />
              <button 
                className="btn btn-primary"
                onClick={sendMessage}
                disabled={!userMessage.trim()}
              >
                发送
              </button>
            </div>
          </div>
        )}

        {activeTab === 'team' && (
          <div className="team-section">
            <h3>AI角色管理</h3>
            <div className="roles-grid">
              {roles.map(role => (
                <div key={role.id} className="role-card">
                  <div className="role-header">
                    <div 
                      className="role-avatar" 
                      style={{ backgroundColor: `${role.color}20`, color: role.color }}
                    >
                      {role.avatar}
                    </div>
                    <div className="role-info">
                      <h4>{role.name}</h4>
                      <div className="role-status">
                        <span 
                          className="status-dot" 
                          style={{ backgroundColor: getRoleStatusColor(role.status) }}
                        />
                        {role.status === 'active' ? '活跃' : role.status === 'listening' ? '倾听中' : '空闲'}
                      </div>
                    </div>
                  </div>
                  {role.lastMessage && (
                    <div className="role-last-message">
                      <p>{role.lastMessage}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Floating Chat Button */}
      <button 
        className="floating-chat-btn"
        onClick={() => setShowChat(!showChat)}
      >
        <MessageSquare size={20} />
      </button>

      {/* Chat Panel */}
      {showChat && (
        <div className="chat-panel">
          <div className="chat-header">
            <h4>实时对话</h4>
            <button 
              className="btn btn-ghost btn-icon"
              onClick={() => setShowChat(false)}
            >
              <X size={16} />
            </button>
          </div>
          <div className="chat-messages">
            {debateState.messages.slice(-5).map((msg, index) => {
              const roleInfo = roles.find(r => r.id === msg.role) || { name: '用户', avatar: '👤' };
              return (
                <div key={index} className="chat-message-item">
                  <div className="chat-avatar">{roleInfo.avatar}</div>
                  <div className="chat-message-content">
                    <div className="chat-author">{roleInfo.name}</div>
                    <div className="chat-text">{msg.content}</div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="chat-input">
            <input
              type="text"
              className="form-input"
              value={userMessage}
              onChange={e => setUserMessage(e.target.value)}
              placeholder="输入消息..."
              onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
            />
            <button 
              className="btn btn-primary"
              onClick={sendMessage}
              disabled={!userMessage.trim()}
            >
              发送
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default ProjectArena;
