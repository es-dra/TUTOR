import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, RefreshCw, CheckCircle, XCircle, Clock, AlertCircle, Download, Trash2, Bot, MessageSquare, Sparkles, BookOpen, GitBranch, Play, Search, Filter, Pause, RotateCcw } from 'lucide-react';
import api from '../api.js';

const STEP_NAMES = {
  smart_input: { name: '智能输入处理', icon: Sparkles, color: '#8b5cf6' },
  auto_arxiv_search: { name: '自动文献搜索', icon: Search, color: '#06b6d4' },
  paper_loading: { name: '加载文献', icon: BookOpen, color: '#3b82f6' },
  paper_validation: { name: '验证文献', icon: CheckCircle, color: '#10b981' },
  zotero_literature: { name: 'Zotero补充', icon: BookOpen, color: '#f59e0b' },
  literature_analysis: { name: '文献分析', icon: Sparkles, color: '#8b5cf6' },
  idea_debate: { name: '辩论生成', icon: MessageSquare, color: '#ec4899' },
  idea_evaluation: { name: '想法评估', icon: Bot, color: '#6366f1' },
  final_proposal: { name: '生成提案', icon: GitBranch, color: '#f59e0b' },
  project_gate: { name: '审批门控', icon: Clock, color: '#ef4444' },
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

const LOG_TYPES = ['all', 'step', 'llm_call', 'agent', 'error', 'info', 'warning'];

function WorkflowDetail({ runId, onClose }) {
  const [run, setRun] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('progress');
  const [stepStatuses, setStepStatuses] = useState({});
  const [logFilter, setLogFilter] = useState('all');
  const [logSearch, setLogSearch] = useState('');
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
    const statuses = {};
    const completedSteps = new Set();

    if (runData.result?.steps) {
      runData.result.steps.forEach(step => {
        if (step.status === 'completed') {
          completedSteps.add(step.name);
        }
      });
    }

    // Calculate current step based on completed steps
    let foundCurrent = false;
    WORKFLOW_STEPS_ORDER.forEach((stepName, index) => {
      if (completedSteps.has(stepName)) {
        statuses[stepName] = 'completed';
      } else if (!foundCurrent && runData.status === 'running') {
        statuses[stepName] = 'current';
        foundCurrent = true;
      } else if (runData.status === 'paused' && stepName === 'project_gate') {
        statuses[stepName] = 'paused';
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

        if (data.type === 'step') {
          const stepName = data.data?.step_name;
          if (stepName && STEP_NAMES[stepName]) {
            setStepStatuses(prev => {
              const newStatuses = { ...prev };
              // Mark previous current as completed
              Object.keys(newStatuses).forEach(k => {
                if (newStatuses[k] === 'current') newStatuses[k] = 'completed';
              });
              newStatuses[stepName] = 'completed';
              return newStatuses;
            });
            const stepIndex = WORKFLOW_STEPS_ORDER.indexOf(stepName);
            if (stepIndex >= 0 && stepIndex < WORKFLOW_STEPS_ORDER.length - 1) {
              const nextStep = WORKFLOW_STEPS_ORDER[stepIndex + 1];
              setStepStatuses(prev => ({ ...prev, [nextStep]: 'current' }));
            }
          }
        }

        if (data.type === 'llm_call') {
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
    if (logsEndRef.current && activeTab === 'logs') {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, activeTab]);

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
      await fetch(`/runs/${runId}`, {
        method: 'DELETE'
      });
      onClose();
    } catch (error) {
      console.error('取消失败:', error);
    }
  };

  const handleRetry = async () => {
    if (!window.confirm('确定要重试此工作流吗？将创建一个新的运行。')) return;
    try {
      const result = await api.retryRun(runId);
      // Navigate to the new run
      onClose();
      // Refresh parent to show new run
      if (window.refreshWorkflows) window.refreshWorkflows();
    } catch (error) {
      console.error('重试失败:', error);
      alert('重试失败: ' + (error.message || '未知错误'));
    }
  };

  // Calculate progress percentage
  const getProgress = () => {
    const completed = Object.values(stepStatuses).filter(s => s === 'completed').length;
    return Math.round((completed / WORKFLOW_STEPS_ORDER.length) * 100);
  };

  // Filter logs
  const filteredLogs = logs.filter(log => {
    if (logFilter !== 'all' && log.type !== logFilter) return false;
    if (logSearch) {
      const searchLower = logSearch.toLowerCase();
      const message = formatLogData(log.data).toLowerCase();
      if (!message.includes(searchLower)) return false;
    }
    return true;
  });

  if (loading) {
    return (
      <div className="modal-overlay">
        <div className="loading">
          <div className="spinner" />
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="modal-overlay">
        <div className="card" style={{ textAlign: 'center' }}>
          <p className="mb-2">未找到工作流</p>
          <button className="btn btn-primary" onClick={onClose}>关闭</button>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay">
      <div className="modal" style={{ maxWidth: '800px' }}>
        {/* Header */}
        <div className="modal-header">
          <div>
            <h2 className="modal-title">工作流详情</h2>
            <code className="text-muted" style={{ fontSize: '0.8125rem' }}>
              {runId}
            </code>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {run && (run.status === 'failed' || run.status === 'completed' || run.status === 'paused') && (
              <button
                className="btn btn-primary"
                onClick={handleRetry}
                title="重试工作流"
                style={{ padding: '0.5rem 1rem' }}
              >
                <RotateCcw size={16} />
                重试
              </button>
            )}
            {run && (run.status === 'pending' || run.status === 'running') && (
              <button
                className="btn btn-danger btn-icon"
                onClick={handleCancel}
                title="取消工作流"
              >
                <Trash2 size={18} />
              </button>
            )}
            <button className="btn btn-secondary btn-icon" onClick={handleRefresh}>
              <RotateCcw size={18} />
            </button>
            <button className="btn btn-ghost btn-icon" onClick={onClose}>
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Status Bar */}
        <div className={`status-bar ${run.status}`}>
          <StatusIcon status={run.status} />
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <strong>{getStatusText(run.status)}</strong>
              {/* Progress Bar */}
              {run.status === 'running' && (
                <div className="progress-bar-container">
                  <div className="progress-bar" style={{ width: `${getProgress()}%` }} />
                  <span className="progress-text">{getProgress()}%</span>
                </div>
              )}
            </div>
            <div className="text-muted" style={{ fontSize: '0.8125rem', marginTop: '0.25rem' }}>
              {getWorkflowTypeName(run.workflow_type)} • 开始于 {run.started_at ? new Date(run.started_at).toLocaleString('zh-CN') : '-'}
            </div>
          </div>
        </div>

        {/* Error Message */}
        {run.status === 'failed' && run.error && (
          <div className="error-banner">
            <AlertCircle size={16} />
            <div>
              <strong>工作流失败</strong>
              <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem' }}>{run.error}</p>
            </div>
          </div>
        )}

        {/* Paused Message */}
        {run.status === 'paused' && (
          <div className="info-banner">
            <Pause size={16} />
            <div>
              <strong>工作流已暂停</strong>
              <p style={{ margin: '0.25rem 0 0', fontSize: '0.875rem' }}>
                {run.error || '等待用户审批'}
              </p>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div style={{ padding: '0 1.5rem' }}>
          <div className="tabs">
            <button
              className={`tab ${activeTab === 'progress' ? 'active' : ''}`}
              onClick={() => setActiveTab('progress')}
            >
              <Play size={14} />
              进度
            </button>
            <button
              className={`tab ${activeTab === 'logs' ? 'active' : ''}`}
              onClick={() => setActiveTab('logs')}
            >
              <Bot size={14} />
              日志 {logs.length > 0 && `(${logs.length})`}
            </button>
            {(run.result && Object.keys(run.result).length > 0) && (
              <button
                className={`tab ${activeTab === 'result' ? 'active' : ''}`}
                onClick={() => setActiveTab('result')}
              >
                <Sparkles size={14} />
                结果
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="modal-body">
          {activeTab === 'progress' && (
            <ProgressView
              stepStatuses={stepStatuses}
              currentStep={Object.entries(stepStatuses).find(([_, s]) => s === 'current')?.[0]}
              run={run}
            />
          )}

          {activeTab === 'logs' && (
            <LogsView
              logs={filteredLogs}
              allLogsCount={logs.length}
              logFilter={logFilter}
              setLogFilter={setLogFilter}
              logSearch={logSearch}
              setLogSearch={setLogSearch}
              logsEndRef={logsEndRef}
            />
          )}

          {activeTab === 'result' && run.result && Object.keys(run.result).length > 0 && (
            <ResultView run={run} runId={runId} />
          )}
        </div>
      </div>
    </div>
  );
}

function ProgressView({ stepStatuses, currentStep }) {
  return (
    <div>
      {/* Step Timeline */}
      <div className="card-glass">
        <h3 className="card-title" style={{ marginBottom: '1.25rem' }}>执行进度</h3>
        <div className="step-timeline">
          {WORKFLOW_STEPS_ORDER.map((stepName, index) => {
            const stepInfo = STEP_NAMES[stepName];
            const status = stepStatuses[stepName] || 'pending';
            const isLast = index === WORKFLOW_STEPS_ORDER.length - 1;
            const Icon = stepInfo?.icon || Clock;

            return (
              <div key={stepName} className="step-item">
                <div className="step-connector">
                  <div className={`step-icon ${status}`}>
                    {status === 'completed' ? <CheckCircle size={16} /> :
                      status === 'current' ? <div className="spinner spinner-sm" /> :
                        status === 'paused' ? <Pause size={14} /> :
                          <Clock size={14} />}
                  </div>
                  {!isLast && (
                    <div className={`step-line ${status === 'pending' || status === 'paused' ? 'pending' : ''}`} />
                  )}
                </div>

                <div className="step-content">
                  <div className="step-name" style={{ color: stepInfo?.color || 'var(--text)' }}>
                    <Icon size={16} />
                    <span>{stepInfo?.name || stepName}</span>
                    {status === 'current' && (
                      <span className="step-status current">执行中</span>
                    )}
                    {status === 'completed' && (
                      <span className="step-status completed">已完成</span>
                    )}
                    {status === 'paused' && (
                      <span className="step-status paused">已暂停</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Current Activity */}
      {currentStep && (
        <div className="card-glass" style={{ marginTop: '1rem' }}>
          <h3 className="card-title" style={{ marginBottom: '0.75rem' }}>当前活动</h3>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
            padding: '1rem',
            background: 'var(--status-running-bg)',
            borderRadius: 'var(--radius-md)'
          }}>
            <Bot size={24} style={{ color: 'var(--status-running)' }} />
            <div>
              <div style={{ fontWeight: 600, color: 'var(--status-running)' }}>
                {STEP_NAMES[currentStep]?.name || currentStep}
              </div>
              <div className="text-muted" style={{ fontSize: '0.875rem' }}>
                正在执行中，请稍候...
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function LogsView({ logs, allLogsCount, logFilter, setLogFilter, logSearch, setLogSearch, logsEndRef }) {
  return (
    <div className="logs-view">
      {/* Log Filters */}
      <div className="logs-toolbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Filter size={14} />
          <select
            className="form-input"
            style={{ width: 'auto', padding: '0.375rem 2rem 0.375rem 0.5rem', fontSize: '0.8125rem' }}
            value={logFilter}
            onChange={(e) => setLogFilter(e.target.value)}
          >
            {LOG_TYPES.map(type => (
              <option key={type} value={type}>
                {type === 'all' ? '全部类型' : type.toUpperCase()}
              </option>
            ))}
          </select>
          {logFilter !== 'all' && (
            <span className="text-muted" style={{ fontSize: '0.8125rem' }}>
              ({logs.length} / {allLogsCount})
            </span>
          )}
        </div>
        <input
          type="text"
          className="form-input"
          placeholder="搜索日志..."
          value={logSearch}
          onChange={(e) => setLogSearch(e.target.value)}
          style={{ width: '200px', padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
        />
      </div>

      {/* Log Entries */}
      <div className="logs-container">
        {logs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#64748B' }}>
            {logFilter !== 'all' || logSearch ? '没有匹配的日志...' : '暂无日志...'}
          </div>
        ) : (
          logs.map((log, index) => (
            <div key={index} className={`log-entry ${log.type}`}>
              <span className="log-timestamp">
                {log.timestamp.toLocaleTimeString('zh-CN')}
              </span>
              <span className={`log-type ${log.type}`}>
                {log.type.toUpperCase()}
              </span>
              <span className="log-message">
                {formatLogData(log.data)}
              </span>
            </div>
          ))
        )}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
}

function ResultView({ run, runId }) {
  const result = run.result || {};

  // Try to render different result types nicely
  const renderResult = () => {
    if (result.ideas || result.final_ideas) {
      const ideas = result.ideas || result.final_ideas || [];
      return (
        <div className="result-section">
          <h4 style={{ marginBottom: '1rem' }}>生成的想法 ({ideas.length})</h4>
          {ideas.map((idea, i) => (
            <div key={i} className="idea-card">
              <h5 style={{ marginBottom: '0.5rem', color: 'var(--primary)' }}>想法 {i + 1}</h5>
              <p style={{ whiteSpace: 'pre-wrap', fontSize: '0.875rem' }}>
                {idea.original_idea || idea.content || idea.description || JSON.stringify(idea, null, 2)}
              </p>
              {idea.score !== undefined && (
                <div style={{ marginTop: '0.5rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                  评分: {typeof idea.score === 'number' ? idea.score.toFixed(2) : idea.score}
                </div>
              )}
            </div>
          ))}
        </div>
      );
    }

    if (result.papers || result.validated_papers) {
      const papers = result.papers || result.validated_papers || [];
      return (
        <div className="result-section">
          <h4 style={{ marginBottom: '1rem' }}>相关论文 ({papers.length})</h4>
          {papers.map((paper, i) => (
            <div key={i} className="paper-card">
              <h5 style={{ marginBottom: '0.25rem' }}>{paper.title || paper.arxiv_id || `论文 ${i + 1}`}</h5>
              {paper.authors && <p className="text-muted" style={{ fontSize: '0.8125rem' }}>{paper.authors.join(', ')}</p>}
              {paper.abstract && <p style={{ fontSize: '0.8125rem', marginTop: '0.5rem' }}>{paper.abstract.substring(0, 300)}...</p>}
            </div>
          ))}
        </div>
      );
    }

    // Default: show as JSON
    return (
      <pre style={{
        background: 'linear-gradient(135deg, #1E293B 0%, #0F172A 100%)',
        color: '#E2E8F0',
        padding: '1.25rem',
        borderRadius: 'var(--radius-md)',
        overflow: 'auto',
        maxHeight: '400px',
        fontSize: '0.8125rem',
        fontFamily: 'var(--font-code)',
      }}>
        {JSON.stringify(result, null, 2)}
      </pre>
    );
  };

  return (
    <div className="card-glass">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h3 className="card-title">执行结果</h3>
        <button
          className="btn btn-secondary"
          style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }}
          onClick={() => {
            const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `result-${runId}.json`;
            a.click();
          }}
        >
          <Download size={16} />
          导出 JSON
        </button>
      </div>
      {renderResult()}
    </div>
  );
}

function StatusIcon({ status }) {
  const configs = {
    pending: { icon: Clock, color: 'var(--status-pending)' },
    running: { icon: RefreshCw, color: 'var(--status-running)', animate: true },
    completed: { icon: CheckCircle, color: 'var(--status-completed)' },
    failed: { icon: XCircle, color: 'var(--status-failed)' },
    cancelled: { icon: AlertCircle, color: 'var(--text-muted)' },
    paused: { icon: Pause, color: 'var(--status-pending)' },
  };

  const config = configs[status] || configs.pending;
  const Icon = config.icon;

  return (
    <Icon size={24} style={{ color: config.color }} className={config.animate ? 'spinner' : ''} />
  );
}

function getStatusText(status) {
  const texts = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    paused: '已暂停',
  };
  return texts[status] || status;
}

function getWorkflowTypeName(type) {
  const names = {
    idea: '创意生成',
    experiment: '实验执行',
    review: '论文评审',
    write: '论文撰写',
  };
  return names[type] || type;
}

function formatLogData(data) {
  if (!data) return '';
  if (typeof data === 'string') return data;
  if (data.message) return data.message;
  if (data.step_name) return `[${data.step_name}] ${data.status || ''}`;
  if (data.model) return `[${data.model}] ${data.prompt?.substring(0, 100)}...`;
  if (data.agent) return `[Agent: ${data.agent}] ${data.action || ''}`;
  if (data.error) return `错误: ${data.error}`;
  return JSON.stringify(data);
}

export default WorkflowDetail;
