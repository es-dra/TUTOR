import React, { useState, useEffect } from 'react';
import { FlaskConical, CheckCircle, XCircle, Clock } from 'lucide-react';
import api from '../api';

function Dashboard({ onViewRun }) {
  const [runs, setRuns] = useState([]);
  const [statsData, setStatsData] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [runsData, stats] = await Promise.all([
        api.listRuns(),
        api.getStats().catch(() => ({ total: 0, by_status: {}, by_type: {} }))
      ]);
      setRuns(runsData.runs || []);
      setStatsData(stats);
    } catch (error) {
      console.error('加载失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const stats = {
    total: statsData.total || runs.length,
    running: statsData.by_status?.running ?? runs.filter(r => r.status === 'running').length,
    completed: statsData.by_status?.completed ?? runs.filter(r => r.status === 'completed').length,
    failed: statsData.by_status?.failed ?? runs.filter(r => r.status === 'failed').length,
  };

  const recentRuns = runs.slice(0, 5);

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
      </div>
    );
  }

  return (
    <div>
      <h1 style={{ marginBottom: '1.5rem' }}>仪表盘</h1>

      <div className="dashboard-grid">
        <div className="stat-card">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">总工作流</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#2563eb' }}>{stats.running}</div>
          <div className="stat-label">运行中</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#10b981' }}>{stats.completed}</div>
          <div className="stat-label">已完成</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: '#ef4444' }}>{stats.failed}</div>
          <div className="stat-label">失败</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2 className="card-title">最近工作流</h2>
        </div>

        {recentRuns.length === 0 ? (
          <div className="empty-state">
            <FlaskConical size={48} style={{ opacity: 0.3 }} />
            <p style={{ marginTop: '1rem' }}>暂无工作流，点击"新建"开始</p>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '0.75rem' }}>ID</th>
                <th style={{ padding: '0.75rem' }}>类型</th>
                <th style={{ padding: '0.75rem' }}>状态</th>
                <th style={{ padding: '0.75rem' }}>开始时间</th>
                <th style={{ padding: '0.75rem' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {recentRuns.map(run => (
                <tr key={run.run_id} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '0.75rem' }}>
                    <code style={{ background: '#f1f5f9', padding: '0.25rem 0.5rem', borderRadius: '4px' }}>
                      {run.run_id}
                    </code>
                  </td>
                  <td style={{ padding: '0.75rem' }}>{run.workflow_type}</td>
                  <td style={{ padding: '0.75rem' }}>
                    <StatusBadge status={run.status} />
                  </td>
                  <td style={{ padding: '0.75rem', color: 'var(--text-secondary)' }}>
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
                  </td>
                  <td style={{ padding: '0.75rem' }}>
                    <button
                      className="btn btn-primary"
                      onClick={() => onViewRun(run.run_id)}
                    >
                      查看
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
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
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.25rem',
      padding: '0.25rem 0.75rem',
      borderRadius: '9999px',
      fontSize: '0.75rem',
      fontWeight: 500,
      background: config.bg,
      color: config.color,
    }}>
      {status === 'completed' && <CheckCircle size={14} />}
      {status === 'failed' && <XCircle size={14} />}
      {status === 'running' && <Clock size={14} />}
      {config.label}
    </span>
  );
}

export default Dashboard;
