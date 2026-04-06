// TUTOR API 客户端 - 使用相对路径，Vite 开发服务器代理到后端
const API_BASE = '';

/**
 * 解析统一 API 响应格式
 * @param {Response} res - fetch Response 对象
 * @param {string} operationName - 操作名称，用于错误信息
 * @returns {Promise<any>} 解析后的数据
 */
async function parseResponse(res, operationName = '操作') {
  const data = await res.json();
  if (!res.ok) {
    const errorMsg = data?.error?.message || `${operationName}失败`;
    throw new Error(errorMsg);
  }
  // 兼容新旧格式：检查是否是新的 envelope 格式
  if (data.success !== undefined && data.data !== undefined) {
    if (!data.success) {
      throw new Error(data.error?.message || `${operationName}失败`);
    }
    return data;
  }
  // 旧格式直接返回
  return data;
}

export const api = {
  // 健康检查
  async health() {
    const res = await fetch(`${API_BASE}/health`);
    return res.json();
  },

  // 启动工作流
  async startRun(workflowType, params = {}, config = {}) {
    const res = await fetch(`${API_BASE}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflow_type: workflowType,
        params,
        config
      })
    });
    return parseResponse(res, '启动工作流');
  },

  // 获取运行状态
  async getRunStatus(runId) {
    const res = await fetch(`${API_BASE}/runs/${runId}`);
    const data = await parseResponse(res, '获取状态');
    // 兼容 envelope 格式
    return data.data || data;
  },

  // 列出所有运行
  async listRuns(status = null, workflowType = null, page = 1, limit = 20) {
    let url = `${API_BASE}/runs`;
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (workflowType) params.append('workflow_type', workflowType);
    if (page > 1) params.append('offset', String((page - 1) * limit));
    if (limit !== 20) params.append('limit', String(limit));
    if (params.toString()) url += `?${params.toString()}`;

    const res = await fetch(url);
    const data = await parseResponse(res, '获取列表');
    // 返回 envelope 格式的完整响应，让调用方处理分页
    return data;
  },

  // 删除运行
  async deleteRun(runId) {
    const res = await fetch(`${API_BASE}/runs/${runId}`, {
      method: 'DELETE'
    });
    return parseResponse(res, '删除');
  },

  // 批量删除运行
  async batchDeleteRuns(runIds) {
    const res = await fetch(`${API_BASE}/runs/batch-delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_ids: runIds })
    });
    return parseResponse(res, '批量删除');
  },

  // 清理旧运行 (dry_run=true 只返回预览)
  async cleanupOldRuns(status = null, olderThanDays = 7, dryRun = false) {
    let url = `${API_BASE}/runs/cleanup?older_than_days=${olderThanDays}&dry_run=${dryRun}`;
    if (status) url += `&status=${status}`;
    const res = await fetch(url);
    return parseResponse(res, '清理');
  },

  // 重试失败的工作流
  async retryRun(runId) {
    const res = await fetch(`${API_BASE}/runs/${runId}/retry`, {
      method: 'POST'
    });
    return parseResponse(res, '重试');
  },

  // 更新运行标签（归档/收藏）
  async updateRunTags(runId, tags) {
    const res = await fetch(`${API_BASE}/runs/${runId}/tags`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags })
    });
    return parseResponse(res, '更新标签');
  },

  // 获取SSE事件流
  createEventSource(runId, onMessage, onError) {
    const eventSource = new EventSource(`${API_BASE}/events/${runId}`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error('SSE解析失败:', e);
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE错误:', error);
      onError?.(error);
    };

    return eventSource;
  },

  // 文件上传
  async uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${API_BASE}/api/v1/uploads`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error('文件上传失败');
    return res.json();
  },

  async uploadFiles(files) {
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
    });

    const res = await fetch(`${API_BASE}/api/v1/uploads/multiple`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error('文件上传失败');
    return res.json();
  },

  async listUploadedFiles() {
    const res = await fetch(`${API_BASE}/api/v1/uploads`);
    if (!res.ok) throw new Error('获取文件列表失败');
    return res.json();
  },

  async deleteUploadedFile(fileId) {
    const res = await fetch(`${API_BASE}/api/v1/uploads/${fileId}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('删除文件失败');
    return res.json();
  },

  // 审批相关
  async listApprovals(runId = null, status = null) {
    let url = `${API_BASE}/approvals`;
    const params = new URLSearchParams();
    if (runId) params.append('run_id', runId);
    if (status) params.append('status', status);
    if (params.toString()) url += `?${params.toString()}`;

    const res = await fetch(url);
    if (!res.ok) throw new Error('获取审批列表失败');
    return res.json();
  },

  async approveRequest(approvalId, comment = '') {
    const res = await fetch(`${API_BASE}/approvals/${approvalId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment })
    });
    if (!res.ok) throw new Error('审批失败');
    return res.json();
  },

  async rejectRequest(approvalId, comment = '') {
    const res = await fetch(`${API_BASE}/approvals/${approvalId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment })
    });
    if (!res.ok) throw new Error('拒绝失败');
    return res.json();
  },

  // 指标
  async getMetrics() {
    const res = await fetch(`${API_BASE}/metrics`);
    if (!res.ok) throw new Error('获取指标失败');
    return res.text();
  },

  // 统计
  async getStats() {
    const res = await fetch(`${API_BASE}/stats`);
    const data = await parseResponse(res, '获取统计');
    return data.data || data;
  },

  // ============ V3 API ============
  // V3 Project API
  async createV3Project(name, description = '') {
    const res = await fetch(`${API_BASE}/api/v3/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description })
    });
    return parseResponse(res, '创建项目');
  },

  async listV3Projects(status = null, limit = 50, offset = 0) {
    let url = `${API_BASE}/api/v3/projects`;
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (limit !== 50) params.append('limit', String(limit));
    if (offset > 0) params.append('offset', String(offset));
    if (params.toString()) url += `?${params.toString()}`;
    
    const res = await fetch(url);
    return parseResponse(res, '获取项目列表');
  },

  async getV3Project(projectId) {
    const res = await fetch(`${API_BASE}/api/v3/projects/${projectId}`);
    return parseResponse(res, '获取项目详情');
  },

  async updateV3Project(projectId, data) {
    const res = await fetch(`${API_BASE}/api/v3/projects/${projectId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return parseResponse(res, '更新项目');
  },

  async deleteV3Project(projectId) {
    const res = await fetch(`${API_BASE}/api/v3/projects/${projectId}`, {
      method: 'DELETE'
    });
    return parseResponse(res, '删除项目');
  },

  async getV3ProjectConversations(projectId) {
    const res = await fetch(`${API_BASE}/api/v3/projects/${projectId}/conversations`);
    return parseResponse(res, '获取对话历史');
  },

  async listV3Roles() {
    const res = await fetch(`${API_BASE}/api/v3/projects/roles/list`);
    return parseResponse(res, '获取角色列表');
  },

  // V3项目标签管理
  async updateV3ProjectTags(projectId, tags) {
    const res = await fetch(`${API_BASE}/api/v3/projects/${projectId}/tags`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags })
    });
    return parseResponse(res, '更新项目标签');
  },

  async listV3ArchivedProjects(limit = 50, offset = 0) {
    let url = `${API_BASE}/api/v3/projects/list/archived`;
    const params = new URLSearchParams();
    if (limit !== 50) params.append('limit', String(limit));
    if (offset > 0) params.append('offset', String(offset));
    if (params.toString()) url += `?${params.toString()}`;
    
    const res = await fetch(url);
    return parseResponse(res, '获取归档项目');
  },

  async listV3FavoriteProjects(limit = 50, offset = 0) {
    let url = `${API_BASE}/api/v3/projects/list/favorites`;
    const params = new URLSearchParams();
    if (limit !== 50) params.append('limit', String(limit));
    if (offset > 0) params.append('offset', String(offset));
    if (params.toString()) url += `?${params.toString()}`;
    
    const res = await fetch(url);
    return parseResponse(res, '获取收藏项目');
  },

  // WebSocket连接
  createWebSocket(projectId, handlers = {}) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/projects/${projectId}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
      handlers.onOpen?.();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handlers.onMessage?.(data);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      handlers.onError?.(error);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      handlers.onClose?.();
    };

    return {
      send: (type, data = {}) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type, data }));
        }
      },
      close: () => {
        ws.close();
      },
      readyState: () => ws.readyState
    };
  }
};

export default api;
