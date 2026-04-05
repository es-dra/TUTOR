import React, { useState, useEffect } from 'react';
import { FlaskConical, CheckCircle, XCircle, Clock, Play, TrendingUp, Activity } from 'lucide-react';
import api from '../api.js';

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
      const [runsResponse, stats] = await Promise.all([
        api.listRuns(),
        api.getStats().catch(() => ({ total: 0, by_status: {}, by_type: {} }))
      ]);
      // API returns {success: true, data: [...runs...], meta: {...}}
      const runsData = runsResponse.data || [];
      setRuns(runsData);
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

  // Sort: running first, then by start time (most recent first)
  const sortedRuns = [...runs].sort((a, b) => {
    if (a.status === 'running' && b.status !== 'running') return -1;
    if (a.status !== 'running' && b.status === 'running') return 1;
    return new Date(b.started_at || 0) - new Date(a.started_at || 0);
  });
  const recentRuns = sortedRuns.slice(0, 8);

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">仪表盘</h1>
        <p className="page-subtitle">智能研究自动化平台概览</p>
      </div>

      {/* Stats Grid */}
      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-icon">
            <Activity size={24} />
          </div>
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">总工作流</div>
        </div>

        <div className="stat-card warning">
          <div className="stat-icon">
            <Clock size={24} />
          </div>
          <div className="stat-value">{stats.running}</div>
          <div className="stat-label">运行中</div>
        </div>

        <div className="stat-card success">
          <div className="stat-icon">
            <CheckCircle size={24} />
          </div>
          <div className="stat-value">{stats.completed}</div>
          <div className="stat-label">已完成</div>
        </div>

        <div className="stat-card danger">
          <div className="stat-icon">
            <XCircle size={24} />
          </div>
          <div className="stat-value">{stats.failed}</div>
          <div className="stat-label">失败</div>
        </div>
      </div>

      {/* Recent Workflows */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">
            <TrendingUp size={18} style={{ marginRight: '0.5rem', verticalAlign: 'middle' }} />
            最近工作流
          </h2>
        </div>

        {recentRuns.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <FlaskConical size={36} />
            </div>
            <h3 className="empty-state-title">暂无工作流</h3>
            <p className="empty-state-text">点击"新建"开始你的第一个研究工作流</p>
          </div>
        ) : (
          <div className="table-container" style={{ boxShadow: 'none' }}>
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>类型</th>
                  <th>状态</th>
                  <th>开始时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map(run => (
                  <tr key={run.run_id}>
                    <td>
                      <code className="workflow-id">{run.run_id.substring(0, 12)}...</code>
                    </td>
                    <td>
                      <span style={{ fontWeight: 500 }}>{getWorkflowTypeName(run.workflow_type)}</span>
                    </td>
                    <td>
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="text-secondary">
                      {run.started_at ? new Date(run.started_at).toLocaleString('zh-CN') : '-'}
                    </td>
                    <td>
                      <button
                        className="btn btn-primary"
                        style={{ padding: '0.375rem 0.875rem', fontSize: '0.8125rem' }}
                        onClick={() => onViewRun(run.run_id)}
                      >
                        <Play size={14} />
                        查看
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const configs = {
    pending: { class: 'pending', icon: Clock, label: '等待中' },
    running: { class: 'running', icon: Activity, label: '运行中' },
    completed: { class: 'completed', icon: CheckCircle, label: '已完成' },
    failed: { class: 'failed', icon: XCircle, label: '失败' },
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

function getWorkflowTypeName(type) {
  const names = {
    idea: '创意生成',
    experiment: '实验执行',
    review: '论文评审',
    write: '论文撰写',
  };
  return names[type] || type;
}

export default Dashboard;
