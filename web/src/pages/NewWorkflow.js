import React, { useState, useRef } from 'react';
import { Lightbulb, FileText, Beaker, PenTool, Send, Upload, X, Search, Sparkles } from 'lucide-react';
import api from '../api';

const WORKFLOW_TYPES = [
  {
    id: 'idea',
    name: '创意生成',
    icon: <Lightbulb size={32} />,
    description: '从文献分析到创新想法生成',
    color: '#f59e0b',
    inputPlaceholder: '例如: LLM、Transformer、Diffusion Model\n或描述你的研究方向: 基于Transformer的图像分割\n或输入 arXiv URL: https://arxiv.org/abs/2301.00001',
    inputHint: '支持: 算法缩写(LLM/ViT/GAN)、领域关键词、计算机视觉/NLP)、arXiv链接、本地PDF路径、自然语言描述',
  },
  {
    id: 'experiment',
    name: '实验执行',
    icon: <Beaker size={32} />,
    description: '自动化实验运行和结果分析',
    color: '#10b981',
  },
  {
    id: 'review',
    name: '论文评审',
    icon: <FileText size={32} />,
    description: 'AI 辅助论文审阅和改进',
    color: '#6366f1',
  },
  {
    id: 'write',
    name: '论文撰写',
    icon: <PenTool size={32} />,
    description: '端到端论文写作支持',
    color: '#ec4899',
  },
];

