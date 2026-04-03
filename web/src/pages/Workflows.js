import React, { useState, useEffect, useCallback } from 'react';
import { FlaskConical, Filter } from 'lucide-react';
import api from '../api';

function Workflows({ onViewRun }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ status: '', type: '' });
  const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0 });

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listRuns(
        filter.status || null,
        filter.type || null,
        pagination.page,
        pagination.limit
      );
      setRuns(data.runs || []);
      setPagination(prev => ({ ...prev, total: data.total || 0 }));
    } catch (error) {
      console.error('加载失败:', error);
    } finally {
      setLoading(false);
    }
  }, [filter.status, filter.type, pagination.page, pagination.limit]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const totalPages = Math.ceil(pagination.total / pagination.limit);

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
        <h1>工作流列表</h1>
      </div>

      <div className="card" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Filter size={18} />
            <span>筛选:</span>
          </div>

          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={filter.status}
            onChange={(e) => setFilter({ ...filter, status: e.target.value })}
          >
            <option value="">全部状态</option>
            <option value="pending">等待中</option>
            <option value="running">运行中</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
          </select>

          <select
            className="form-input"
            style={{ width: 'auto' }}
            value={filter.type}
            onChange={(e) => setFilter({ ...filter, type: e.target.value })}
          >
            <option value="">全部类型</option>
            <option value="idea">创意生成</option>
            <option value="experiment">实验执行</option>
            <option value="review">论文评审</option>
            <option value="write">论文撰写</option>
          </select>
        </div>
      </div>

      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
          <button
            className="btn btn-secondary"
            disabled={pagination.page <= 1}
            onClick={() => setPagination(p => ({ ...p, page: p.page - 1 }))}
          >
            上一页
          </button>
          <span style={{ display: 'flex', alignItems: 'center', padding: '0 1rem' }}>
            第 {pagination.page} / {totalPages} 页 (共 {pagination.total} 条)
          </span>
          <button
            className="btn btn-secondary"
            disabled={pagination.page >= totalPages}
            onClick={() => setPagination(p => ({ ...p, page: p.page + 1 }))}
          >
            下一页
          </button>
        </div>
      )}

      {runs.length === 0 ? (
        <div className="empty-state">
          <FlaskConical size={48} style={{ opacity: 0.3 }} />
          <p style={{ marginTop: '1rem' }}>没有找到匹配的工作流</p>
        </div>
      ) : (
        <div className="workflow-grid">
          {runs.map(run => (
            <div
              key={run.run_id}
              className="workflow-card"
              onClick={() => onViewRun(run.run_id)}
            >
              <div className="workflow-type">{run.workflow_type}</div>
              <div className="workflow-title">
                <code style={{ background: 'transparent', padding: 0 }}>{run.run_id}</code>
              </div>
              <div style={{ marginTop: '0.5rem' }}>
                <StatusBadge status={run.status} />
              </div>
              {run.started_at && (
                <div style={{ marginTop: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                  {new Date(run.started_at).toLocaleString()}
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
    pending: { bg: '#fef3c7', color: '#92400e', label: '等待中' },
    running: { bg: '#dbeafe', color: '#1e40af', label: '运行中' },
    completed: { bg: '#d1fae5', color: '#065f46', label: '已完成' },
    failed: { bg: '#fee2e2', color: '#991b1b', label: '失败' },
  };

  const config = configs[status] || configs.pending;

  return (
    <span className={`workflow-status status-${status}`}>
      {config.label}
    </span>
  );
}

export default Workflows;
