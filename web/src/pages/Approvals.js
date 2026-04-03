import React, { useState, useEffect, useCallback } from 'react';
import { CheckCircle, XCircle, Clock, AlertCircle } from 'lucide-react';
import api from '../api';

function Approvals() {
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

  const getStatusIcon = (status) => {
    switch (status) {
      case 'approved': return <CheckCircle size={16} color="#10b981" />;
      case 'rejected': return <XCircle size={16} color="#ef4444" />;
      case 'pending': return <Clock size={16} color="#f59e0b" />;
      case 'cancelled': return <AlertCircle size={16} color="#64748b" />;
      default: return <Clock size={16} />;
    }
  };

  const getStatusLabel = (status) => {
    const labels = {
      pending: '待审批',
      approved: '已批准',
      rejected: '已拒绝',
      cancelled: '已取消',
    };
    return labels[status] || status;
  };

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h1>审批管理</h1>
        <button className="btn btn-secondary" onClick={loadApprovals}>
          刷新
        </button>
      </div>

      <div className="card" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontWeight: 500 }}>筛选:</span>
          </div>

          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={filter.status}
            onChange={(e) => setFilter({ ...filter, status: e.target.value })}
          >
            <option value="">全部状态</option>
            <option value="pending">待审批</option>
            <option value="approved">已批准</option>
            <option value="rejected">已拒绝</option>
            <option value="cancelled">已取消</option>
          </select>

          <input
            type="text"
            className="form-input"
            style={{ width: 'auto' }}
            placeholder="Run ID"
            value={filter.runId}
            onChange={(e) => setFilter({ ...filter, runId: e.target.value })}
          />
        </div>
      </div>

      {approvals.length === 0 ? (
        <div className="empty-state">
          <AlertCircle size={48} style={{ opacity: 0.3 }} />
          <p style={{ marginTop: '1rem' }}>暂无审批请求</p>
        </div>
      ) : (
        <div className="workflow-grid">
          {approvals.map(approval => (
            <div key={approval.id} className="card" style={{ cursor: 'default' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <code style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                    {approval.id}
                  </code>
                  <h3 style={{ margin: '0.5rem 0', fontSize: '1rem' }}>
                    {approval.type || 'approval'} - {approval.step_name || 'N/A'}
                  </h3>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  {getStatusIcon(approval.status)}
                  <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>
                    {getStatusLabel(approval.status)}
                  </span>
                </div>
              </div>

              {approval.message && (
                <p style={{
                  margin: '0.75rem 0',
                  padding: '0.75rem',
                  background: 'var(--background)',
                  borderRadius: '6px',
                  fontSize: '0.875rem',
                  color: 'var(--text-secondary)'
                }}>
                  {approval.message}
                </p>
              )}

              {approval.run_id && (
                <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                  工作流: <code>{approval.run_id}</code>
                </div>
              )}

              {approval.requested_at && (
                <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                  请求时间: {new Date(approval.requested_at).toLocaleString()}
                </div>
              )}

              {approval.resolved_at && approval.status !== 'pending' && (
                <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                  处理时间: {new Date(approval.resolved_at).toLocaleString()}
                </div>
              )}

              {approval.comment && (
                <div style={{
                  marginTop: '0.75rem',
                  padding: '0.5rem',
                  background: approval.status === 'approved' ? '#d1fae5' : '#fee2e2',
                  borderRadius: '4px',
                  fontSize: '0.875rem'
                }}>
                  <strong>备注:</strong> {approval.comment}
                </div>
              )}

              {approval.status === 'pending' && (
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                  <button
                    className="btn btn-success"
                    onClick={() => handleApprove(approval.id)}
                    disabled={actionLoading === approval.id}
                    style={{ flex: 1 }}
                  >
                    <CheckCircle size={16} />
                    批准
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={() => handleReject(approval.id)}
                    disabled={actionLoading === approval.id}
                    style={{ flex: 1 }}
                  >
                    <XCircle size={16} />
                    拒绝
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

export default Approvals;
