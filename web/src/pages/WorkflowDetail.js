import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, RefreshCw, CheckCircle, XCircle, Clock, AlertCircle, Download, Trash2, Bot, MessageSquare, Sparkles, BookOpen, GitBranch, Play, Search } from 'lucide-react';
import api from '../api';

// 工作流步骤映射
const STEP_NAMES = {
  smart_input: { name: '智能输入处理', icon: <Sparkles size={14} />, color: '#8b5cf6' },
  auto_arxiv_search: { name: '自动文献搜索', icon: <Search size={14} />, color: '#06b6d4' },
  paper_loading: { name: '加载文献', icon: <BookOpen size={14} />, color: '#3b82f6' },
  paper_validation: { name: '验证文献', icon: <CheckCircle size={14} />, color: '#10b981' },
  zotero_literature: { name: 'Zotero补充', icon: <BookOpen size={14} />, color: '#f59e0b' },
  literature_analysis: { name: '文献分析', icon: <Sparkles size={14} />, color: '#8b5cf6' },
  idea_debate: { name: '辩论生成', icon: <MessageSquare size={14} />, color: '#ec4899' },
  idea_evaluation: { name: '想法评估', icon: <Bot size={14} />, color: '#6366f1' },
  final_proposal: { name: '生成提案', icon: <GitBranch size={14} />, color: '#f59e0b' },
  project_gate: { name: '审批门控', icon: <Clock size={14} />, color: '#ef4444' },
};

const WORKFLOW_STEPS_ORDER = [
  'smart_input',
  'auto_arxiv_search',
  'paper_loading',
  'paper_validation',
  'zotero_literature',
  'literature_analysis',
  'idea_debate',
  'idea_evaluation',
  'final_proposal',
  'project_gate',
];

function WorkflowDetail({ runId, onClose }) {
  const [run, setRun] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('progress');
  const [stepStatuses, setStepStatuses] = useState({});
  const eventSourceRef = useRef(null);
  const logsEndRef = useRef(null);

  const loadRun = useCallback(async () => {
    try {
      const data = await api.getRunStatus(runId);
      setRun(data);
      updateStepStatuses(data);
    } catch (error) {
      console.error('加载失败:', error);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  const updateStepStatuses = (runData) => {
    // 根据日志更新步骤状态
    const statuses = {};
    const completedSteps = new Set();

    // 从结果中提取已完成的步骤
    if (runData.result?.steps) {
      runData.result.steps.forEach(step => {
        if (step.status === 'completed') {
          completedSteps.add(step.name);
        }
      });
    }

    // 更新步骤状态
    WORKFLOW_STEPS_ORDER.forEach((stepName, index) => {
      if (completedSteps.has(stepName)) {
        statuses[stepName] = 'completed';
      } else if (index === 0) {
        statuses[stepName] = 'current';
      }
    });

    setStepStatuses(statuses);
  };

  const connectSSE = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const eventSource = api.createEventSource(
      runId,
      (data) => {
        const logEntry = { ...data, timestamp: new Date() };
        setLogs(prev => [...prev, logEntry]);

        // 更新步骤状态
        if (data.type === 'step') {
          const stepName = data.data?.step_name;
          if (stepName && STEP_NAMES[stepName]) {
            setStepStatuses(prev => ({ ...prev, [stepName]: 'completed' }));
            // 设置下一步为当前
            const stepIndex = WORKFLOW_STEPS_ORDER.indexOf(stepName);
            if (stepIndex >= 0 && stepIndex < WORKFLOW_STEPS_ORDER.length - 1) {
              const nextStep = WORKFLOW_STEPS_ORDER[stepIndex + 1];
              setStepStatuses(prev => ({ ...prev, [nextStep]: 'current' }));
            }
          }
        }

        if (data.type === 'llm_call') {
          // LLM调用日志 - 可能是辩论过程
          setStepStatuses(prev => ({ ...prev, idea_debate: 'current' }));
        }

        if (data.type === 'complete' || data.type === 'error') {
          loadRun();
        }
      },
      (error) => {
        console.error('SSE连接错误:', error);
      }
    );

    eventSourceRef.current = eventSource;
  }, [runId, loadRun]);

  useEffect(() => {
    loadRun();
    connectSSE();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [loadRun, connectSSE]);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Auto-refresh when running
  useEffect(() => {
    if (!run || (run.status !== 'pending' && run.status !== 'running')) return;

    const interval = setInterval(() => {
      loadRun();
    }, 5000);

    return () => clearInterval(interval);
  }, [run?.status, runId, loadRun]);

  const handleRefresh = () => {
    setLogs([]);
    loadRun();
    connectSSE();
  };

  const handleCancel = async () => {
    if (!window.confirm('确定要取消此工作流吗？')) return;
    try {
      await fetch(`${process.env.REACT_APP_API_URL || 'http://localhost:8080'}/runs/${runId}`, {
        method: 'DELETE'
      });
      loadRun();
    } catch (error) {
      console.error('取消失败:', error);
    }
  };

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="card">
        <p>未找到工作流</p>
        <button className="btn btn-primary" onClick={onClose}>关闭</button>
      </div>
    );
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0, 0, 0, 0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '2rem'
    }}>
      <div style={{
        background: 'var(--surface)',
        borderRadius: '12px',
        width: '100%',
        maxWidth: '1200px',
        maxHeight: '90vh',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column'
      }}>
        {/* Header */}
        <div style={{
          padding: '1.5rem',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div>
            <h2 style={{ margin: 0 }}>工作流详情</h2>
            <code style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              {runId}
            </code>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {run && (run.status === 'pending' || run.status === 'running') && (
              <button
                className="btn btn-danger"
                onClick={handleCancel}
                title="取消工作流"
              >
                <Trash2 size={18} />
              </button>
            )}
            <button className="btn btn-secondary" onClick={handleRefresh}>
              <RefreshCw size={18} />
            </button>
            <button className="btn btn-secondary" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Status Bar */}
        <div style={{
          padding: '1rem 1.5rem',
          background: run.status === 'running' ? '#dbeafe' : run.status === 'completed' ? '#d1fae5' : '#fee2e2',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem'
        }}>
          <StatusIcon status={run.status} />
          <div>
            <strong>{getStatusText(run.status)}</strong>
            <span style={{ marginLeft: '1rem', color: 'var(--text-secondary)' }}>
              {run.workflow_type} • 开始于 {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
            </span>
          </div>
        </div>

        {/* Tabs */}
        <div className="tabs" style={{ padding: '0 1.5rem' }}>
          <button
            className={`tab ${activeTab === 'progress' ? 'active' : ''}`}
            onClick={() => setActiveTab('progress')}
          >
            <Play size={14} style={{ marginRight: 4 }} />
            进度
          </button>
          <button
            className={`tab ${activeTab === 'logs' ? 'active' : ''}`}
            onClick={() => setActiveTab('logs')}
          >
            日志 {logs.length > 0 && `(${logs.length})`}
          </button>
          {run.result && (
            <button
              className={`tab ${activeTab === 'result' ? 'active' : ''}`}
              onClick={() => setActiveTab('result')}
            >
              结果
            </button>
          )}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'auto', padding: '1.5rem' }}>
          {activeTab === 'progress' && (
            <ProgressView
              stepStatuses={stepStatuses}
              currentStep={Object.entries(stepStatuses).find(([_, s]) => s === 'current')?.[0]}
              run={run}
            />
          )}

          {activeTab === 'logs' && (
            <LogsView logs={logs} logsEndRef={logsEndRef} />
          )}

          {activeTab === 'result' && run.result && (
            <ResultView run={run} runId={runId} />
          )}
        </div>
      </div>
    </div>
  );
}

