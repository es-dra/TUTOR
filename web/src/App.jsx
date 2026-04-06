import React, { useState, useEffect } from 'react';
import { Brain, BarChart3, FlaskConical, Shield, Settings as SettingsIcon, Plus, AlertTriangle, Sparkles } from 'lucide-react';
import Dashboard from './pages/Dashboard.jsx';
import Workflows from './pages/Workflows.jsx';
import WorkflowDetail from './pages/WorkflowDetail.jsx';
import NewWorkflow from './pages/NewWorkflow.jsx';
import Approvals from './pages/Approvals.jsx';
import SettingsPage from './pages/Settings.jsx';
import V3Dashboard from './pages/v3/V3Dashboard.jsx';
import ProjectArena from './pages/v3/ProjectArena.jsx';
import api from './api.js';

function App() {
  const [currentPage, setCurrentPage] = useState('v3-dashboard');
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [selectedProject, setSelectedProject] = useState(null);
  const [health, setHealth] = useState(null);
  const [hasApiKey, setHasApiKey] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(console.error);
    checkApiConfig();
  }, []);

  const checkApiConfig = async () => {
    try {
      const res = await fetch(`/api/v1/providers`);
      const data = await res.json();
      const hasKey = Object.values(data).some(p => p.connected);
      setHasApiKey(hasKey);
    } catch (e) {
      // API not available yet
    }
  };

  const navItems = [
    { id: 'v3-dashboard', label: 'v3工作台', icon: Sparkles },
    { id: 'dashboard', label: '仪表盘', icon: BarChart3 },
    { id: 'workflows', label: '工作流', icon: FlaskConical },
    { id: 'approvals', label: '审批', icon: Shield },
    { id: 'new', label: '新建', icon: Plus },
  ];

  const renderPage = () => {
    if (currentPage === 'v3-arena' && selectedProject) {
      return (
        <ProjectArena 
          project={selectedProject} 
          onBack={() => {
            setSelectedProject(null);
            setCurrentPage('v3-dashboard');
          }} 
        />
      );
    }
    
    switch (currentPage) {
      case 'v3-dashboard':
        return (
          <V3Dashboard 
            onCreateProject={(project) => {
              setSelectedProject(project);
              setCurrentPage('v3-arena');
            }}
            onOpenProject={(project) => {
              setSelectedProject(project);
              setCurrentPage('v3-arena');
            }}
          />
        );
      case 'dashboard':
        return <Dashboard onViewRun={setSelectedRunId} />;
      case 'workflows':
        return <Workflows onViewRun={setSelectedRunId} />;
      case 'approvals':
        return <Approvals onViewRun={(runId) => {
          setSelectedRunId(runId);
          setCurrentPage('workflows');
        }} />;
      case 'new':
        return <NewWorkflow onCreated={(runId) => {
          setSelectedRunId(runId);
          setCurrentPage('workflows');
        }} />;
      case 'settings':
        return <SettingsPage />;
      default:
        return (
          <V3Dashboard 
            onCreateProject={(project) => {
              setSelectedProject(project);
              setCurrentPage('v3-arena');
            }}
            onOpenProject={(project) => {
              setSelectedProject(project);
              setCurrentPage('v3-arena');
            }}
          />
        );
    }
  };

  return (
    <div className="app">
      {/* API Key Alert Banner */}
      {!hasApiKey && health?.status === 'ok' && (
        <div className="alert-banner">
          <div className="alert-banner-content">
            <div className="alert-banner-icon">
              <AlertTriangle size={14} />
            </div>
            <span><strong>请先配置 API Key</strong> 才能正常使用工作流</span>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => setCurrentPage('settings')}
            style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }}
          >
            去配置
          </button>
        </div>
      )}

      {/* Header */}
      <header className="header">
        <div className="logo" onClick={() => setCurrentPage('dashboard')}>
          <div className="logo-icon">
            <Brain size={22} />
          </div>
          <span>TUTOR</span>
        </div>

        <nav className="nav">
          {navItems.map(item => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={`nav-link ${currentPage === item.id ? 'active' : ''}`}
                onClick={() => {
                  setCurrentPage(item.id);
                  setSelectedRunId(null);
                }}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="header-actions">
          <button
            className="btn btn-ghost btn-icon"
            onClick={() => setCurrentPage('settings')}
            title="API 配置"
          >
            <SettingsIcon size={20} />
          </button>
          <div className={`status-badge ${health?.status === 'ok' ? 'online' : 'offline'}`}>
            <span className={`status-dot ${health?.status === 'ok' ? 'online' : 'offline'}`} />
            {health?.status === 'ok' ? '在线' : '离线'}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="main">
        {renderPage()}
      </main>

      {/* Workflow Detail Modal */}
      {selectedRunId && (
        <WorkflowDetail
          runId={selectedRunId}
          onClose={() => setSelectedRunId(null)}
        />
      )}
    </div>
  );
}

export default App;
