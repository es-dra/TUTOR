import React, { useState, useEffect } from 'react';
import { Brain, Play, BarChart3, FlaskConical, Shield, Settings as SettingsIcon } from 'lucide-react';
import api from './api';
import Dashboard from './pages/Dashboard';
import Workflows from './pages/Workflows';
import WorkflowDetail from './pages/WorkflowDetail';
import NewWorkflow from './pages/NewWorkflow';
import Approvals from './pages/Approvals';
import Settings from './pages/Settings';

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [health, setHealth] = useState(null);
  const [hasApiKey, setHasApiKey] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(console.error);
    checkApiConfig();
  }, []);

  const checkApiConfig = async () => {
    try {
      const res = await fetch('http://localhost:8080/api/v1/providers');
      const data = await res.json();
      const hasKey = Object.values(data).some(p => p.connected);
      setHasApiKey(hasKey);
    } catch (e) {
      // API not available yet
    }
  };

  const navItems = [
    { id: 'dashboard', label: '仪表盘', icon: <BarChart3 size={18} /> },
    { id: 'workflows', label: '工作流', icon: <FlaskConical size={18} /> },
    { id: 'approvals', label: '审批', icon: <Shield size={18} /> },
    { id: 'new', label: '新建', icon: <Play size={18} /> },
  ];

  return (
    <div className="app">
      {!hasApiKey && health?.status === 'ok' && (
        <div style={{
          background: '#fef3c7',
          color: '#92400e',
          padding: '0.75rem 1rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <span>
            <strong>请先配置 API Key</strong> 才能正常使用工作流。
          </span>
          <button
            className="btn btn-primary"
            style={{ background: '#d97706', fontSize: '0.875rem', padding: '0.25rem 0.75rem' }}
            onClick={() => setCurrentPage('settings')}
          >
            去配置
          </button>
        </div>
      )}

      <header className="header">
        <div className="logo">
          <Brain size={32} />
          <span>TUTOR</span>
        </div>

        <nav className="nav">
          {navItems.map(item => (
            <button
              key={item.id}
              className={`nav-link ${currentPage === item.id ? 'active' : ''}`}
              onClick={() => {
                setCurrentPage(item.id);
                setSelectedRunId(null);
              }}
            >
              {item.icon}
              <span style={{ marginLeft: '0.5rem' }}>{item.label}</span>
            </button>
          ))}
        </nav>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button
            className="nav-link"
            onClick={() => setCurrentPage('settings')}
            title="API 配置"
          >
            <SettingsIcon size={18} />
          </button>
          <span style={{
            padding: '0.25rem 0.75rem',
            borderRadius: '9999px',
            fontSize: '0.75rem',
            fontWeight: 500,
            background: health?.status === 'ok' ? '#d1fae5' : '#fee2e2',
            color: health?.status === 'ok' ? '#065f46' : '#991b1b'
          }}>
            {health?.status === 'ok' ? '● 在线' : '● 离线'}
          </span>
        </div>
      </header>

      <main className="main">
        {currentPage === 'dashboard' && (
          <Dashboard onViewRun={setSelectedRunId} />
        )}

        {currentPage === 'workflows' && (
          <Workflows onViewRun={setSelectedRunId} />
        )}

        {currentPage === 'approvals' && (
          <Approvals />
        )}

        {currentPage === 'new' && (
          <NewWorkflow onCreated={(runId) => {
            setSelectedRunId(runId);
            setCurrentPage('workflows');
          }} />
        )}

        {currentPage === 'settings' && (
          <Settings />
        )}

        {selectedRunId && (
          <WorkflowDetail
            runId={selectedRunId}
            onClose={() => setSelectedRunId(null)}
          />
        )}
      </main>
    </div>
  );
}

export default App;
