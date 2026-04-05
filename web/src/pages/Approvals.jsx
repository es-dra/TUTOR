import React, { useState, useEffect, useCallback } from 'react';
import { CheckCircle, XCircle, Clock, AlertCircle, RefreshCw, Filter, MessageSquare, Eye, Sparkles } from 'lucide-react';
import api from '../api.js';

function Approvals({ onViewRun }) {
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ status: '', runId: '' });
  const [actionLoading, setActionLoading] = useState(null);

  const loadApprovals = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listApprovals(
        filter.runId || null,
        filter.status || null
      );
      setApprovals(data.approvals || []);
    } catch (error) {
      console.error('加载失败:', error);
    } finally {
      setLoading(false);
    }
  }, [filter.runId, filter.status]);

  useEffect(() => {
    loadApprovals();
  }, [loadApprovals]);

  const handleApprove = async (approvalId) => {
    setActionLoading(approvalId);
    try {
      await api.approveRequest(approvalId);
      loadApprovals();
    } catch (error) {
      console.error('审批失败:', error);
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (approvalId) => {
    setActionLoading(approvalId);
    try {
      await api.rejectRequest(approvalId);
      loadApprovals();
    } catch (error) {
      console.error('拒绝失败:', error);
    } finally {
      setActionLoading(null);
    }
  };

  const statusOptions = [
    { value: '', label: '全部状态' },
    { value: 'pending', label: '待审批' },
    { value: 'approved', label: '已批准' },
    { value: 'rejected', label: '已拒绝' },
    { value: 'cancelled', label: '已取消' },
  ];

  const getPhaseName = (phase) => {
    const names = {
      idea: '创意生成',
      experiment: '实验执行',
      review: '论文评审',
      write: '论文撰写',
    };
    return phase ? (names[phase] || phase) : '未知';
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">审批管理</h1>
        <p className="page-subtitle">管理工作流中的审批请求</p>
      </div>

      {/* Filter Bar */}
      <div className="filter-bar">
        <span className="filter-label">
          <Filter size={16} />
          筛选
        </span>

        <select
          className="form-input"
          style={{ width: 'auto', padding: '0.5rem 2.5rem 0.5rem 0.75rem' }}
          value={filter.status}
          onChange={(e) => setFilter({ ...filter, status: e.target.value })}
        >
          {statusOptions.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        <input
          type="text"
          className="form-input"
          style={{ width: 'auto', padding: '0.5rem 0.75rem' }}
          placeholder="Run ID"
          value={filter.runId}
          onChange={(e) => setFilter({ ...filter, runId: e.target.value })}
        />

        <button className="btn btn-secondary" onClick={loadApprovals} style={{ marginLeft: 'auto' }}>
          <RefreshCw size={16} />
          刷新
        </button>
      </div>

      {/* Approvals List */}
      {loading ? (
        <div className="loading">
          <div className="spinner" />
        </div>
      ) : approvals.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <AlertCircle size={36} />
          </div>
          <h3 className="empty-state-title">暂无审批请求</h3>
          <p className="empty-state-text">所有审批请求都已被处理</p>
        </div>
      ) : (
        <div className="workflow-grid">
          {approvals.map(approval => (
            <div key={approval.approval_id} className="approval-card">
              <div className="approval-header">
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <Sparkles size={16} style={{ color: '#ec4899' }} />
                    <span style={{ fontWeight: 600, fontSize: '1rem' }}>
                      {approval.title || '审批请求'}
                    </span>
                  </div>
                  <code className="approval-id">{approval.approval_id}</code>
                </div>
                <StatusBadge status={approval.status} />
              </div>

              {approval.description && (
                <div className="approval-message">
                  {approval.description}
                </div>
              )}

              {/* Context Data Preview */}
              {approval.context_data && (
                <div style={{ marginTop: '1rem' }}>
                  {approval.context_data.debate_ideas && (
                    <div className="context-preview">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <Sparkles size={14} />
                        <strong>辩论产生的想法 ({approval.context_data.debate_ideas.length}个)</strong>
                      </div>
                      {approval.context_data.debate_ideas.slice(0, 2).map((idea, i) => (
                        <div key={i} className="idea-preview">
                          <p>{idea.original_idea?.substring(0, 150)}...</p>
                        </div>
                      ))}
                      {approval.context_data.debate_ideas.length > 2 && (
                        <div className="text-muted" style={{ fontSize: '0.8125rem', marginTop: '0.5rem' }}>
                          还有 {approval.context_data.debate_ideas.length - 2} 个想法...
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div className="approval-meta" style={{ marginTop: '1rem' }}>
                <span>工作流:</span>
                <code style={{ marginLeft: '0.5rem' }}>{approval.run_id?.substring(0, 16)}...</code>
                {onViewRun && (
                  <button
                    className="btn btn-ghost"
                    style={{ marginLeft: '0.5rem', padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                    onClick={() => onViewRun(approval.run_id)}
                  >
                    <Eye size={12} />
                    查看
                  </button>
                )}
              </div>

              <div className="approval-meta">
                <Clock size={12} />
                <span>请求时间:</span>
                <span style={{ marginLeft: '0.25rem' }}>
                  {approval.created_at ? new Date(approval.created_at).toLocaleString('zh-CN') : '-'}
                </span>
              </div>

              {approval.resolved_at && approval.status !== 'pending' && (
                <div className="approval-meta">
                  <CheckCircle size={12} />
                  <span>处理时间:</span>
                  <span style={{ marginLeft: '0.25rem' }}>
                    {new Date(approval.resolved_at).toLocaleString('zh-CN')}
                  </span>
                </div>
              )}

              {approval.resolved_by && (
                <div className="approval-meta">
                  <span>处理人:</span>
                  <span style={{ marginLeft: '0.25rem' }}>{approval.resolved_by}</span>
                </div>
              )}

              {approval.comment && (
                <div style={{
                  marginTop: '0.75rem',
                  padding: '0.75rem',
                  background: approval.status === 'approved' ? 'var(--status-completed-bg)' : 'var(--status-failed-bg)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.875rem',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '0.5rem'
                }}>
                  <MessageSquare size={14} style={{ marginTop: '0.125rem', flexShrink: 0 }} />
                  <div>
                    <strong>备注:</strong>
                    <p style={{ margin: '0.25rem 0 0' }}>{approval.comment}</p>
                  </div>
                </div>
              )}

              {approval.status === 'pending' && (
                <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.25rem' }}>
                  <button
                    className="btn btn-success"
                    onClick={() => handleApprove(approval.approval_id)}
                    disabled={actionLoading === approval.approval_id}
                    style={{ flex: 1 }}
                  >
                    <CheckCircle size={16} />
                    {actionLoading === approval.approval_id ? '处理中...' : '批准'}
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={() => handleReject(approval.approval_id)}
                    disabled={actionLoading === approval.approval_id}
                    style={{ flex: 1 }}
                  >
                    <XCircle size={16} />
                    {actionLoading === approval.approval_id ? '处理中...' : '拒绝'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  const configs = {
    approved: { class: 'completed', icon: CheckCircle, label: '已批准' },
    rejected: { class: 'failed', icon: XCircle, label: '已拒绝' },
    pending: { class: 'running', icon: Clock, label: '待审批' },
    cancelled: { class: 'pending', icon: AlertCircle, label: '已取消' },
    timeout: { class: 'pending', icon: AlertCircle, label: '已超时' },
  };

  const config = configs[status] || configs.pending;
  const Icon = config.icon;

  return (
    <span className={`status-badge-workflow ${config.class}`}>
      <Icon size={14} />
      {config.label}
    </span>
  );
}

export default Approvals;
