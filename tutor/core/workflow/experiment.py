"""ExperimentFlow - 自动化实验工作流

根据选定的idea，自动复现相关代码、配置实验环境、执行实验并生成结果报告。

MVP限制：
- 仅支持本地实验执行
- 不支持远程SSH部署
- 依赖安装失败时需用户手动介入
- 可视化图表仅支持Matplotlib基础图表
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from tutor.core.workflow import Workflow, WorkflowStep
from tutor.core.workflow.project_gate import ProjectGateStep
from tutor.core.model import ModelGateway
from tutor.core.storage import StorageManager

logger = logging.getLogger(__name__)


class EnvironmentCheckStep(WorkflowStep):
    """环境检测步骤
    
    检查本地Python环境、GPU可用性、磁盘空间等。
    
    输出状态：
    - environment_info: Dict - 环境信息
    - environment_ready: bool - 环境是否就绪
    """
    
    def __init__(self):
        super().__init__(
            name="environment_check",
            description="Check local environment (Python, GPU, disk space)"
        )
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行环境检测"""
        logger.info("Checking environment...")
        
        info = {
            "python_version": sys.version,
            "platform": sys.platform,
            "gpu_available": self._check_gpu(),
            "disk_space_gb": self._check_disk_space(),
            "memory_gb": self._check_memory(),
        }
        
        # 判断环境是否就绪（简化版）
        ready = info["gpu_available"] and info["disk_space_gb"] > 10
        
        result = {
            "environment_info": info,
            "environment_ready": ready,
            "issues": []
        }
        
        if not ready:
            if not info["gpu_available"]:
                result["issues"].append("No GPU available")
            if info["disk_space_gb"] <= 10:
                result["issues"].append(f"Insufficient disk space: {info['disk_space_gb']:.1f}GB")
        
        logger.info(f"Environment check complete: ready={ready}, issues={result['issues']}")
        
        return result
    
    def _check_gpu(self) -> bool:
        """检查GPU是否可用（简化：仅检查nvidia-smi是否存在）"""
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, check=True, timeout=5)
            logger.info("GPU detected (nvidia-smi available)")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("No GPU detected (nvidia-smi not available)")
            return False
    
    def _check_disk_space(self) -> float:
        """检查磁盘空间（GB）"""
        import shutil
        total, used, free = shutil.disk_usage("/")
        return free / (1024**3)
    
    def _check_memory(self) -> float:
        """检查内存（GB）"""
        import psutil
        return psutil.virtual_memory().total / (1024**3)
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证"""
        return []


class CodeFetchStep(WorkflowStep):
    """代码获取步骤
    
    根据idea关联的GitHub仓库或arXiv代码链接获取代码。
    如果idea中没有代码链接，则提示用户提供。
    
    输出状态：
    - code_source: str - 代码来源（local/git/arxiv）
    - code_dir: Path - 代码存放目录
    - code_metadata: Dict - 代码元信息
    """
    
    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="code_fetch",
            description="Fetch experiment code from GitHub, ArXiv, or local path"
        )
        self.model_gateway = model_gateway
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行代码获取"""
        idea_data = context.get_state("selected_idea", {})
        
        # 检查是否有代码链接
        code_url = idea_data.get("code_url")
        repo_url = idea_data.get("repo_url")
        local_path = idea_data.get("local_code_path")
        
        if local_path:
            source = "local"
            code_dir = Path(local_path)
            if not code_dir.exists():
                raise ValueError(f"Local code path does not exist: {local_path}")
            
        elif repo_url or code_url:
            # 这里简化：实际需要git clone或下载解压
            source = "git" if repo_url else "arxiv"
            logger.info(f"Fetching code from {repo_url or code_url}")
            code_dir = self._fetch_remote_code(repo_url or code_url)
            
        else:
            # 没有代码链接，需要用户提供
            logger.warning("No code source found in idea. Asking user for input.")
            # MVP: 抛出异常，要求用户提供
            raise ValueError(
                "Idea does not specify code source. "
                "Please provide a local path or repository URL."
            )
        
        result = {
            "code_source": source,
            "code_dir": str(code_dir),
            "code_metadata": {
                "files": [f.name for f in code_dir.rglob("*") if f.is_file()][:20],
                "total_size_mb": sum(f.stat().st_size for f in code_dir.rglob("*") if f.is_file()) / (1024**2)
            }
        }
        
        logger.info(f"Code fetch complete: source={source}, dir={code_dir}")
        
        return result
    
    def _fetch_remote_code(self, url: str) -> Path:
        """从远程获取代码（简化实现）
        
        MVP仅支持本地路径，真实实现需要：
        - git clone (如果GitHub URL)
        - 下载并解压 (如果arXiv suppack)
        """
        raise NotImplementedError(
            "Remote code fetching not implemented in MVP. "
            "Please provide local code path."
        )
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证前置条件"""
        errors = []
        if "selected_idea" not in context.get_all_state():
            errors.append("No selected_idea found. Please select an idea first.")
        return errors


class DependencyInstallStep(WorkflowStep):
    """依赖安装步骤
    
    读取requirements.txt或setup.py，安装依赖。
    
    输出状态：
    - dependencies_installed: bool - 是否成功安装
    - installed_packages: List[str] - 已安装的包列表
    - install_log: str - 安装日志
    """
    
    def __init__(self):
        super().__init__(
            name="dependency_install",
            description="Install Python dependencies from requirements.txt or setup.py"
        )
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行依赖安装"""
        code_dir = Path(context.get_state("code_dir", ""))
        if not code_dir.exists():
            raise ValueError(f"Code directory not found: {code_dir}")
        
        # 查找requirements.txt
        req_file = code_dir / "requirements.txt"
        setup_file = code_dir / "setup.py"
        pyproject_file = code_dir / "pyproject.toml"
        
        install_log = []
        installed_packages = []
        
        if req_file.exists():
            logger.info(f"Installing from {req_file}")
            success, log = self._pip_install(req_file)
            install_log.append(log)
            if success:
                # 解析已安装包（简化）
                installed_packages = self._parse_requirements(req_file)
            else:
                raise RuntimeError(f"Dependency installation failed:\n{log}")
                
        elif pyproject_file.exists():
            logger.info(f"Installing from {pyproject_file}")
            # 使用pip install -e .安装
            success, log = self._pip_install([str(pyproject_file)])
            install_log.append(log)
            if not success:
                raise RuntimeError(f"Dependency installation failed:\n{log}")
            installed_packages = ["(from pyproject.toml)"]
            
        elif setup_file.exists():
            logger.info(f"Installing from {setup_file}")
            success, log = self._pip_install([str(setup_file)])
            install_log.append(log)
            if not success:
                raise RuntimeError(f"Dependency installation failed:\n{log}")
            installed_packages = ["(from setup.py)"]
            
        else:
            logger.warning("No requirements file found. Skipping dependency installation.")
            install_log.append("No requirements.txt/setup.py/pyproject.toml found.")
        
        result = {
            "dependencies_installed": True,
            "installed_packages": installed_packages,
            "install_log": "\n".join(install_log)
        }
        
        logger.info(f"Dependency install complete: {len(installed_packages)} packages")
        
        return result
    
    def _pip_install(self, requirements_file: Path) -> tuple[bool, str]:
        """执行pip安装
        
        Returns:
            (success, log_output)
        """
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            success = result.returncode == 0
            log = f"Command: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            return success, log
        except subprocess.TimeoutExpired:
            return False, "Installation timed out after 5 minutes"
        except Exception as e:
            return False, f"Installation error: {e}"
    
    def _parse_requirements(self, req_file: Path) -> List[str]:
        """解析requirements.txt获取包列表"""
        packages = []
        with open(req_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # 简单提取包名（忽略版本）
                    pkg = line.split('==')[0].split('>=')[0].split('<=')[0].strip()
                    if pkg:
                        packages.append(pkg)
        return packages
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证前置条件"""
        errors = []
        code_dir = context.get_state("code_dir")
        if not code_dir:
            errors.append("No code_dir found. Run code_fetch first.")
        return errors


class ExperimentExecutionStep(WorkflowStep):
    """实验执行步骤
    
    运行训练/测试脚本，记录日志和指标。
    
    输出状态：
    - experiment_status: str - 执行状态（running/completed/failed）
    - logs: List[str] - 日志行列表
    - metrics: Dict - 最终指标
    - artifacts: List[Path] - 生成的文件列表
    """
    
    def __init__(self, timeout_minutes: int = 30):
        super().__init__(
            name="experiment_execution",
            description="Run training/testing script and collect logs/metrics"
        )
        self.timeout_seconds = timeout_minutes * 60
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行实验"""
        code_dir = Path(context.get_state("code_dir", ""))
        config = context.config
        
        # 确定要运行的脚本
        # MVP约定：优先运行main.py, 其次train.py, 再实验其他
        script_candidates = ["main.py", "train.py", "run.py", "experiment.py"]
        script_path = None
        for candidate in script_candidates:
            candidate_path = code_dir / candidate
            if candidate_path.exists():
                script_path = candidate_path
                break
        
        if not script_path:
            raise ValueError(
                "No training script found. Please provide one of: " +
                ", ".join(script_candidates)
            )
        
        logger.info(f"Running experiment script: {script_path}")
        
        # 准备命令（可以从config传递参数）
        cmd = [sys.executable, str(script_path)]
        
        # 添加超时
        try:
            process = subprocess.Popen(
                cmd,
                cwd=code_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            logs = []
            metrics = {}
            
            # 实时读取输出
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    line = output.strip()
                    logs.append(line)
                    logger.debug(f"[Experiment] {line}")
                    
                    # 尝试提取指标（简化：查找 "metric: value" 格式）
                    metrics.update(self._extract_metrics(line))
            
            # 等待完成
            returncode = process.poll(timeout=self.timeout_seconds)
            
            if returncode != 0:
                raise RuntimeError(
                    f"Experiment script failed with exit code {returncode}\n"
                    f"Last 10 logs:\n" + "\n".join(logs[-10:])
                )
            
            # 收集生成的文件（artifact）
            artifacts = self._collect_artifacts(code_dir)
            
            result = {
                "experiment_status": "completed",
                "return_code": returncode,
                "logs": logs[-100:],  # 保留最后100行
                "metrics": metrics,
                "artifacts": [str(a.relative_to(code_dir)) for a in artifacts],
                "log_file": str((code_dir / "experiment.log").relative_to(code_dir))
            }
            
            # 保存完整日志到文件
            log_file = code_dir / "experiment.log"
            with open(log_file, 'w') as f:
                f.write("\n".join(logs))
            
            logger.info(f"Experiment completed. Metrics: {metrics}")
            
            return result
            
        except subprocess.TimeoutExpired:
            process.kill()
            raise RuntimeError(f"Experiment timed out after {self.timeout_seconds} seconds")
    
    def _extract_metrics(self, line: str) -> Dict[str, float]:
        """从日志行提取指标
        
        支持格式：
        - "accuracy: 0.95"
        - "loss = 0.123"
        - "val_loss: 1.234"
        """
        import re
        metrics = {}
        
        patterns = [
            r'([a-zA-Z_]+)\s*[:=]\s*([\d.]+(?:[eE][+-]?\d+)?)',  # accuracy: 0.95
            r'([a-zA-Z_]+)\s*\|\s*([\d.]+(?:[eE][+-]?\d+)?)',    # accuracy | 0.95
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, line)
            for key, value in matches:
                key = key.lower().strip()
                try:
                    metrics[key] = float(value)
                except ValueError:
                    pass
        
        return metrics
    
    def _collect_artifacts(self, code_dir: Path) -> List[Path]:
        """收集实验生成的文件"""
        artifacts = []
        
        # 常见输出目录
        output_dirs = [
            code_dir / "outputs",
            code_dir / "results",
            code_dir / "logs",
            code_dir / "checkpoints",
            code_dir / "figures",
        ]
        
        for out_dir in output_dirs:
            if out_dir.exists() and out_dir.is_dir():
                for file in out_dir.rglob("*"):
                    if file.is_file() and file.stat().st_size > 0:
                        artifacts.append(file)
        
        # 根目录下常见的文件
        for ext in [".png", ".jpg", ".pdf", ".csv", ".json", ".txt"]:
            for file in code_dir.glob(f"*{ext}"):
                if file.is_file():
                    artifacts.append(file)
        
        return artifacts
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证前置条件"""
        errors = []
        if not context.get_state("code_dir"):
            errors.append("No code_dir found. Run code_fetch first.")
        env_ready = context.get_state("environment_ready", False)
        if not env_ready:
            errors.append("Environment not ready. Check environment_check.")
        return errors


class ResultsAnalysisStep(WorkflowStep):
    """结果分析步骤
    
    分析实验日志和指标，生成可视化图表（Matplotlib）。
    
    输出状态：
    - analysis_report: str - 分析报告文本
    - charts: List[str] - 生成的图表文件名
    """
    
    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="results_analysis",
            description="Analyze experiment logs and metrics, generate visualizations"
        )
        self.model_gateway = model_gateway
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行结果分析"""
        logs = context.get_state("logs", [])
        metrics = context.get_state("metrics", {})
        code_dir = Path(context.get_state("code_dir", ""))
        
        logger.info("Analyzing experiment results...")
        
        # 1. 使用模型生成分析报告
        analysis_report = self._generate_analysis_report(logs, metrics)
        
        # 2. 生成可视化图表（如果指标足够）
        charts = []
        if metrics:
            chart_file = self._generate_chart(metrics, code_dir)
            if chart_file:
                charts.append(chart_file)
        
        result = {
            "analysis_report": analysis_report,
            "charts": charts,
            "summary": {
                "total_metrics": len(metrics),
                "log_lines_analyzed": len(logs),
                "charts_generated": len(charts)
            }
        }
        
        logger.info(f"Results analysis complete: {len(charts)} charts generated")
        
        return result
    
    def _generate_analysis_report(self, logs: List[str], metrics: Dict[str, float]) -> str:
        """使用模型生成分析报告"""
        # 提取日志摘要（最后50行）
        log_summary = "\n".join(logs[-50:])
        
        metrics_str = "\n".join([f"{k}: {v}" for k, v in metrics.items()])
        
        prompt = f"""
Analyze the following experiment logs and metrics, and provide a structured analysis.

**Final Metrics:**
{metrics_str if metrics else "No metrics found."}

**Recent Log Snippet:**
```log
{log_summary}
```

Please provide an analysis covering:
1. **Experiment Summary**: What was the goal and outcome?
2. **Key Metrics**: Interpretation of the final metrics.
3. **Observations**: Any notable patterns or anomalies in the logs.
4. **Issues**: Any errors, warnings, or unexpected behaviors.
5. **Recommendations**: Suggestions for improvement in next run.

Be concise but thorough.
"""
        
        try:
            response = self.model_gateway.chat(
                "analyzer",
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate analysis report: {e}")
            return f"Analysis failed: {e}"
    
    def _generate_chart(self, metrics: Dict[str, float], output_dir: Path) -> Optional[str]:
        """生成Matplotlib图表"""
        try:
            import matplotlib
            matplotlib.use('Agg')  # 非交互式后端
            import matplotlib.pyplot as plt
            
            # 简单条形图显示所有指标
            if not metrics:
                return None
            
            fig, ax = plt.subplots(figsize=(8, 4))
            keys = list(metrics.keys())[:10]  # 最多显示10个指标
            values = [metrics[k] for k in keys]
            
            bars = ax.bar(range(len(keys)), values)
            ax.set_xticks(range(len(keys)))
            ax.set_xticklabels(keys, rotation=45, ha='right')
            ax.set_ylabel('Value')
            ax.set_title('Experiment Metrics')
            
            # 添加数值标签
            for bar, val in zip(bars, values):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'{val:.3f}', ha='center', va='bottom')
            
            plt.tight_layout()
            
            chart_file = output_dir / "metrics_chart.png"
            plt.savefig(chart_file, dpi=150)
            plt.close()
            
            logger.info(f"Chart saved: {chart_file}")
            return str(chart_file.name)
            
        except ImportError:
            logger.warning("Matplotlib not installed. Skipping chart generation.")
            return None
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            return None
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证前置条件"""
        errors = []
        if not context.get_state("logs"):
            errors.append("No logs found. Run experiment_execution first.")
        return errors


class ComparisonEvaluationStep(WorkflowStep):
    """对比评估步骤
    
    与baseline方法对比，生成评估报告。
    
    输出状态：
    - comparison_report: str - 对比评估报告
    - improvement_metrics: Dict - 改进指标
    """
    
    def __init__(self, model_gateway: ModelGateway):
        super().__init__(
            name="comparison_evaluation",
            description="Compare results with baseline methods and generate evaluation report"
        )
        self.model_gateway = model_gateway
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """执行对比评估"""
        metrics = context.get_state("metrics", {})
        analysis_report = context.get_state("analysis_report", "")
        idea_data = context.get_state("selected_idea", {})
        
        logger.info("Generating comparison evaluation...")
        
        # 提取idea中提到的baseline方法
        baselines = idea_data.get("baselines", ["existing methods"])
        
        # 构建对比分析提示
        prompt = f"""
Based on the experiment results, compare with baseline methods and evaluate the proposed approach.

**Selected Idea:**
{idea_data.get('title', 'Untitled')}
{idea_data.get('description', 'No description')}

**Experiment Metrics:**
{chr(10).join([f'- {k}: {v:.4f}' for k, v in metrics.items()])}

**Analysis Report:**
{analysis_report}

**Baseline Methods to Compare:**
{chr(10).join([f'- {b}' for b in baselines])}

Please provide:
1. **Comparison Summary**: How does the proposed method perform relative to baselines?
2. **Key Improvements**: Which metrics show improvement and by how much?
3. **Trade-offs**: Any areas where performance is lower or cost higher?
4. **Overall Assessment**: Is the proposed method an improvement? Why or why not?
5. **Recommendations**: Should the approach be further refined or is it publishable?

Be objective and evidence-based.
"""
        
        try:
            response = self.model_gateway.chat(
                "evaluator",
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000
            )
            
            comparison_report = response.strip()
            
            # 尝试提取改进指标（简化）
            improvement_metrics = self._extract_improvements(metrics, baselines)
            
            result = {
                "comparison_report": comparison_report,
                "improvement_metrics": improvement_metrics,
                "baselines_compared": baselines
            }
            
            logger.info("Comparison evaluation complete")
            
            return result
            
        except Exception as e:
            logger.error(f"Comparison evaluation failed: {e}")
            return {
                "comparison_report": f"Evaluation failed: {e}",
                "improvement_metrics": {},
                "baselines_compared": baselines
            }
    
    def _extract_improvements(self, metrics: Dict[str, float], baselines: List[str]) -> Dict[str, Any]:
        """提取改进指标（MVP简化：仅记录数值）"""
        # 实际应用需要基线数值对比，这里仅返回当前指标
        return {
            "current_metrics": metrics,
            "note": "Baseline comparison requires baseline metric values (not implemented in MVP)"
        }
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证前置条件"""
        errors = []
        if not context.get_state("metrics"):
            errors.append("No metrics found. Run experiment_execution first.")
        return errors


class ExperimentReportStep(WorkflowStep):
    """实验报告步骤
    
    整合所有信息，生成完整实验报告。
    
    输出：
    - final_report: str - Markdown格式的实验报告
    - report_metadata: Dict - 报告元数据
    - output_files: List[str] - 生成的文件列表
    """
    
    def __init__(self):
        super().__init__(
            name="final_report",
            description="Generate final experiment report in Markdown"
        )
    
    def execute(self, context: 'WorkflowContext') -> Dict[str, Any]:
        """生成最终报告"""
        idea = context.get_state("selected_idea", {})
        env_info = context.get_state("environment_info", {})
        code_meta = context.get_state("code_metadata", {})
        analysis = context.get_state("analysis_report", "")
        comparison = context.get_state("comparison_report", "")
        metrics = context.get_state("metrics", {})
        artifacts = context.get_state("artifacts", [])
        charts = context.get_state("charts", [])
        
        logger.info("Generating final experiment report...")
        
        # 构建报告内容
        report = f"""# Experiment Report

## 1. Experiment Overview

**Idea Title:** {idea.get('title', 'Untitled')}
**Idea Description:** {idea.get('description', 'No description')}
**Workflow ID:** {context.workflow_id}
**Workflow ID:** {context.workflow_id}

## 2. Environment Information

- **Python Version:** {env_info.get('python_version', 'Unknown')}
- **Platform:** {env_info.get('platform', 'Unknown')}
- **GPU Available:** {env_info.get('gpu_available', False)}
- **Disk Space:** {env_info.get('disk_space_gb', 0):.1f} GB
- **Memory:** {env_info.get('memory_gb', 0):.1f} GB

## 3. Code and Dependencies

**Code Source:** {context.get_state('code_source', 'Unknown')}
**Code Directory:** {context.get_state('code_dir', 'Unknown')}
**Files in Repository:** {len(code_meta.get('files', []))} files

**Installed Packages:**
{chr(10).join([f'- {pkg}' for pkg in context.get_state('installed_packages', [])[:10]])}
{'(...and more)' if len(context.get_state('installed_packages', [])) > 10 else ''}

## 4. Experiment Execution

**Status:** Completed
**Logs:** See `experiment.log` (last 100 lines preserved)
**Artifacts Generated:** {len(artifacts)} files

**Key Metrics:**
{self._format_metrics_table(metrics)}

## 5. Results Analysis

{analysis}

## 6. Comparison with Baselines

{comparison}

## 7. Artifacts and Outputs

**Generated Files:**
{chr(10).join([f'- `{artifact}`' for artifact in artifacts])}

**Charts:**
{chr(10).join([f'- `{chart}`' for chart in charts]) if charts else '- No charts generated'}

---

*Generated by TutorClaw ExperimentFlow*  
*Workflow ID: {context.workflow_id}*
"""
        
        # 保存报告文件
        output_dir = context.results_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = output_dir / "experiment_report.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # 同时保存JSON元数据
        import json
        metadata = {
            "workflow_id": context.workflow_id,
            "created_at": context.workflow_id,
            "idea_title": idea.get("title"),
            "metrics": metrics,
            "artifacts": artifacts,
            "charts": charts
        }
        meta_file = output_dir / "report_metadata.json"
        with open(meta_file, 'w') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Experiment report saved: {report_file}")
        
        result = {
            "final_report": report,
            "report_metadata": metadata,
            "output_files": [str(report_file), str(meta_file)] + artifacts
        }
        
        return result
    
    def _format_metrics_table(self, metrics: Dict[str, float]) -> str:
        """格式化指标表格"""
        if not metrics:
            return "- No metrics recorded"
        
        lines = ["| Metric | Value |", "|--------|-------|"]
        for key, value in metrics.items():
            lines.append(f"| {key} | {value:.4f} |")
        
        return "\n".join(lines)
    
    def validate(self, context: 'WorkflowContext') -> List[str]:
        """验证前置条件"""
        errors = []
        required_states = [
            "selected_idea", "environment_info", "code_dir",
            "analysis_report", "comparison_report", "metrics"
        ]
        for state in required_states:
            if not context.get_state(state):
                errors.append(f"Missing state: {state}")
        return errors


class ExperimentFlow(Workflow):
    """ExperimentFlow - 自动化实验工作流

    完整的工作流：环境检测 → 代码获取 → 依赖安装 → 实验执行 → 分析 → 对比 → 报告

    支持两种执行模式:
    1. 本地执行 (默认): 所有步骤在本地机器执行
    2. 远程执行: 代码部署到远程 GPU 服务器执行

    配置示例:
    ```yaml
    workflow:
      experiment:
        timeout_minutes: 30
        script: "train.py"  # 可选，默认自动检测
        requirements: "requirements.txt"

    # 远程执行配置 (可选)
    remote:
      enabled: true
      host: "gpu-server.example.com"
      port: 22
      username: "researcher"
      key_file: "~/.ssh/id_rsa"  # 或 password: "xxx"
      remote_workspace: "/tmp/tutor-experiments"
      conda_env: "ml"  # 可选
      gpu_required: true
      gpu_device: "0"
    ```
    """

    def build_steps(self) -> List[WorkflowStep]:
        """构建工作流步骤"""
        remote_config = self.config.get("remote")

        if remote_config and remote_config.get("enabled"):
            # 远程执行模式
            return self._build_remote_steps(remote_config)
        else:
            # 本地执行模式
            return self._build_local_steps()

    def _build_local_steps(self) -> List[WorkflowStep]:
        """构建本地执行步骤"""
        project_id = self.config.get("project_id", "unknown")
        steps = [
            EnvironmentCheckStep(),
            CodeFetchStep(self.model_gateway),
            DependencyInstallStep(),
            ExperimentExecutionStep(
                timeout_minutes=self.config.get("timeout_minutes", 30)
            ),
            ResultsAnalysisStep(self.model_gateway),
            ComparisonEvaluationStep(self.model_gateway),
            ExperimentReportStep(),
            # 审批门控 - 暂停等待用户审批实验结果
            ProjectGateStep(
                project_id=project_id,
                phase="experiment",
                title="审批实验结果",
                description="请审批实验结果，批准后将启动评审流程"
            ),
        ]
        return steps

    def _build_remote_steps(self, remote_config: Dict[str, Any]) -> List[WorkflowStep]:
        """构建远程执行步骤"""
        from tutor.core.deployment import RemoteConfig

        # 构建远程配置
        config = RemoteConfig(
            host=remote_config["host"],
            port=remote_config.get("port", 22),
            username=remote_config["username"],
            password=remote_config.get("password"),
            key_file=remote_config.get("key_file"),
            remote_workspace=remote_config.get("remote_workspace", "/tmp/tutor-experiments"),
            python_path=remote_config.get("python_path", "python"),
            conda_env=remote_config.get("conda_env"),
            gpu_required=remote_config.get("gpu_required", True),
            gpu_device=remote_config.get("gpu_device", "0"),
            experiment_timeout_minutes=self.config.get("timeout_minutes", 30),
        )

        steps = [
            RemoteEnvironmentCheckStep(config),
            CodeFetchStep(self.model_gateway),
            RemoteCodeDeployStep(config),
            RemoteExperimentExecutionStep(config),
            ResultFetchStep(),
            ResultsAnalysisStep(self.model_gateway),
            ComparisonEvaluationStep(self.model_gateway),
            ExperimentReportStep(),
        ]
        return steps


# ==================== 远程执行步骤 ====================


class RemoteEnvironmentCheckStep(WorkflowStep):
    """远程环境检测步骤

    检查远程 GPU 服务器的环境配置。

    输出状态:
    - environment_info: Dict - 环境信息
    - environment_ready: bool - 环境是否就绪
    """

    def __init__(self, remote_config):
        super().__init__(
            name="remote_environment_check",
            description="Check remote server environment (GPU, disk, Python)"
        )
        self.remote_config = remote_config

    def execute(self, context: "WorkflowContext") -> Dict[str, Any]:
        """执行远程环境检测"""
        from tutor.core.deployment import RemoteExecutor

        logger.info(f"Checking remote environment: {self.remote_config.host}")

        try:
            with RemoteExecutor(self.remote_config) as executor:
                env_info = executor.check_environment()

                result = {
                    "environment_info": env_info,
                    "environment_ready": True,
                    "remote_host": self.remote_config.host,
                    "gpu_available": env_info.get("gpu_available", False),
                    "issues": [],
                }

                logger.info(f"Remote environment check passed: {env_info}")

        except Exception as e:
            logger.error(f"Remote environment check failed: {e}")
            result = {
                "environment_info": {},
                "environment_ready": False,
                "remote_host": self.remote_config.host,
                "gpu_available": False,
                "issues": [str(e)],
            }

        return result

    def validate(self, context: "WorkflowContext") -> List[str]:
        return []


class RemoteCodeDeployStep(WorkflowStep):
    """远程代码部署步骤

    将本地代码部署到远程服务器。

    输出状态:
    - code_deployed: bool - 是否部署成功
    - remote_workspace: str - 远程工作空间路径
    """

    def __init__(self, remote_config):
        super().__init__(
            name="remote_code_deploy",
            description="Deploy code to remote server"
        )
        self.remote_config = remote_config

    def execute(self, context: "WorkflowContext") -> Dict[str, Any]:
        """执行代码部署"""
        from tutor.core.deployment import RemoteExecutor

        code_dir = Path(context.get_state("code_dir", ""))
        if not code_dir.exists():
            raise ValueError(f"Code directory not found: {code_dir}")

        idea_data = context.get_state("selected_idea", {})
        experiment_id = idea_data.get("id", "default")

        logger.info(f"Deploying code to remote server: {self.remote_config.host}")

        try:
            with RemoteExecutor(self.remote_config) as executor:
                # 创建工作空间
                workspace = executor.create_workspace(experiment_id)

                # 部署代码
                executor.deploy_code(str(code_dir), workspace)

                # 安装依赖
                dep_result = executor.install_dependencies(workspace)

                result = {
                    "code_deployed": True,
                    "remote_workspace": workspace,
                    "dependencies_installed": dep_result.get("installed", False),
                    "remote_host": self.remote_config.host,
                }

                logger.info(f"Code deployed to {workspace}")

        except Exception as e:
            logger.error(f"Code deployment failed: {e}")
            raise

        return result

    def validate(self, context: "WorkflowContext") -> List[str]:
        errors = []
        if "selected_idea" not in context.get_all_state():
            errors.append("No selected_idea found. Please select an idea first.")
        return errors


class RemoteExperimentExecutionStep(WorkflowStep):
    """远程实验执行步骤

    在远程 GPU 服务器上运行实验。

    输出状态:
    - experiment_status: str - 执行状态
    - logs: List[str] - 日志行列表
    - metrics: Dict - 最终指标
    - artifacts: List[str] - 生成的文件列表
    """

    def __init__(self, remote_config, timeout_minutes: int = 30):
        super().__init__(
            name="remote_experiment_execution",
            description=f"Run experiment on remote server ({remote_config.host})"
        )
        self.remote_config = remote_config
        self.timeout_minutes = timeout_minutes

    def execute(self, context: "WorkflowContext") -> Dict[str, Any]:
        """执行远程实验"""
        from tutor.core.deployment import RemoteExecutor

        workspace = context.get_state("remote_workspace")
        if not workspace:
            raise ValueError("No remote_workspace found. Run remote_code_deploy first.")

        code_dir = Path(context.get_state("code_dir", ""))
        config = context.config

        # 确定要运行的脚本
        script_candidates = ["main.py", "train.py", "run.py", "experiment.py"]
        script_path = None
        for candidate in script_candidates:
            candidate_path = code_dir / candidate
            if candidate_path.exists():
                script_path = candidate_path
                break

        if not script_path:
            raise ValueError(
                "No training script found. Please provide one of: " +
                ", ".join(script_candidates)
            )

        experiment_command = f"python {script_path.name}"

        logger.info(f"Running experiment on remote server: {experiment_command}")

        # 收集日志的回调
        logs = []

        def log_callback(line: str):
            logs.append(line.strip())
            # 尝试提取指标
            logger.debug(f"[Remote] {line.strip()}")

        try:
            with RemoteExecutor(self.remote_config) as executor:
                exp_result = executor.run_experiment(
                    workspace,
                    experiment_command,
                    log_callback=log_callback,
                    timeout_minutes=self.timeout_minutes,
                )

                # 拉取结果文件列表
                # 注意: 实际拉取在 ResultFetchStep 完成

                result = {
                    "experiment_status": "completed" if exp_result.success else "failed",
                    "return_code": exp_result.exit_code,
                    "logs": logs[-100:],
                    "metrics": exp_result.metrics,
                    "remote_host": self.remote_config.host,
                    "workspace": workspace,
                }

                logger.info(f"Remote experiment completed: {exp_result.success}")

        except Exception as e:
            logger.error(f"Remote experiment failed: {e}")
            raise

        return result

    def validate(self, context: "WorkflowContext") -> List[str]:
        errors = []
        if not context.get_state("remote_workspace"):
            errors.append("No remote_workspace found. Run remote_code_deploy first.")
        env_ready = context.get_state("environment_ready", False)
        if not env_ready:
            errors.append("Environment not ready. Check remote_environment_check.")
        return errors


class ResultFetchStep(WorkflowStep):
    """结果拉取步骤

    从远程服务器拉取实验结果到本地。

    输出状态:
    - fetched_artifacts: List[str] - 拉取的文件列表
    - local_results_dir: str - 本地结果目录
    """

    def __init__(self):
        super().__init__(
            name="result_fetch",
            description="Fetch experiment results from remote server"
        )

    def execute(self, context: "WorkflowContext") -> Dict[str, Any]:
        """执行结果拉取"""
        from tutor.core.deployment import RemoteExecutor

        remote_workspace = context.get_state("remote_workspace")
        if not remote_workspace:
            # 没有远程工作空间，可能是本地执行
            return {
                "fetched_artifacts": [],
                "local_results_dir": str(context.results_dir / "artifacts"),
                "note": "No remote workspace, skipping fetch",
            }

        # 获取远程配置
        # 这里通过 context.config 获取，因为原始 config 在 context 中
        remote_config_data = context.config.get("remote", {})

        if not remote_config_data:
            return {
                "fetched_artifacts": [],
                "local_results_dir": str(context.results_dir / "artifacts"),
                "note": "No remote config, skipping fetch",
            }

        from tutor.core.deployment import RemoteConfig

        remote_config = RemoteConfig(
            host=remote_config_data["host"],
            port=remote_config_data.get("port", 22),
            username=remote_config_data["username"],
            password=remote_config_data.get("password"),
            key_file=remote_config_data.get("key_file"),
        )

        local_results_dir = context.results_dir / "artifacts"
        local_results_dir.mkdir(parents=True, exist_ok=True)

        try:
            with RemoteExecutor(remote_config) as executor:
                fetched = executor.fetch_results(
                    remote_workspace,
                    str(local_results_dir),
                )

                result = {
                    "fetched_artifacts": fetched,
                    "local_results_dir": str(local_results_dir),
                    "total_files": len(fetched),
                }

                logger.info(f"Fetched {len(fetched)} result files")

        except Exception as e:
            logger.error(f"Result fetch failed: {e}")
            result = {
                "fetched_artifacts": [],
                "local_results_dir": str(local_results_dir),
                "error": str(e),
            }

        return result

    def validate(self, context: "WorkflowContext") -> List[str]:
        return []


__all__ = [
    # Base classes
    'ExperimentFlow',
    # Local execution steps
    'EnvironmentCheckStep',
    'CodeFetchStep',
    'DependencyInstallStep',
    'ExperimentExecutionStep',
    'ResultsAnalysisStep',
    'ComparisonEvaluationStep',
    'ExperimentReportStep',
    # Remote execution steps
    'RemoteEnvironmentCheckStep',
    'RemoteCodeDeployStep',
    'RemoteExperimentExecutionStep',
    'ResultFetchStep',
]
