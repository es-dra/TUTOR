import React, { useState, useEffect, useCallback } from 'react';
import { FlaskConical, Filter, ChevronLeft, ChevronRight, Play, Clock, Activity, CheckCircle, XCircle, Archive, Trash2, Star, MessageSquare, MoreVertical, X, Trash, Wand, Check } from 'lucide-react';
import api from '../api.js';

function Workflows({ onViewRun }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ status: '', type: '' });
  const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0 });
  const [actionMenu, setActionMenu] = useState(null);
  const [notesModal, setNotesModal] = useState(null);
  const [selectedRuns, setSelectedRuns] = useState(new Set());
  const [cleanupModal, setCleanupModal] = useState(null); // { preview: [...], loading: false }
  const [batchDeleting, setBatchDeleting] = useState(false);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.listRuns(
        filter.status || null,
        filter.type || null,
        pagination.page,
        pagination.limit
      );
      const runsData = response.data || [];
      const totalCount = response.meta?.total || 0;
      setRuns(runsData);
      setPagination(prev => ({ ...prev, total: totalCount }));
    } catch (error) {
      console.error('加载失败:', error);
    } finally {
      setLoading(false);
    }
  }, [filter.status, filter.type, pagination.page, pagination.limit]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  // Clear selection when page/filter changes
  useEffect(() => {
    setSelectedRuns(new Set());
  }, [filter.status, filter.type, pagination.page]);

  const totalPages = Math.ceil(pagination.total / pagination.limit);

  const toggleSelectAll = () => {
    if (selectedRuns.size === runs.length) {
      setSelectedRuns(new Set());
    } else {
      setSelectedRuns(new Set(runs.map(r => r.run_id)));
    }
  };

  const toggleSelectRun = (runId) => {
    const newSelected = new Set(selectedRuns);
    if (newSelected.has(runId)) {
      newSelected.delete(runId);
    } else {
      newSelected.add(runId);
    }
    setSelectedRuns(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedRuns.size === 0) return;
    if (!window.confirm(`确定要删除选中的 ${selectedRuns.size} 个工作流吗？此操作不可恢复。`)) return;

    setBatchDeleting(true);
    try {
      const ids = Array.from(selectedRuns);
      await api.batchDeleteRuns(ids);
      setSelectedRuns(new Set());
      loadRuns();
    } catch (err) {
      console.error('批量删除失败:', err);
      alert('批量删除失败: ' + err.message);
    } finally {
      setBatchDeleting(false);
    }
  };

  const handleCleanupPreview = async (olderThanDays, status) => {
    setCleanupModal({ preview: [], loading: true });
    try {
      const result = await api.cleanupOldRuns(status, olderThanDays, true);
      setCleanupModal({
        preview: result.data?.run_ids || [],
        count: result.data?.count || 0,
        loading: false,
        olderThanDays,
        status
      });
    } catch (err) {
      console.error('预览失败:', err);
      setCleanupModal(null);
    }
  };

  const handleCleanupExecute = async () => {
    if (!cleanupModal) return;
    if (!window.confirm(`确定要清理 ${cleanupModal.count} 个旧工作流吗？此操作不可恢复。`)) return;

    try {
      await api.cleanupOldRuns(cleanupModal.status, cleanupModal.olderThanDays, false);
      setCleanupModal(null);
      loadRuns();
    } catch (err) {
      console.error('清理失败:', err);
      alert('清理失败: ' + err.message);
    }
  };

  const handleArchive = async (runId, e) => {
    e.stopPropagation();
    const run = runs.find(r => r.run_id === runId);
    const tags = run.tags || [];
    const isArchived = tags.includes('archived');
    const newTags = isArchived
      ? tags.filter(t => t !== 'archived')
      : [...tags, 'archived'];
    try {
      await api.updateRunTags(runId, newTags);
      loadRuns();
    } catch (err) {
      console.error('归档失败:', err);
    }
    setActionMenu(null);
  };

  const handleFavorite = async (runId, e) => {
    e.stopPropagation();
    const run = runs.find(r => r.run_id === runId);
    const tags = run.tags || [];
    const isFav = tags.includes('favorite');
    const newTags = isFav
      ? tags.filter(t => t !== 'favorite')
      : [...tags, 'favorite'];
    try {
      await api.updateRunTags(runId, newTags);
      loadRuns();
    } catch (err) {
      console.error('收藏失败:', err);
    }
    setActionMenu(null);
  };

  const handleDelete = async (runId, e) => {
    e.stopPropagation();
    if (!window.confirm('确定要删除此工作流吗？此操作不可恢复。')) return;
    try {
      await api.deleteRun(runId);
      loadRuns();
    } catch (err) {
      console.error('删除失败:', err);
    }
    setActionMenu(null);
  };

  const handleNotes = async (runId, notes, e) => {
    if (e) e.stopPropagation();
    const run = runs.find(r => r.run_id === runId);
    const tags = run.tags || [];
    const newTags = tags.filter(t => !t.startsWith('notes:'));
    if (notes.trim()) {
      newTags.push(`notes:${notes.trim()}`);
    }
    try {
      await api.updateRunTags(runId, newTags);
      loadRuns();
    } catch (err) {
      console.error('保存备注失败:', err);
    }
    setNotesModal(null);
    setActionMenu(null);
  };

  const getNotes = (run) => {
    const notesTag = (run.tags || []).find(t => t.startsWith('notes:'));
    return notesTag ? notesTag.slice(6) : '';
  };

  const statusOptions = [
    { value: '', label: '全部状态' },
    { value: 'pending', label: '等待中' },
    { value: 'running', label: '运行中' },
    { value: 'completed', label: '已完成' },
    { value: 'failed', label: '失败' },
  ];

  const typeOptions = [
    { value: '', label: '全部类型' },
    { value: 'idea', label: '创意生成' },
    { value: 'experiment', label: '实验执行' },
    { value: 'review', label: '论文评审' },
    { value: 'write', label: '论文撰写' },
  ];

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">工作流列表</h1>
        <p className="page-subtitle">查看和管理所有研究工作流</p>
      </div>

      {/* Batch Actions Bar */}
      {selectedRuns.size > 0 && (
        <div className="batch-actions-bar">
          <span style={{ fontWeight: 500 }}>
            已选择 {selectedRuns.size} 个工作流
          </span>
          <button
            className="btn btn-danger"
            style={{ padding: '0.5rem 1rem' }}
            onClick={handleBatchDelete}
            disabled={batchDeleting}
          >
            <Trash size={16} />
            {batchDeleting ? '删除中...' : '批量删除'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => setSelectedRuns(new Set())}
          >
            取消选择
          </button>
        </div>
      )}

      {/* Filter Bar */}
      <div className="filter-bar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span className="filter-label">
            <Filter size={16} />
            筛选
          </span>

          <select
            className="form-input"
            style={{ width: 'auto', padding: '0.5rem 2.5rem 0.5rem 0.75rem' }}
            value={filter.status}
            onChange={(e) => {
              setFilter({ ...filter, status: e.target.value });
              setPagination(p => ({ ...p, page: 1 }));
            }}
          >
            {statusOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          <select
            className="form-input"
            style={{ width: 'auto', padding: '0.5rem 2.5rem 0.5rem 0.75rem' }}
            value={filter.type}
            onChange={(e) => {
              setFilter({ ...filter, type: e.target.value });
              setPagination(p => ({ ...p, page: 1 }));
            }}
          >
            {typeOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            className="btn btn-secondary"
            style={{ padding: '0.5rem 1rem' }}
            onClick={() => handleCleanupPreview(7, 'failed')}
          >
            <Wand size={16} />
            清理失败
          </button>
          <button
            className="btn btn-secondary"
            style={{ padding: '0.5rem 1rem' }}
            onClick={() => handleCleanupPreview(7, 'completed')}
          >
            <Wand size={16} />
            清理完成
          </button>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination">
          <button
            className="btn btn-secondary"
            style={{ padding: '0.5rem 0.75rem' }}
            disabled={pagination.page <= 1}
            onClick={() => setPagination(p => ({ ...p, page: p.page - 1 }))}
          >
            <ChevronLeft size={16} />
          </button>
          <span className="pagination-info">
            第 {pagination.page} / {totalPages} 页 (共 {pagination.total} 条)
          </span>
          <button
            className="btn btn-secondary"
            style={{ padding: '0.5rem 0.75rem' }}
            disabled={pagination.page >= totalPages}
            onClick={() => setPagination(p => ({ ...p, page: p.page + 1 }))}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}

      {/* Workflow Grid */}
      {loading ? (
        <div className="loading">
          <div className="spinner" />
        </div>
      ) : runs.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <FlaskConical size={36} />
          </div>
          <h3 className="empty-state-title">没有找到匹配的工作流</h3>
          <p className="empty-state-text">尝试调整筛选条件或创建新的工作流</p>
        </div>
      ) : (
        <div className="workflow-grid">
          {/* Header row with select all */}
          <div className="workflow-card select-all-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <button
                className={`checkbox ${selectedRuns.size === runs.length && runs.length > 0 ? 'checked' : ''}`}
                onClick={toggleSelectAll}
              >
                {selectedRuns.size === runs.length && runs.length > 0 && <Check size={12} />}
              </button>
              <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>全选</span>
            </div>
          </div>

          {runs.map(run => (
            <div
              key={run.run_id}
              className={`workflow-card ${selectedRuns.has(run.run_id) ? 'selected' : ''}`}
              onClick={() => onViewRun(run.run_id)}
            >
              <div className="workflow-card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <button
                    className={`checkbox ${selectedRuns.has(run.run_id) ? 'checked' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleSelectRun(run.run_id);
                    }}
                  >
                    {selectedRuns.has(run.run_id) && <Check size={12} />}
                  </button>
                  <div className="workflow-type">{getWorkflowTypeName(run.workflow_type)}</div>
                </div>
                <button
                  className="btn btn-ghost btn-icon"
                  style={{ padding: '0.25rem' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setActionMenu({ runId: run.run_id, x: e.clientX, y: e.clientY });
                  }}
                >
                  <MoreVertical size={16} />
                </button>
              </div>
              <code className="workflow-id">{run.run_id.substring(0, 16)}...</code>
              <div style={{ marginTop: '0.75rem' }}>
                <StatusBadge status={run.status} />
              </div>
              {/* Tags */}
              {run.tags && run.tags.length > 0 && (
                <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                  {run.tags.includes('favorite') && (
                    <span className="tag tag-favorite">
                      <Star size={10} fill="currentColor" /> 收藏
                    </span>
                  )}
                  {run.tags.includes('archived') && (
                    <span className="tag tag-archived">
                      <Archive size={10} /> 已归档
                    </span>
                  )}
                </div>
              )}
              {/* Notes preview */}
              {getNotes(run) && (
                <div className="text-muted" style={{ fontSize: '0.75rem', marginTop: '0.25rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <MessageSquare size={10} style={{ marginRight: '0.25rem', verticalAlign: 'middle' }} />
                  {getNotes(run)}
                </div>
              )}
              {run.started_at && (
                <div className="text-muted" style={{ fontSize: '0.8125rem', marginTop: '0.5rem' }}>
                  {new Date(run.started_at).toLocaleString('zh-CN')}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Action Menu Popup */}
      {actionMenu && (
        <>
          <div
            style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 999 }}
            onClick={() => setActionMenu(null)}
          />
          <div
            className="action-menu"
            style={{
              position: 'fixed',
              top: actionMenu.y,
              left: actionMenu.x,
              zIndex: 1000,
            }}
          >
            <button
              className="action-menu-item"
              onClick={(e) => {
                const run = runs.find(r => r.run_id === actionMenu.runId);
                setNotesModal({ runId: actionMenu.runId, notes: getNotes(run) });
              }}
            >
              <MessageSquare size={14} />
              备注
            </button>
            <button
              className="action-menu-item"
              onClick={(e) => handleFavorite(actionMenu.runId, e)}
            >
              <Star size={14} />
              {runs.find(r => r.run_id === actionMenu.runId)?.tags?.includes('favorite') ? '取消收藏' : '收藏'}
            </button>
            <button
              className="action-menu-item"
              onClick={(e) => handleArchive(actionMenu.runId, e)}
            >
              <Archive size={14} />
              {runs.find(r => r.run_id === actionMenu.runId)?.tags?.includes('archived') ? '取消归档' : '归档'}
            </button>
            <div className="action-menu-divider" />
            <button
              className="action-menu-item danger"
              onClick={(e) => handleDelete(actionMenu.runId, e)}
            >
              <Trash2 size={14} />
              删除
            </button>
          </div>
        </>
      )}

      {/* Notes Modal */}
      {notesModal && (
        <div className="modal-overlay" onClick={() => setNotesModal(null)}>
          <div className="modal" style={{ maxWidth: '400px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">工作流备注</h2>
              <button className="btn btn-ghost btn-icon" onClick={() => setNotesModal(null)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <textarea
                className="form-input"
                placeholder="添加备注..."
                value={notesModal.notes}
                onChange={(e) => setNotesModal({ ...notesModal, notes: e.target.value })}
                style={{ minHeight: '100px' }}
              />
            </div>
            <div style={{ padding: '0 1.5rem 1.5rem', display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setNotesModal(null)}>
                取消
              </button>
              <button className="btn btn-primary" onClick={(e) => handleNotes(notesModal.runId, notesModal.notes, e)}>
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cleanup Modal */}
      {cleanupModal && (
        <div className="modal-overlay" onClick={() => setCleanupModal(null)}>
          <div className="modal" style={{ maxWidth: '450px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">
                <Wand size={20} style={{ marginRight: '0.5rem' }} />
                清理旧工作流
              </h2>
              <button className="btn btn-ghost btn-icon" onClick={() => setCleanupModal(null)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              {cleanupModal.loading ? (
                <div className="loading">
                  <div className="spinner" />
                  <span style={{ marginLeft: '0.5rem' }}>正在扫描旧工作流...</span>
                </div>
              ) : (
                <>
                  <p style={{ marginBottom: '1rem' }}>
                    找到 <strong>{cleanupModal.count}</strong> 个超过 {cleanupModal.olderThanDays} 天的
                    {cleanupModal.status === 'failed' ? '失败' : '已完成'} 工作流。
                  </p>
                  {cleanupModal.preview.length > 0 && (
                    <div style={{
                      background: 'var(--bg-secondary)',
                      borderRadius: 'var(--radius-md)',
                      padding: '0.75rem',
                      maxHeight: '150px',
                      overflow: 'auto',
                      fontSize: '0.8125rem'
                    }}>
                      {cleanupModal.preview.map(id => (
                        <div key={id} style={{ fontFamily: 'var(--font-code)', marginBottom: '0.25rem' }}>
                          {id}
                        </div>
                      ))}
                      {cleanupModal.count > cleanupModal.preview.length && (
                        <div className="text-muted">...还有 {cleanupModal.count - cleanupModal.preview.length} 个</div>
                      )}
                    </div>
                  )}
                  <p style={{ marginTop: '1rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                    清理将永久删除这些工作流及其所有关联数据。
                  </p>
                </>
              )}
            </div>
            {!cleanupModal.loading && (
              <div style={{ padding: '0 1.5rem 1.5rem', display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <button className="btn btn-secondary" onClick={() => setCleanupModal(null)}>
                  取消
                </button>
                <button className="btn btn-danger" onClick={handleCleanupExecute}>
                  <Trash size={16} />
                  确认清理
                </button>
              </div>
            )}
          </div>
        </div>
      )}
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

export default Workflows;
