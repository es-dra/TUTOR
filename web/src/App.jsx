import React, { useState, useEffect } from 'react';
import { Routes, Route, Link, useNavigate, useLocation } from 'react-router-dom';
import { Brain, BarChart3, FlaskConical, Shield, Settings as SettingsIcon, Plus, AlertTriangle, Sparkles } from 'lucide-react';
import Dashboard from './pages/Dashboard.jsx';
import Workflows from './pages/Workflows.jsx';
import WorkflowDetail from './pages/WorkflowDetail.jsx';
import NewWorkflow from './pages/NewWorkflow.jsx';
import Approvals from './pages/Approvals.jsx';
import SettingsPage from './pages/Settings.jsx';
import V3Dashboard from './pages/v3/V3Dashboard.jsx';
import ProjectArena from './pages/v3/ProjectArena.jsx';
import OnboardingGuidance from './components/OnboardingGuidance.jsx';
import api from './api.js';

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [health, setHealth] = useState(null);
  const [hasApiKey, setHasApiKey] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(() => {
    // Check if onboarding has been completed before
    try {
      const completed = localStorage.getItem('tutorOnboardingCompleted');
      return !completed;
    } catch (e) {
      return true; // Show onboarding if we can't check
    }
  });

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
    { path: '/', label: 'v3工作台', icon: Sparkles },
    { path: '/dashboard', label: '仪表盘', icon: BarChart3 },
    { path: '/workflows', label: '工作流', icon: FlaskConical },
    { path: '/approvals', label: '审批', icon: Shield },
    { path: '/new', label: '新建', icon: Plus },
  ];

  const getCurrentPath = () => {
    return location.pathname || '/';
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
            onClick={() => navigate('/settings')}
            style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }}
          >
            去配置
          </button>
        </div>
      )}

      {/* Header */}
      <header className="header">
        <Link to="/" className="logo">
          <div className="logo-icon">
            <Brain size={22} />
          </div>
          <span>TUTOR</span>
        </Link>

        <nav className="nav">
          {navItems.map(item => {
            const Icon = item.icon;
            const isActive = getCurrentPath() === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-link ${isActive ? 'active' : ''}`}
                onClick={() => setSelectedRunId(null)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="header-actions">
          <Link
            to="/settings"
            className="btn btn-ghost btn-icon"
            title="API 配置"
          >
            <SettingsIcon size={20} />
          </Link>
          <div className={`status-badge ${health?.status === 'ok' ? 'online' : 'offline'}`}>
            <span className={`status-dot ${health?.status === 'ok' ? 'online' : 'offline'}`} />
            {health?.status === 'ok' ? '在线' : '离线'}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="main">
        <Routes>
          <Route 
            path="/" 
            element={
              <V3Dashboard 
                onCreateProject={(project) => navigate(`/projects/${project.id}`)}
                onOpenProject={(project) => navigate(`/projects/${project.id}`)}
              />
            } 
          />
          <Route path="/dashboard" element={<Dashboard onViewRun={setSelectedRunId} />} />
          <Route path="/workflows" element={<Workflows onViewRun={setSelectedRunId} />} />
          <Route 
            path="/approvals" 
            element={
              <Approvals onViewRun={(runId) => {
                setSelectedRunId(runId);
                navigate('/workflows');
              }} />
            } 
          />
          <Route 
            path="/new" 
            element={
              <NewWorkflow onCreated={(runId) => {
                setSelectedRunId(runId);
                navigate('/workflows');
              }} />
            } 
          />
          <Route path="/settings" element={<SettingsPage />} />
          <Route 
            path="/projects/:projectId" 
            element={<ProjectArena />} 
          />
        </Routes>
      </main>

      {/* Workflow Detail Modal */}
      {selectedRunId && (
        <WorkflowDetail
          runId={selectedRunId}
          onClose={() => setSelectedRunId(null)}
        />
      )}

      {/* Onboarding Guidance */}
      {showOnboarding && (
        <OnboardingGuidance 
          onComplete={() => {
            setShowOnboarding(false);
            try {
              localStorage.setItem('tutorOnboardingCompleted', 'true');
            } catch (e) {
              console.warn('Could not save onboarding completion status');
            }
          }}
          onNavigate={(page) => {
            const pathMap = {
              'v3-dashboard': '/',
              'dashboard': '/dashboard',
              'workflows': '/workflows',
              'approvals': '/approvals',
              'new': '/new',
              'settings': '/settings'
            };
            navigate(pathMap[page] || '/');
          }}
        />
      )}
    </div>
  );
}

export default App;
