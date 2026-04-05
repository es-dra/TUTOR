import React, { useState, useEffect } from 'react';
import { Key, CheckCircle, XCircle, Loader, ExternalLink, Shield } from 'lucide-react';

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
      const data = await fetch(`/api/v1/providers`).then(r => r.json());
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
    setError(null);
    try {
      const res = await fetch(`/api/v1/providers/${name}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, api_base: apiBase })
      });
      const result = await res.json();
      if (result.success) {
        setMessage({ type: 'success', text: `${getProviderName(name)} 连接成功！API Key 已保存。` });
        loadProviders();
      } else {
        setError(`${getProviderName(name)} 连接失败: ${result.message}`);
      }
    } catch (err) {
      setError(`${getProviderName(name)} 连接失败: ${err.message}`);
    } finally {
      setValidating({ ...validating, [name]: false });
    }
  };

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
      </div>
    );
  }

  const providerList = Object.entries(providers);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">API 配置</h1>
        <p className="page-subtitle">配置你的 AI 模型 API Keys</p>
      </div>

      {/* Messages */}
      {message && (
        <div className="card-glass" style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '1rem 1.25rem',
          background: 'var(--status-completed-bg)',
          color: 'var(--status-completed)',
          marginBottom: '1.5rem'
        }}>
          <CheckCircle size={20} />
          <span style={{ fontWeight: 500 }}>{message.text}</span>
        </div>
      )}

      {error && (
        <div className="card-glass" style={{
          padding: '1rem 1.25rem',
          background: 'var(--status-failed-bg)',
          color: 'var(--status-failed)',
          marginBottom: '1.5rem'
        }}>
          <XCircle size={20} style={{ display: 'inline', marginRight: '0.5rem' }} />
          <span style={{ fontWeight: 500 }}>{error}</span>
        </div>
      )}

      {/* Provider Config */}
      <div className="settings-section">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
          <div style={{
            width: 40,
            height: 40,
            background: 'var(--primary-50)',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--primary)'
          }}>
            <Key size={20} />
          </div>
          <div>
            <h2 className="settings-title">模型 API Keys</h2>
            <p className="settings-description">
              你的 API Key 会安全保存在本地，不会上传到任何服务器
            </p>
          </div>
        </div>

        <div style={{ display: 'grid', gap: '1.25rem' }}>
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

      {/* Security Info */}
      <div className="card-glass">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
          <div style={{
            width: 40,
            height: 40,
            background: 'var(--primary-50)',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--primary)',
            flexShrink: 0
          }}>
            <Shield size={20} />
          </div>
          <div>
            <h3 style={{ fontWeight: 600, marginBottom: '0.25rem' }}>关于 API Key 安全</h3>
            <p className="text-secondary" style={{ fontSize: '0.875rem' }}>
              你的 API Key 使用本地加密存储（需要设置 TUTOR_MASTER_KEY 环境变量以启用加密）。
              更多信息请查看 <a
                href="https://docs.tutor.ai"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--primary)' }}
              >
                文档 <ExternalLink size={12} style={{ display: 'inline' }} />
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProviderConfig({ name, provider, isValidating, onValidate }) {
  const [apiKey, setApiKey] = useState('');
  const [apiBase, setApiBase] = useState(provider.api_base || '');

  const getProviderName = (name) => {
    const names = {
      openai: 'OpenAI',
      deepseek: 'DeepSeek',
      anthropic: 'Anthropic',
      azure: 'Azure OpenAI',
      local: 'Local (Ollama)'
    };
    return names[name] || name;
  };

  const getProviderUrl = (name) => {
    const urls = {
      openai: 'https://platform.openai.com/api-keys',
      deepseek: 'https://platform.deepseek.com/api_keys',
      anthropic: 'https://console.anthropic.com/settings/keys',
      azure: 'https://portal.azure.com',
      local: 'http://localhost:11434'
    };
    return urls[name] || '#';
  };

  return (
    <div className="provider-card">
      <div className="provider-header">
        <div>
          <h4 className="provider-name">{getProviderName(name)}</h4>
          <code className="text-muted" style={{ fontSize: '0.75rem' }}>
            {provider.api_base || `${name}.com`}
          </code>
        </div>
        <div className={`provider-status ${provider.connected ? 'connected' : 'disconnected'}`}>
          {provider.connected ? (
            <>
              <CheckCircle size={16} />
              已连接
            </>
          ) : (
            <>
              <XCircle size={16} />
              未连接
            </>
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
          <small style={{ marginTop: '0.25rem', display: 'block' }}>
            <a
              href={getProviderUrl(name)}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--primary)' }}
            >
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
            <Loader size={16} className="spinner" />
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