// 进度视图组件
function ProgressView({ stepStatuses, currentStep, run }) {
  return (
    <div>
      {/* 步骤时间线 */}
      <div className="card">
        <h3 className="card-title">执行进度</h3>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
          marginTop: '1rem'
        }}>
          {WORKFLOW_STEPS_ORDER.map((stepName, index) => {
            const stepInfo = STEP_NAMES[stepName];
            const status = stepStatuses[stepName] || 'pending';
            const isLast = index === WORKFLOW_STEPS_ORDER.length - 1;

            return (
              <div key={stepName} style={{ display: 'flex', alignItems: 'flex-start' }}>
                {/* 连接线 */}
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  marginRight: '1rem'
                }}>
                  {/* 状态图标 */}
                  <div style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: status === 'completed' ? '#10b981' :
                      status === 'current' ? '#3b82f6' : '#e2e8f0',
                    color: status === 'completed' || status === 'current' ? '#fff' : '#94a3b8',
                    transition: 'all 0.3s',
                  }}>
                    {status === 'completed' ? <CheckCircle size={16} /> :
                      status === 'current' ? <div className="spinner" style={{ width: 16, height: 16 }} /> :
                        <Clock size={14} />}
                  </div>
                  {/* 连接线 */}
                  {!isLast && (
                    <div style={{
                      width: '2px',
                      height: '24px',
                      background: status === 'completed' ? '#10b981' : '#e2e8f0',
                    }} />
                  )}
                </div>

                {/* 步骤信息 */}
                <div style={{
                  flex: 1,
                  padding: '0.5rem 0',
                  opacity: status === 'pending' ? 0.5 : 1,
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    color: stepInfo?.color || 'var(--text-primary)'
                  }}>
                    {stepInfo?.icon}
                    <strong>{stepInfo?.name || stepName}</strong>
                    {status === 'current' && (
                      <span style={{
                        fontSize: '0.75rem',
                        padding: '0.125rem 0.5rem',
                        background: '#dbeafe',
                        color: '#1e40af',
                        borderRadius: '9999px'
                      }}>
                        执行中
                      </span>
                    )}
                    {status === 'completed' && (
                      <span style={{
                        fontSize: '0.75rem',
                        padding: '0.125rem 0.5rem',
                        background: '#d1fae5',
                        color: '#065f46',
                        borderRadius: '9999px'
                      }}>
                        已完成
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 当前活动 */}
      {currentStep && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3 className="card-title">当前活动</h3>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '0.75rem',
            background: '#eff6ff',
            borderRadius: '8px',
            marginTop: '0.5rem'
          }}>
            <Bot size={20} style={{ color: '#3b82f6' }} />
            <div>
              <div style={{ fontWeight: 500 }}>
                {STEP_NAMES[currentStep]?.name || currentStep}
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                正在执行中，请稍候...
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// 日志视图组件
function LogsView({ logs, logsEndRef }) {
  return (
    <div className="logs-container" style={{
      background: '#1e293b',
      borderRadius: '8px',
      padding: '1rem',
      maxHeight: '500px',
      overflow: 'auto'
    }}>
      {logs.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '2rem', color: '#94a3b8' }}>
          暂无日志...
        </div>
      ) : (
        logs.map((log, index) => (
          <div
            key={index}
            className="log-entry"
            style={{
              display: 'flex',
              gap: '0.75rem',
              padding: '0.375rem 0',
              borderBottom: '1px solid #334155',
              fontSize: '0.875rem',
            }}
          >
            <span style={{ color: '#64748b', minWidth: '70px' }}>
              {log.timestamp.toLocaleTimeString()}
            </span>
            <span style={{
              padding: '0.125rem 0.5rem',
              borderRadius: '4px',
              fontSize: '0.75rem',
              background: getLogBgColor(log.type),
              color: getLogColor(log.type),
            }}>
              {log.type.toUpperCase()}
            </span>
            <span style={{ color: '#e2e8f0', flex: 1, wordBreak: 'break-word' }}>
              {formatLogData(log.data)}
            </span>
          </div>
        ))
      )}
      <div ref={logsEndRef} />
    </div>
  );
}

