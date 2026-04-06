import React, { useState } from 'react';
import { Zap, Sparkles, Target, MessageSquare, Check, List } from 'lucide-react';

const OnboardingGuidance = ({ onComplete, onNavigate }) => {
  const [step, setStep] = useState(0);

  const handleNext = () => {
    if (step === 3) {
      onComplete();
      return;
    }
    setStep(prev => prev + 1);
  };

  const handleSkip = () => {
    onComplete();
  };

  const handleGoBack = () => {
    if (step > 0) {
      setStep(prev => prev - 1);
    }
  };

  const steps = [
    {
      title: '欢迎使用 TUTOR',
      description: 'TUTOR 是一个智能研究自动化平台，帮助您从研究想法生成到论文撰写的完整流程。',
      icon: Sparkles,
      features: [
        '🎯 自动生成研究想法',
        '🧪 设计和执行实验',
        '📝 撰写和润色论文',
        '👥 多角色协作工作流'
      ]
    },
    {
      title: '配置 AI 模型',
      description: '为了使用 TUTOR 的功能，您需要配置至少一个 AI 模型提供商。',
      icon: Target,
      features: [
        '🔑 支持 OpenAI, Anthropic, Azure 等主流提供商',
        '⚡ 自动负载均衡和故障转移',
        '💰 成本追踪和使用量监控',
        '🔒 安全存储您的 API 密钥'
      ],
      action: {
        text: '前往配置',
        onClick: () => {
          if (onNavigate) onNavigate('settings');
          onComplete(); // Exit onboarding when going to settings
        }
      }
    },
    {
      title: '创建您的第一个工作流',
      description: '让我们快速了解 TUTOR 的四种工作流类型：',
      icon: Zap,
      workflows: [
        { id: 'idea', name: '想法生成', description: '从论文中提取灵感，生成 novel research ideas', icon: MessageSquare },
        { id: 'experiment', name: '实验执行', description: '自动化实验设计、执行和结果分析', icon: Zap },
        { id: 'review', name: '论文评审', description: '多维度评估论文质量，提供改进建议', icon: List },
        { id: 'write', name: '论文撰写', description: '从大纲到成稿的完整写作流程', icon: Check }
      ]
    },
    {
      title: '开始使用',
      description: '现在您已经了解了 TUTOR 的基本功能，让我们开始您的研究之旅！',
      icon: Check,
      features: [
        '🚀 点击「新建」创建第一个工作流',
        '📊 在「工作流」页面监控运行状态',
        '👀 在「审批」页面查看需要人工干预的任务',
        '📈 在「仪表盘」查看整体使用统计'
      ],
      final: true
    }
  ];

  const currentStep = steps[step];
  const isLastStep = step === steps.length - 1;

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-content">
        <div className="onboarding-header">
          <h2>{currentStep.title}</h2>
          {step > 0 && (
            <button className="onboarding-back" onClick={handleGoBack}>
              上一步
            </button>
          )}
          {!isLastStep && (
            <button className="onboarding-close" onClick={handleSkip}>
              跳过
            </button>
          )}
        </div>
        
        <div className="onboarding-body">
          <div className="onboarding-icon">
            <currentStep.icon size={48} />
          </div>
          
          <p className="onboarding-description">{currentStep.description}</p>
          
          {currentStep.features && (
            <ul className="onboarding-features">
              {currentStep.features.map((feature, index) => (
                <li key={index}>{feature}</li>
              ))}
            </ul>
          )}
          
          {currentStep.workflows && (
            <div className="onboarding-workflows">
              {currentStep.workflows.map(wf => (
                <div key={wf.id} className="onboarding-workflow-card">
                  <div className="onboarding-workflow-icon">
                    <wf.icon size={32} />
                  </div>
                  <div className="onboarding-workflow-info">
                    <h4>{wf.name}</h4>
                    <p>{wf.description}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {currentStep.action && (
            <button className="onboarding-action-btn" onClick={currentStep.action.onClick}>
              {currentStep.action.text}
            </button>
          )}
          
          {isLastStep && (
            <>
              <button className="onboarding-btn-secondary" onClick={handleSkip}>
                直接开始
              </button>
              <button className="onboarding-btn-primary" onClick={handleNext}>
                我准备好了
              </button>
            </>
          )}
          
          {!isLastStep && !currentStep.action && (
            <button className="onboarding-btn-primary" onClick={handleNext}>
              下一步
            </button>
          )}
        </div>
        
        <div className="onboarding-footer">
          <div className="onboarding-progress">
            {steps.map((s, i) => (
              <div 
                key={i} 
                className={`onboarding-dot ${i === step ? 'active' : ''}`}
              />
            ))}
          </div>
          <span>{step + 1} / {steps.length}</span>
        </div>
      </div>
    </div>
  );
};

export default OnboardingGuidance;