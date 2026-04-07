import React, { useState, useEffect, useRef } from 'react';
import { Lightbulb, FileText, Beaker, PenTool, Send, Upload, X, Search, Sparkles, ChevronLeft, ArrowRight, FolderOpen, Link2, Plus } from 'lucide-react';
import api from '../api.js';

const WORKFLOW_TYPES = [
  {
    id: 'idea',
    name: '创意生成',
    icon: Lightbulb,
    description: '从文献分析到创新想法生成',
    color: '#f59e0b',
    bgColor: '#FEF3C7',
    inputPlaceholder: '例如: LLM、Transformer、Diffusion Model\n或描述你的研究方向: 基于Transformer的图像分割\n或输入 arXiv URL: https://arxiv.org/abs/2301.00001',
    inputHint: '支持: 算法缩写(LLM/ViT/GAN)、领域关键词、arXiv链接、本地PDF路径',
  },
  {
    id: 'experiment',
    name: '实验执行',
    icon: Beaker,
    description: '自动化实验运行和结果分析',
    color: '#10b981',
    bgColor: '#D1FAE5',
  },
  {
    id: 'review',
    name: '论文评审',
    icon: FileText,
    description: 'AI 辅助论文审阅和改进',
    color: '#6366f1',
    bgColor: '#E0E7FF',
  },
  {
    id: 'write',
    name: '论文撰写',
    icon: PenTool,
    description: '端到端论文写作支持',
    color: '#ec4899',
    bgColor: '#FCE7F3',
  },
];