function NewWorkflow({ onCreated }) {
  const [selectedType, setSelectedType] = useState(null);
  const [params, setParams] = useState({
    input: '',
    papers: [],
    files: [],
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzedKeywords, setAnalyzedKeywords] = useState([]);
  const fileInputRef = useRef(null);

  // 智能分析输入
  const analyzeInput = async (text) => {
    if (!text.trim()) {
      setAnalyzedKeywords([]);
      return;
    }

    setAnalyzing(true);
    // 简单的本地关键词提取（实际项目中可以调用后端API）
    const keywords = extractKeywords(text);
    setAnalyzedKeywords(keywords);
    setAnalyzing(false);
  };

  // 本地关键词提取
  const extractKeywords = (text) => {
    const keywords = [];
    const lines = text.toLowerCase().split('\n').filter(l => l.trim());

    // 检测 arXiv URL
    const arxivPattern = /arxiv\.org\/abs\/(\d+\.\d+)/g;
    const matches = text.match(arxivPattern);
    if (matches) {
      keywords.push(...matches.map(m => `arXiv: ${m.split('/').pop()}`));
    }

    // 检测常见算法缩写
    const algos = ['llm', 'vit', 'gan', 'vae', 'transformer', 'bert', 'gpt', 'diffusion', 'clip', 'rl', 'nlp', 'cv'];
    for (const algo of algos) {
      if (text.toLowerCase().includes(algo)) {
        keywords.push(algo.toUpperCase());
      }
    }

    // 提取纯词
    const words = text.split(/\s+/).filter(w => w.length > 2);
    const commonWords = ['the', 'and', 'for', 'with', 'from', 'this', 'that', 'based', 'using', 'research', 'paper', 'study'];
    const interestingWords = words.filter(w => !commonWords.includes(w.toLowerCase()));
    keywords.push(...interestingWords.slice(0, 5).map(w => w.replace(/[^a-zA-Z]/g, '')));

    return [...new Set(keywords)].slice(0, 8);
  };

  // 处理文件上传
  const handleFileUpload = (e) => {
    const files = Array.from(e.target.files || []);
    addFiles(files);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    const files = Array.from(e.dataTransfer.files);
    addFiles(files);
  };

  const addFiles = (files) => {
    const newFiles = files.map(f => ({
      name: f.name,
      path: f.path || f.name,
      type: f.type,
      size: f.size,
      file: f, // 保存原始 File 对象用于上传
    }));
    setParams(prev => ({
      ...prev,
      files: [...prev.files, ...newFiles.filter(
        nf => !prev.files.some(ef => ef.name === nf.name)
      )],
    }));
  };

  const removeFile = (index) => {
    setParams(prev => ({
      ...prev,
      files: prev.files.filter((_, i) => i !== index),
    }));
  };

  // 处理输入变化
  const handleInputChange = (e) => {
    const value = e.target.value;
    setParams(prev => ({ ...prev, input: value }));
    analyzeInput(value);
  };

  // 提交工作流
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedType) return;

    setSubmitting(true);
    setError(null);

    try {
      // 组合所有输入源
      const paperSources = [];

      // 1. 从文本输入中提取 arXiv URLs
      const lines = params.input.split('\n').filter(l => l.trim());
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('http') && trimmed.includes('arxiv.org')) {
          paperSources.push(trimmed);
        } else if (trimmed.startsWith('/') || trimmed.startsWith('C:') || trimmed.startsWith('.')) {
          // 本地路径（如果是有效的服务器路径）
          paperSources.push(trimmed);
        }
      }

      // 2. 上传本地文件到服务器
      if (params.files.length > 0) {
        setAnalyzing(true); // 复用这个状态显示上传进度
        try {
          const uploadedFiles = await api.uploadFiles(params.files.map(f => f.file));
          paperSources.push(...uploadedFiles.map(f => f.path));
        } catch (uploadErr) {
          console.error('File upload failed:', uploadErr);
          // 如果上传失败，继续使用文件名（可能会失败但不影响提交）
          paperSources.push(...params.files.map(f => f.path));
        }
        setAnalyzing(false);
      }

      // 构建请求参数
      const requestParams = {
        // 主要输入：用于智能解析
        input: params.input,
        // 关键词（从输入中提取）
        keywords: analyzedKeywords.filter(k => !k.startsWith('arXiv:')),
        // 文献源列表
        paper_sources: paperSources.length > 0 ? paperSources : undefined,
      };

      // 移除空值
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

  const renderParams = () => {
    if (!selectedType) return null;

    const typeConfig = WORKFLOW_TYPES.find(t => t.id === selectedType);
    if (selectedType !== 'idea') {
      // 其他工作流类型保持简单
      return renderBasicParams();
    }

    return (
      <>
        {/* 智能输入区域 */}
        <div className="form-group">
          <label className="form-label">
            <Sparkles size={16} style={{ marginRight: 8, color: '#f59e0b' }} />
            研究方向 / 关键词
          </label>
          <textarea
            className="form-input"
            style={{ minHeight: '120px' }}
            placeholder={typeConfig?.inputPlaceholder}
            value={params.input}
            onChange={handleInputChange}
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
          />
          <small style={{ color: 'var(--text-secondary)', marginTop: '0.25rem', display: 'block' }}>
            {typeConfig?.inputHint}
          </small>
        </div>

        {/* 识别的关键词 */}
        {(analyzedKeywords.length > 0 || analyzing) && (
          <div className="form-group">
            <label className="form-label">
              <Search size={16} style={{ marginRight: 8 }} />
              识别的关键词 / 搜索词
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {analyzing ? (
                <span style={{ color: 'var(--text-secondary)' }}>分析中...</span>
              ) : (
                analyzedKeywords.map((kw, i) => (
                  <span
                    key={i}
                    style={{
                      padding: '0.25rem 0.75rem',
                      background: kw.startsWith('arXiv:') ? '#dbeafe' : '#fef3c7',
                      color: kw.startsWith('arXiv:') ? '#1e40af' : '#92400e',
                      borderRadius: '9999px',
                      fontSize: '0.875rem',
                    }}
                  >
                    {kw}
                  </span>
                ))
              )}
            </div>
          </div>
        )}

        {/* 文件上传区域 */}
        <div className="form-group">
          <label className="form-label">
            <Upload size={16} style={{ marginRight: 8 }} />
            本地文献文件（可选）
          </label>

          {/* 拖放区域 */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${dragActive ? '#f59e0b' : 'var(--border)'}`,
              borderRadius: '8px',
              padding: '1.5rem',
              textAlign: 'center',
              cursor: 'pointer',
              background: dragActive ? '#fffbeb' : 'transparent',
              transition: 'all 0.2s',
            }}
          >
            <Upload size={24} style={{ color: 'var(--text-secondary)', marginBottom: '0.5rem' }} />
            <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
              拖放 PDF 文件到此处，或点击选择文件
            </p>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              支持 PDF, TXT, MD, TEX 格式
            </p>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.txt,.md,.tex"
            onChange={handleFileUpload}
            style={{ display: 'none' }}
          />

          {/* 已选择的文件列表 */}
          {params.files.length > 0 && (
            <div style={{ marginTop: '0.75rem' }}>
              {params.files.map((file, index) => (
                <div
                  key={index}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.5rem 0.75rem',
                    background: 'var(--surface)',
                    borderRadius: '6px',
                    marginBottom: '0.25rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <FileText size={16} style={{ color: '#ef4444' }} />
                    <span style={{ fontSize: '0.875rem' }}>{file.name}</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      ({(file.size / 1024).toFixed(1)} KB)
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeFile(index)}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: '0.25rem',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 输入格式示例 */}
        <div className="card" style={{ marginTop: '1rem', background: '#f8fafc' }}>
          <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.875rem' }}>输入示例</h4>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            <p style={{ margin: '0.25rem 0' }}>
              <strong>算法缩写:</strong> LLM, ViT, GAN, Diffusion, CLIP, Transformer
            </p>
            <p style={{ margin: '0.25rem 0' }}>
              <strong>研究领域:</strong> NLP, CV, Computer Vision, Reinforcement Learning
            </p>
            <p style={{ margin: '0.25rem 0' }}>
              <strong>arXiv链接:</strong> https://arxiv.org/abs/2301.00001
            </p>
            <p style={{ margin: '0.25rem 0' }}>
              <strong>本地文件:</strong> /path/to/paper.pdf
            </p>
            <p style={{ margin: '0.25rem 0' }}>
              <strong>自然语言:</strong> 基于Transformer的图像分割方法研究
            </p>
          </div>
        </div>
      </>
    );
  };

  const renderBasicParams = () => {
    switch (selectedType) {
      case 'experiment':
        return (
          <div className="form-group">
            <label className="form-label">研究想法</label>
            <textarea
              className="form-input"
              placeholder="描述你的研究想法和实验设计..."
              value={params.input || ''}
              onChange={(e) => setParams({ ...params, input: e.target.value })}
            />
          </div>
        );
      case 'review':
        return (
          <div className="form-group">
            <label className="form-label">论文路径或 URL</label>
            <input
              type="text"
              className="form-input"
              placeholder="https://arxiv.org/abs/2301.00001"
              value={params.input || ''}
              onChange={(e) => setParams({ ...params, input: e.target.value })}
            />
          </div>
        );
      case 'write':
        return (
          <>
            <div className="form-group">
              <label className="form-label">论文标题</label>
              <input
                type="text"
                className="form-input"
                placeholder="输入论文标题"
                value={params.title || ''}
                onChange={(e) => setParams({ ...params, title: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">论文主题/摘要</label>
              <textarea
                className="form-input"
                placeholder="描述论文的主要内容和研究方向..."
                value={params.topic || ''}
                onChange={(e) => setParams({ ...params, topic: e.target.value })}
              />
            </div>
          </>
        );
      default:
        return null;
    }
  };

  return (
    <div>
      <h1 style={{ marginBottom: '1.5rem' }}>新建工作流</h1>

      {!selectedType ? (
        <div className="workflow-grid">
          {WORKFLOW_TYPES.map(type => (
            <div
              key={type.id}
              className="workflow-card"
              onClick={() => setSelectedType(type.id)}
              style={{ borderColor: type.color, borderWidth: 2 }}
            >
              <div style={{ color: type.color, marginBottom: '0.5rem' }}>
                {type.icon}
              </div>
              <div className="workflow-title">{type.name}</div>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                {type.description}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">
              {WORKFLOW_TYPES.find(t => t.id === selectedType)?.name}
            </h2>
            <button
              className="btn btn-secondary"
              onClick={() => {
                setSelectedType(null);
                setParams({ input: '', papers: [], files: [] });
                setAnalyzedKeywords([]);
              }}
            >
              返回
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            {renderParams()}

            {error && (
              <div style={{
                padding: '0.75rem',
                background: '#fee2e2',
                color: '#991b1b',
                borderRadius: '6px',
                marginBottom: '1rem'
              }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setSelectedType(null);
                  setParams({ input: '', papers: [], files: [] });
                  setAnalyzedKeywords([]);
                }}
                disabled={submitting}
              >
                取消
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={submitting || !params.input?.trim()}
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