// 结果视图组件
function ResultView({ run, runId }) {
  return (
    <div className="card">
      <h3 className="card-title">执行结果</h3>
      <pre style={{
        background: '#1e293b',
        color: '#e2e8f0',
        padding: '1rem',
        borderRadius: '8px',
        overflow: 'auto',
        maxHeight: '400px',
        fontSize: '0.875rem'
      }}>
        {JSON.stringify(run.result, null, 2)}
      </pre>
      <button
        className="btn btn-primary"
        style={{ marginTop: '1rem' }}
        onClick={() => {
          const blob = new Blob([JSON.stringify(run.result, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `result-${runId}.json`;
          a.click();
        }}
      >
        <Download size={18} />
        导出结果
      </button>
    </div>
  );
}

// 辅助函数
function StatusIcon({ status }) {
  const configs = {
    pending: { icon: <Clock size={24} />, color: '#92400e' },
    running: { icon: <RefreshCw size={24} className="spinner" />, color: '#1e40af' },
    completed: { icon: <CheckCircle size={24} />, color: '#065f46' },
    failed: { icon: <XCircle size={24} />, color: '#991b1b' },
    cancelled: { icon: <AlertCircle size={24} />, color: '#64748b' },
  };

  const config = configs[status] || configs.pending;

  return (
    <div style={{ color: config.color }}>
      {config.icon}
    </div>
  );
}

function getStatusText(status) {
  const texts = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  };
  return texts[status] || status;
}

function getLogBgColor(type) {
  if (type === 'error') return '#7f1d1d';
  if (type === 'warning' || type === 'warn') return '#78350f';
  if (type === 'llm_call') return '#1e3a5f';
  if (type === 'step') return '#166534';
  if (type === 'debate') return '#4c1d95';
  return '#334155';
}

function getLogColor(type) {
  if (type === 'error') return '#fca5a5';
  if (type === 'warning' || type === 'warn') return '#fdba74';
  if (type === 'llm_call') return '#93c5fd';
  if (type === 'step') return '#86efac';
  if (type === 'debate') return '#c4b5fd';
  return '#94a3b8';
}

function formatLogData(data) {
  if (!data) return '';
  if (typeof data === 'string') return data;
  if (data.message) return data.message;
  if (data.step_name) return `步骤: ${data.step_name}`;
  if (data.model) return `[${data.model}] ${data.prompt?.substring(0, 100)}...`;
  if (data.agent) return `[Agent: ${data.agent}] ${data.action || ''}`;
  return JSON.stringify(data);
}

export default WorkflowDetail;
