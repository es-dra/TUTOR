import React, { useState, useEffect } from 'react';
import { Key, CheckCircle, XCircle, Loader, ExternalLink } from 'lucide-react';

function SettingsPage() {
  const [providers, setProviders] = useState({});
  const [loading, setLoading] = useState(true);
  const [validating, setValidating] = useState({});
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadProviders();
  }, []);

  const loadProviders = async () => {
    setLoading(true);
    try {
      const data = await fetch('http://localhost:8080/api/v1/providers').then(r => r.json());
      setProviders(data);
    } catch (err) {
      setError('无法加载 Provider 配置');
    } finally {
      setLoading(false);
    }
  };

  const handleValidate = async (name, apiKey, apiBase) => {
    setValidating({ ...validating, [name]: true });
    setMessage(null);
    try {
      const res = await fetch(`http://localhost:8080/api/v1/providers/${name}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, api_base: apiBase })
      });
      const result = await res.json();
      if (result.success) {
        setMessage({ type: 'success', text: `${name} 连接成功！API Key 已保存。` });
        loadProviders();
      } else {
        setError(`${name} 连接失败: ${result.message}`);
      }
    } catch (err) {
      setError(`${name} 连接失败: ${err.message}`);
    } finally {
      setValidating({ ...validating, [name]: false });
    }
  };

  if (loading) {
    return (
      <div className="loading">
        <Loader className="spinner" size={32} />
        <p>加载中...</p>
      </div>
    );
  }

  const providerList = Object.entries(providers);

  return (
    <div>
      <h1 style={{ marginBottom: '1.5rem' }}>API 配置</h1>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
          <Key size={20} />
          <h2 className="card-title" style={{ margin: 0 }}>模型 API Keys</h2>
        </div>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
          配置你的 AI 模型 API Key。你的 API Key 会安全保存在本地，不会上传到任何服务器。
        </p>

        {message && (
          <div style={{
            padding: '0.75rem',
            background: '#d1fae5',
            color: '#065f46',
            borderRadius: '6px',
            marginBottom: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem'
          }}>
            <CheckCircle size={18} />
            {message.text}
          </div>
        )}

        {error && (
          <div style={{
            padding: '0.75rem',
            background: '#fee2e2',
            color: '#991b1b',
            borderRadius: '6px',
            marginBottom: '1rem'
          }}>
            <XCircle size={18} style={{ display: 'inline', marginRight: '0.5rem' }} />
            {error}
          </div>
        )}

        <div style={{ display: 'grid', gap: '1.5rem' }}>
          {providerList.map(([name, provider]) => (
            <ProviderConfig
              key={name}
              name={name}
              provider={provider}
              isValidating={validating[name]}
              onValidate={handleValidate}
            />
          ))}
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: '0.5rem' }}>关于 API Key 安全</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
          你的 API Key 使用本地加密存储（需要设置 TUTOR_MASTER_KEY 环境变量以启用加密）。
          更多信息请查看 <a href="https://docs.tutor.ai" target="_blank" rel="noopener noreferrer" style={{ color: '#2563eb' }}>
            文档 <ExternalLink size={12} style={{ display: 'inline' }} /></a>。
        </p>
      </div>
    </div>
  );
}

function ProviderConfig({ name, provider, isValidating, onValidate }) {
  const [apiKey, setApiKey] = useState('');
  const [apiBase, setApiBase] = useState(provider.api_base || '');

  const providerNames = {
    openai: 'OpenAI',
    deepseek: 'DeepSeek',
    anthropic: 'Anthropic',
    azure: 'Azure OpenAI',
    local: 'Local (Ollama)'
  };

  const providerUrls = {
    openai: 'https://platform.openai.com/api-keys',
    deepseek: 'https://platform.deepseek.com/api_keys',
    anthropic: 'https://console.anthropic.com/settings/keys',
    azure: 'https://portal.azure.com',
    local: 'http://localhost:11434'
  };

  return (
    <div style={{
      padding: '1rem',
      border: '1px solid var(--border)',
      borderRadius: '8px'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <div>
          <h4 style={{ margin: 0 }}>{providerNames[name] || name}</h4>
          <code style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {provider.api_base || `${name}.com`}
          </code>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {provider.connected ? (
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#10b981', fontSize: '0.875rem' }}>
              <CheckCircle size={16} /> 已连接
            </span>
          ) : (
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#ef4444', fontSize: '0.875rem' }}>
              <XCircle size={16} /> 未连接
            </span>
          )}
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">API Key</label>
        <input
          type="password"
          className="form-input"
          placeholder={provider.connected ? '已配置 (不显示)' : 'sk-...'}
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
        {name !== 'local' && (
          <small style={{ color: 'var(--text-secondary)', marginTop: '0.25rem', display: 'block' }}>
            <a href={providerUrls[name]} target="_blank" rel="noopener noreferrer" style={{ color: '#2563eb' }}>
              获取 API Key <ExternalLink size={12} style={{ display: 'inline' }} />
            </a>
          </small>
        )}
      </div>

      {provider.api_base && (
        <div className="form-group">
          <label className="form-label">API Base (可选)</label>
          <input
            type="text"
            className="form-input"
            placeholder={provider.api_base}
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
          />
        </div>
      )}

      <button
        className="btn btn-primary"
        disabled={!apiKey || isValidating}
        onClick={() => onValidate(name, apiKey, apiBase)}
      >
        {isValidating ? (
          <>
            <Loader size={16} className="spinner" style={{ animation: 'spin 1s linear infinite' }} />
            验证中...
          </>
        ) : (
          '验证并保存'
        )}
      </button>
    </div>
  );
}

export default SettingsPage;
