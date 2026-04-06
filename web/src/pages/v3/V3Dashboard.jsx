import React, { useState, useEffect, useCallback } from 'react';
import { Plus, FolderOpen, Brain, FlaskConical, PenTool, SearchCheck, Sparkles, Filter, ChevronLeft, ChevronRight, Archive, Trash2, Star, MessageSquare, MoreVertical, X, Trash, Check } from 'lucide-react';
import api from '../../api.js';

function V3Dashboard({ onCreateProject, onOpenProject }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');
  const [filter, setFilter] = useState({ status: '', tag: '' });
  const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0 });
  const [actionMenu, setActionMenu] = useState(null);
  const [notesModal, setNotesModal] = useState(null);
  const [selectedProjects, setSelectedProjects] = useState(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      setLoading(true);
      let data = await api.listV3Projects();
      
      // 应用过滤
      if (filter.tag) {
        if (filter.tag === 'archived') {
          data = await api.listV3ArchivedProjects();
        } else if (filter.tag === 'favorite') {
          data = await api.listV3FavoriteProjects();
        }
      } else if (filter.status) {
        data = data.filter(p => p.status === filter.status);
      }
      
      setProjects(data || []);
      setPagination(prev => ({ ...prev, total: (data || []).length }));
    } catch (e) {
      console.error('Failed to load projects:', e);
    } finally {
      setLoading(false);
    }
  }, [filter.status, filter.tag]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // Clear selection when filter changes
  useEffect(() => {
    setSelectedProjects(new Set());
  }, [filter.status, filter.tag]);

  const totalPages = Math.ceil(pagination.total / pagination.limit);

  const toggleSelectAll = () => {
    if (selectedProjects.size === projects.length) {
      setSelectedProjects(new Set());
    } else {
      setSelectedProjects(new Set(projects.map(p => p.id)));
    }
  };

  const toggleSelectProject = (projectId) => {
    const newSelected = new Set(selectedProjects);
    if (newSelected.has(projectId)) {
      newSelected.delete(projectId);
    } else {
      newSelected.add(projectId);
    }
    setSelectedProjects(newSelected);
  };

  const handleBatchDelete = async () => {
    if (selectedProjects.size === 0) return;
    if (!window.confirm(`确定要删除选中的 ${selectedProjects.size} 个项目吗？此操作不可恢复。`)) return;

    setBatchDeleting(true);
    try {
      const ids = Array.from(selectedProjects);
      for (const id of ids) {
        await api.deleteV3Project(id);
      }
      setSelectedProjects(new Set());
      loadProjects();
    } catch (err) {
      console.error('批量删除失败:', err);
      alert('批量删除失败: ' + err.message);
    } finally {
      setBatchDeleting(false);
    }
  };

  const handleArchive = async (projectId, e) => {
    e.stopPropagation();
    const project = projects.find(p => p.id === projectId);
    const tags = project.tags || [];
    const isArchived = tags.includes('archived');
    const newTags = isArchived
      ? tags.filter(t => t !== 'archived')
      : [...tags, 'archived'];
    try {
      await api.updateV3ProjectTags(projectId, newTags);
      loadProjects();
    } catch (err) {
      console.error('归档失败:', err);
    }
    setActionMenu(null);
  };

  const handleFavorite = async (projectId, e) => {
    e.stopPropagation();
    const project = projects.find(p => p.id === projectId);
    const tags = project.tags || [];
    const isFav = tags.includes('favorite');
    const newTags = isFav
      ? tags.filter(t => t !== 'favorite')
      : [...tags, 'favorite'];
    try {
      await api.updateV3ProjectTags(projectId, newTags);
      loadProjects();
    } catch (err) {
      console.error('收藏失败:', err);
    }
    setActionMenu(null);
  };

  const handleDelete = async (projectId, e) => {
    e.stopPropagation();
    if (!window.confirm('确定要删除此项目吗？此操作不可恢复。')) return;
    try {
      await api.deleteV3Project(projectId);
      loadProjects();
    } catch (err) {
      console.error('删除失败:', err);
    }
    setActionMenu(null);
  };

  const handleNotes = async (projectId, notes, e) => {
    if (e) e.stopPropagation();
    const project = projects.find(p => p.id === projectId);
    const tags = project.tags || [];
    const newTags = tags.filter(t => !t.startsWith('notes:'));
    if (notes.trim()) {
      newTags.push(`notes:${notes.trim()}`);
    }
    try {
      await api.updateV3ProjectTags(projectId, newTags);
      loadProjects();
    } catch (err) {
      console.error('保存备注失败:', err);
    }
    setNotesModal(null);
    setActionMenu(null);
  };

  const getNotes = (project) => {
    const tags = project.tags || [];
    const notesTag = tags.find(t => t.startsWith('notes:'));
    return notesTag ? notesTag.slice(6) : '';
  };

  const isFavorite = (project) => {
    const tags = project.tags || [];
    return tags.includes('favorite');
  };

  const isArchived = (project) => {
    const tags = project.tags || [];
    return tags.includes('archived');
  };

  const handleCreateProject = async (e) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    try {
      const project = await api.createV3Project(newProjectName, newProjectDesc);
      setShowCreateModal(false);
      setNewProjectName('');
      setNewProjectDesc('');
      loadProjects();
      if (onCreateProject) {
        onCreateProject(project);
      }
    } catch (e) {
      console.error('Failed to create project:', e);
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      idea: '#F59E0B',
      experiment: '#3B82F6',
      writing: '#8B5CF6',
      review: '#EC4899',
      completed: '#10B981',
      paused: '#6B7280'
    };
    return colors[status] || '#6B7280';
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'idea': return <Sparkles size={16} />;
      case 'experiment': return <FlaskConical size={16} />;
      case 'writing': return <PenTool size={16} />;
      case 'review': return <SearchCheck size={16} />;
      case 'completed': return <SearchCheck size={16} />;
      default: return <FolderOpen size={16} />;
    }
  };

  const statusOptions = [
    { value: '', label: '全部状态' },
    { value: 'idea', label: '创意阶段' },
    { value: 'experiment', label: '实验阶段' },
    { value: 'writing', label: '撰写阶段' },
    { value: 'review', label: '评审阶段' },
    { value: 'completed', label: '已完成' },
    { value: 'paused', label: '已暂停' },
  ];

  const tagOptions = [
    { value: '', label: '全部项目' },
    { value: 'favorite', label: '已收藏' },
    { value: 'archived', label: '已归档' },
  ];

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="v3-dashboard">
      <div className="page-header">
        <h1 className="page-title">科研项目工作台</h1>
        <p className="page-subtitle">管理和追踪您的所有AI辅助科研项目</p>
      </div>

      {/* 统计卡片 */}
      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-icon">
            <Brain size={24} />
          </div>
          <div className="stat-value">{projects.length}</div>
          <div className="stat-label">总项目数</div>
        </div>
        <div className="stat-card success">
          <div className="stat-icon">
            <SearchCheck size={24} />
          </div>
          <div className="stat-value">
            {projects.filter(p => p.status === 'completed').length}
          </div>
          <div className="stat-label">已完成</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-icon">
            <Sparkles size={24} />
          </div>
          <div className="stat-value">
            {projects.filter(p => p.status === 'idea' || p.status === 'experiment').length}
          </div>
          <div className="stat-label">进行中</div>
        </div>
      </div>

      {/* 批量操作栏 */}
      {selectedProjects.size > 0 && (
        <div className="batch-actions-bar">
          <span style={{ fontWeight: 500 }}>
            已选择 {selectedProjects.size} 个项目
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
            onClick={() => setSelectedProjects(new Set())}
          >
            取消选择
          </button>
        </div>
      )}

      {/* 筛选栏 */}
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
              setFilter({ ...filter, status: e.target.value, tag: '' });
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
            value={filter.tag}
            onChange={(e) => {
              setFilter({ ...filter, tag: e.target.value, status: '' });
              setPagination(p => ({ ...p, page: 1 }));
            }}
          >
            {tagOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button 
            className="btn btn-primary"
            onClick={() => setShowCreateModal(true)}
          >
            <Plus size={16} />
            创建新项目
          </button>
        </div>
      </div>

      {/* 分页 */}
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
            第 {pagination.page} / {totalPages} 页 (共 {pagination.total} 个)
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

      {/* 项目列表 */}
      {projects.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <FolderOpen size={40} />
          </div>
          <h3 className="empty-state-title">没有找到匹配的项目</h3>
          <p className="empty-state-text">
            尝试调整筛选条件或创建新的项目
          </p>
        </div>
      ) : (
        <div className="workflow-grid">
          {/* Header row with select all */}
          <div className="workflow-card select-all-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <button
                className={`checkbox ${selectedProjects.size === projects.length && projects.length > 0 ? 'checked' : ''}`}
                onClick={toggleSelectAll}
              >
                {selectedProjects.size === projects.length && projects.length > 0 && <Check size={12} />}
              </button>
              <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>全选</span>
            </div>
          </div>

          {projects.map(project => (
            <div 
              key={project.id} 
              className={`workflow-card ${selectedProjects.has(project.id) ? 'selected' : ''}`}
              onClick={() => onOpenProject(project)}
            >
              <div className="workflow-card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <button
                    className={`checkbox ${selectedProjects.has(project.id) ? 'checked' : ''}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleSelectProject(project.id);
                    }}
                  >
                    {selectedProjects.has(project.id) && <Check size={12} />}
                  </button>
                  <div className="workflow-type">
                    {getStatusIcon(project.status)}
                    &nbsp;{project.status.toUpperCase()}
                  </div>
                </div>
                <button
                  className="btn btn-ghost btn-icon"
                  style={{ padding: '0.25rem' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setActionMenu({ projectId: project.id, x: e.clientX, y: e.clientY });
                  }}
                >
                  <MoreVertical size={16} />
                </button>
              </div>
              <h3 className="workflow-title">{project.name}</h3>
              {project.description && (
                <p style={{ 
                  color: 'var(--text-secondary)', 
                  fontSize: '0.875rem',
                  marginBottom: '1rem'
                }}>
                  {project.description}
                </p>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="workflow-id">{project.id}</span>
                <span 
                  className="status-badge-workflow"
                  style={{ backgroundColor: `${getStatusColor(project.status)}20`, color: getStatusColor(project.status) }}
                >
                  {project.status}
                </span>
              </div>
              {/* Tags */}
              {(project.tags && project.tags.length > 0) && (
                <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                  {isFavorite(project) && (
                    <span className="tag tag-favorite">
                      <Star size={10} fill="currentColor" /> 收藏
                    </span>
                  )}
                  {isArchived(project) && (
                    <span className="tag tag-archived">
                      <Archive size={10} /> 已归档
                    </span>
                  )}
                </div>
              )}
              {/* Notes preview */}
              {getNotes(project) && (
                <div className="text-muted" style={{ fontSize: '0.75rem', marginTop: '0.25rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <MessageSquare size={10} style={{ marginRight: '0.25rem', verticalAlign: 'middle' }} />
                  {getNotes(project)}
                </div>
              )}
              <div style={{ 
                marginTop: '0.75rem', 
                fontSize: '0.75rem', 
                color: 'var(--text-muted)' 
              }}>
                更新于: {new Date(project.updated_at).toLocaleDateString('zh-CN')}
              </div>
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
                const project = projects.find(p => p.id === actionMenu.projectId);
                setNotesModal({ projectId: actionMenu.projectId, notes: getNotes(project) });
              }}
            >
              <MessageSquare size={14} />
              备注
            </button>
            <button
              className="action-menu-item"
              onClick={(e) => handleFavorite(actionMenu.projectId, e)}
            >
              <Star size={14} />
              {isFavorite(projects.find(p => p.id === actionMenu.projectId)) ? '取消收藏' : '收藏'}
            </button>
            <button
              className="action-menu-item"
              onClick={(e) => handleArchive(actionMenu.projectId, e)}
            >
              <Archive size={14} />
              {isArchived(projects.find(p => p.id === actionMenu.projectId)) ? '取消归档' : '归档'}
            </button>
            <div className="action-menu-divider" />
            <button
              className="action-menu-item danger"
              onClick={(e) => handleDelete(actionMenu.projectId, e)}
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
              <h2 className="modal-title">项目备注</h2>
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
              <button className="btn btn-primary" onClick={(e) => handleNotes(notesModal.projectId, notesModal.notes, e)}>
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 创建项目模态框 */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">创建新项目</h2>
              <button 
                className="btn btn-ghost btn-icon"
                onClick={() => setShowCreateModal(false)}
              >
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <form onSubmit={handleCreateProject}>
                <div className="form-group">
                  <label className="form-label">项目名称</label>
                  <input
                    type="text"
                    className="form-input"
                    value={newProjectName}
                    onChange={e => setNewProjectName(e.target.value)}
                    placeholder="输入项目名称..."
                    autoFocus
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">项目描述（可选）</label>
                  <textarea
                    className="form-input"
                    value={newProjectDesc}
                    onChange={e => setNewProjectDesc(e.target.value)}
                    placeholder="简单描述一下这个项目..."
                    rows={3}
                  />
                </div>
                <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
                  <button 
                    type="button" 
                    className="btn btn-secondary"
                    onClick={() => setShowCreateModal(false)}
                  >
                    取消
                  </button>
                  <button 
                    type="submit" 
                    className="btn btn-primary"
                    disabled={!newProjectName.trim()}
                  >
                    创建
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default V3Dashboard;
