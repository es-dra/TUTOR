// TUTOR API 客户端
const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8080';

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
    if (!res.ok) throw new Error('启动工作流失败');
    return res.json();
  },

  // 获取运行状态
  async getRunStatus(runId) {
    const res = await fetch(`${API_BASE}/runs/${runId}`);
    if (!res.ok) throw new Error('获取状态失败');
    return res.json();
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
    if (!res.ok) throw new Error('获取列表失败');
    return res.json();
  },

  // 删除运行
  async deleteRun(runId) {
    const res = await fetch(`${API_BASE}/runs/${runId}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('删除失败');
    return res.json();
  },

  // 更新运行标签（归档/收藏）
  async updateRunTags(runId, tags) {
    const res = await fetch(`${API_BASE}/runs/${runId}/tags`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags })
    });
    if (!res.ok) throw new Error('更新标签失败');
    return res.json();
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
    if (!res.ok) throw new Error('获取统计失败');
    return res.json();
  }
};

export default api;