function NewWorkflow({ onCreated }) {
  const [mode, setMode] = useState('independent'); // 'independent' | 'continue'
  const [step, setStep] = useState(1); // 1: select mode/type, 2: fill params
  const [selectedType, setSelectedType] = useState(null);
  const [params, setParams] = useState({
    input: '',
    title: '',
    topic: '',
  });
  const [files, setFiles] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzedKeywords, setAnalyzedKeywords] = useState([]);
  const [existingProjects, setExistingProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const fileInputRef = useRef(null);

  const typeConfig = WORKFLOW_TYPES.find(t => t.id === selectedType);

  // Load existing projects for "continue" mode
  useEffect(() => {
    if (mode === 'continue') {
      loadProjects();
    }
  }, [mode]);

  const loadProjects = async () => {
    try {
      const res = await fetch('/api/v1/projects');
      const data = await res.json();
      // 兼容三种格式：
      // 1) 直接数组: [...]
      // 2) Envelope: { success, data: [...] }
      // 3) Legacy: { projects: [...] }
      if (Array.isArray(data)) {
        setExistingProjects(data);
      } else if (Array.isArray(data?.data)) {
        setExistingProjects(data.data);
      } else if (Array.isArray(data?.projects)) {
        setExistingProjects(data.projects);
      } else {
        setExistingProjects([]);
      }
    } catch (err) {
      console.error('加载项目失败:', err);
      setExistingProjects([]);
    }
  };

  const analyzeInput = async (text) => {
    if (!text.trim()) {
      setAnalyzedKeywords([]);
      return;
    }
    setAnalyzing(true);
    const keywords = extractKeywords(text);
    setAnalyzedKeywords(keywords);
    setAnalyzing(false);
  };

  const extractKeywords = (text) => {
    const keywords = [];
    const arxivPattern = /arxiv\.org\/abs\/(\d+\.\d+)/g;
    const matches = text.match(arxivPattern);
    if (matches) {
      keywords.push(...matches.map(m => ({ type: 'arxiv', value: `arXiv: ${m.split('/').pop()}` })));
    }
    const algos = ['llm', 'vit', 'gan', 'vae', 'transformer', 'bert', 'gpt', 'diffusion', 'clip', 'rl', 'nlp', 'cv'];
    for (const algo of algos) {
      if (text.toLowerCase().includes(algo)) {
        keywords.push({ type: 'keyword', value: algo.toUpperCase() });
      }
    }
    return keywords.slice(0, 8);
  };

  const handleFileUpload = (e) => {
    const newFiles = Array.from(e.target.files || []).map(f => ({
      name: f.name,
      size: f.size,
    }));
    setFiles(prev => [...prev, ...newFiles.filter(nf => !prev.some(ef => ef.name === nf.name))]);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    const newFiles = Array.from(e.dataTransfer.files).map(f => ({
      name: f.name,
      size: f.size,
    }));
    setFiles(prev => [...prev, ...newFiles.filter(nf => !prev.some(ef => ef.name === nf.name))]);
  };

  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleInputChange = (e) => {
    const value = e.target.value;
    setParams(prev => ({ ...prev, input: value }));
    if (selectedType === 'idea') {
      analyzeInput(value);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedType) return;

    setSubmitting(true);
    setError(null);

    try {
      const paperSources = [];
      const lines = params.input.split('\n').filter(l => l.trim());
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('http') && trimmed.includes('arxiv.org')) {
          paperSources.push(trimmed);
        } else if (trimmed.startsWith('/') || trimmed.startsWith('C:') || trimmed.startsWith('.')) {
          paperSources.push(trimmed);
        }
      }

      const requestParams = {
        input: params.input,
        keywords: analyzedKeywords.filter(k => k.type === 'keyword').map(k => k.value),
        paper_sources: paperSources.length > 0 ? paperSources : undefined,
      };

      // If continuing a project, include project_id
      if (mode === 'continue' && selectedProject) {
        requestParams.project_id = selectedProject.project_id;
        // For experiment/review/write, use the project's context
        if (selectedType !== 'idea') {
          requestParams.continue_from = selectedProject.last_workflow_type || 'idea';
        }
      }

      Object.keys(requestParams).forEach(k => {
        if (!requestParams[k] || (Array.isArray(requestParams[k]) && requestParams[k].length === 0)) {
          delete requestParams[k];
        }
      });

      const result = await api.startRun(selectedType, requestParams);
      onCreated(result.run_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setStep(1);
    setSelectedType(null);
    setParams({ input: '', title: '', topic: '' });
    setFiles([]);
    setAnalyzedKeywords([]);
    setError(null);
    setSelectedProject(null);
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">新建工作流</h1>
        <p className="page-subtitle">
          {step === 1 ? '选择工作流类型开始' : `填写 ${typeConfig?.name || ''} 工作流参数`}
        </p>
      </div>

      {step === 1 && mode === 'independent' ? (
        <>
          {/* Mode Selection */}
          <div className="mode-selector">
            <button
              className={`mode-card ${mode === 'independent' ? 'selected' : ''}`}
              onClick={() => setMode('independent')}
            >
              <div className="mode-icon">
                <Plus size={24} />
              </div>
              <div className="mode-info">
                <h3>独立工作流</h3>
                <p>从零开始，创建全新的研究流程</p>
              </div>
            </button>
            <button
              className={`mode-card ${mode === 'continue' ? 'selected' : ''}`}
              onClick={() => setMode('continue')}
            >
              <div className="mode-icon">
                <Link2 size={24} />
              </div>
              <div className="mode-info">
                <h3>继续项目</h3>
                <p>基于已有项目继续工作流</p>
              </div>
            </button>
          </div>

          {/* Type Selection Grid */}
          <div className="type-grid">
            {WORKFLOW_TYPES.map(type => {
              const Icon = type.icon;
              return (
                <div
                  key={type.id}
                  className={`type-card ${selectedType === type.id ? 'selected' : ''}`}
                  onClick={() => setSelectedType(type.id)}
                  style={{
                    borderColor: selectedType === type.id ? type.color : 'transparent',
                    background: selectedType === type.id ? type.bgColor : undefined,
                  }}
                >
                  <div
                    className="type-icon"
                    style={{ background: type.bgColor, color: type.color }}
                  >
                    <Icon size={28} />
                  </div>
                  <h3 className="type-name" style={{ color: type.color }}>{type.name}</h3>
                  <p className="type-description">{type.description}</p>
                </div>
              );
            })}
          </div>

          {selectedType && (
            <div style={{ marginTop: '2rem', display: 'flex', justifyContent: 'center' }}>
              <button
                className="btn btn-primary"
                style={{ padding: '0.875rem 2rem', fontSize: '1rem' }}
                onClick={() => setStep(2)}
              >
                继续
                <ArrowRight size={18} />
              </button>
            </div>
          )}
        </>
      ) : step === 1 && mode === 'continue' ? (
        <>
          {/* Mode Selection */}
          <div className="mode-selector">
            <button
              className={`mode-card ${mode === 'independent' ? 'selected' : ''}`}
              onClick={() => setMode('independent')}
            >
              <div className="mode-icon">
                <Plus size={24} />
              </div>
              <div className="mode-info">
                <h3>独立工作流</h3>
                <p>从零开始，创建全新的研究流程</p>
              </div>
            </button>
            <button
              className={`mode-card ${mode === 'continue' ? 'selected' : ''}`}
              onClick={() => setMode('continue')}
            >
              <div className="mode-icon">
                <Link2 size={24} />
              </div>
              <div className="mode-info">
                <h3>继续项目</h3>
                <p>基于已有项目继续工作流</p>
              </div>
            </button>
          </div>

          {/* Project Selection */}
          <div className="card-glass" style={{ marginTop: '1.5rem' }}>
            <h3 className="card-title" style={{ marginBottom: '1rem' }}>
              <FolderOpen size={20} style={{ marginRight: '0.5rem' }} />
              选择要继续的项目
            </h3>
            {existingProjects.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                <p>暂无项目</p>
                <p style={{ fontSize: '0.875rem' }}>请先创建一个创意生成工作流</p>
                <button
                  className="btn btn-primary"
                  style={{ marginTop: '1rem' }}
                  onClick={() => {
                    setMode('independent');
                    setSelectedType('idea');
                  }}
                >
                  创建创意工作流
                </button>
              </div>
            ) : (
              <div className="project-list">
                {existingProjects.map(project => (
                  <div
                    key={project.project_id}
                    className={`project-item ${selectedProject?.project_id === project.project_id ? 'selected' : ''}`}
                    onClick={() => setSelectedProject(project)}
                  >
                    <div className="project-info">
                      <h4>{project.name || project.project_id}</h4>
                      <div className="project-meta">
                        <span className="tag tag-idea">创意生成</span>
                        {project.status && <span className={`status-dot ${project.status}`}>{project.status}</span>}
                      </div>
                    </div>
                    <div className="project-stats">
                      {project.idea_count !== undefined && (
                        <span title="想法数量">{project.idea_count} 个想法</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Next Workflow Type */}
          {selectedProject && (
            <div className="card-glass" style={{ marginTop: '1rem' }}>
              <h3 className="card-title" style={{ marginBottom: '1rem' }}>
                选择下一步工作流
              </h3>
              <div className="type-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                {WORKFLOW_TYPES.filter(t => t.id !== 'idea').map(type => {
                  const Icon = type.icon;
                  return (
                    <div
                      key={type.id}
                      className={`type-card ${selectedType === type.id ? 'selected' : ''}`}
                      onClick={() => {
                        setSelectedType(type.id);
                        setStep(2);
                      }}
                      style={{
                        borderColor: selectedType === type.id ? type.color : 'transparent',
                        background: selectedType === type.id ? type.bgColor : undefined,
                      }}
                    >
                      <div
                        className="type-icon"
                        style={{ background: type.bgColor, color: type.color }}
                      >
                        <Icon size={24} />
                      </div>
                      <h3 className="type-name" style={{ color: type.color, fontSize: '0.9rem' }}>{type.name}</h3>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="card-glass">
          <div className="card-header">
            <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {typeConfig && <typeConfig.icon size={20} style={{ color: typeConfig.color }} />}
              {typeConfig?.name}
              {mode === 'continue' && selectedProject && (
                <span className="text-muted" style={{ fontWeight: 'normal', fontSize: '0.875rem' }}>
                  — 继续项目 {selectedProject.project_id.substring(0, 8)}...
                </span>
              )}
            </h2>
            <button className="btn btn-ghost" onClick={resetForm}>
              <ChevronLeft size={18} />
              返回
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            {/* Idea Workflow - Smart Input */}
            {selectedType === 'idea' && (
              <>
                <div className="form-group">
                  <label className="form-label">
                    <Sparkles size={16} style={{ color: '#f59e0b' }} />
                    研究方向 / 关键词
                  </label>
                  <textarea
                    className="form-input"
                    style={{ minHeight: '140px' }}
                    placeholder={typeConfig?.inputPlaceholder}
                    value={params.input}
                    onChange={handleInputChange}
                    onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                    onDragLeave={() => setDragActive(false)}
                    onDrop={handleDrop}
                  />
                  <small className="text-muted" style={{ marginTop: '0.25rem', display: 'block' }}>
                    {typeConfig?.inputHint}
                  </small>
                </div>

                {/* Keywords */}
                {(analyzedKeywords.length > 0 || analyzing) && (
                  <div className="form-group">
                    <label className="form-label">
                      <Search size={16} />
                      识别的关键词
                    </label>
                    <div className="keyword-tags">
                      {analyzing ? (
                        <span className="text-muted">分析中...</span>
                      ) : (
                        analyzedKeywords.map((kw, i) => (
                          <span key={i} className={`keyword-tag ${kw.type}`}>
                            {kw.value}
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                )}

                {/* File Upload */}
                <div className="form-group">
                  <label className="form-label">
                    <Upload size={16} />
                    本地文献文件（可选）
                  </label>
                  <div
                    onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                    onDragLeave={() => setDragActive(false)}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`dropzone ${dragActive ? 'active' : ''}`}
                  >
                    <div className="dropzone-icon">
                      <Upload size={24} />
                    </div>
                    <p className="dropzone-text">拖放 PDF 文件到此处，或点击选择文件</p>
                    <p className="dropzone-hint">支持 PDF, TXT, MD, TEX 格式</p>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.txt,.md,.tex"
                    onChange={handleFileUpload}
                    style={{ display: 'none' }}
                  />

                  {files.length > 0 && (
                    <div style={{ marginTop: '1rem' }}>
                      {files.map((file, index) => (
                        <div key={index} className="file-item">
                          <div className="file-info">
                            <div className="file-icon">
                              <FileText size={18} />
                            </div>
                            <div>
                              <div className="file-name">{file.name}</div>
                              <div className="file-size">{(file.size / 1024).toFixed(1)} KB</div>
                            </div>
                          </div>
                          <button
                            type="button"
                            className="btn btn-ghost btn-icon"
                            onClick={() => removeFile(index)}
                          >
                            <X size={16} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Examples */}
                <div className="examples-card">
                  <h4 className="examples-title">输入示例</h4>
                  <div className="example-item">
                    <strong>算法:</strong> LLM, ViT, GAN, Diffusion
                  </div>
                  <div className="example-item">
                    <strong>领域:</strong> NLP, Computer Vision
                  </div>
                  <div className="example-item">
                    <strong>arXiv:</strong> https://arxiv.org/abs/2301.00001
                  </div>
                </div>
              </>
            )}

            {/* Basic params for other types */}
            {selectedType === 'experiment' && (
              <div className="form-group">
                <label className="form-label">研究想法</label>
                <textarea
                  className="form-input"
                  placeholder="描述你的研究想法和实验设计..."
                  value={params.input}
                  onChange={(e) => setParams({ ...params, input: e.target.value })}
                />
                {mode === 'continue' && selectedProject && (
                  <small className="text-muted" style={{ marginTop: '0.5rem', display: 'block' }}>
                    将使用项目中已有的想法作为输入
                  </small>
                )}
              </div>
            )}

            {selectedType === 'review' && (
              <div className="form-group">
                <label className="form-label">论文路径或 URL</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="https://arxiv.org/abs/2301.00001"
                  value={params.input}
                  onChange={(e) => setParams({ ...params, input: e.target.value })}
                />
              </div>
            )}

            {selectedType === 'write' && (
              <>
                <div className="form-group">
                  <label className="form-label">论文标题</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="输入论文标题"
                    value={params.title}
                    onChange={(e) => setParams({ ...params, title: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">论文主题/摘要</label>
                  <textarea
                    className="form-input"
                    placeholder="描述论文的主要内容和研究方向..."
                    value={params.topic}
                    onChange={(e) => setParams({ ...params, topic: e.target.value })}
                  />
                </div>
              </>
            )}

            {error && (
              <div style={{
                padding: '0.875rem',
                background: '#FEE2E2',
                color: '#991B1B',
                borderRadius: 'var(--radius-md)',
                marginBottom: '1rem',
                fontWeight: 500,
              }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={resetForm}
                disabled={submitting}
              >
                取消
              </button>
              <button
                type="submit"
                className="btn btn-success"
                disabled={submitting || (selectedType === 'idea' && !params.input?.trim())}
              >
                <Send size={18} />
                {submitting ? '启动中...' : '启动工作流'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default NewWorkflow;
