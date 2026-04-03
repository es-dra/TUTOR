import pytest
from unittest.mock import MagicMock, patch
from tutor.core.workflow.experiment import EnvironmentCheckStep, CodeFetchStep, DependencyInstallStep

class MockWorkflowContext:
    def __init__(self, steps_list=None):
        self.steps = steps_list or []
        self.state = {}
        self.config = {"steps": len(self.steps)}
        self.workflow_id = "test_experiment"
        self.workflow_type = "experiment"
        self.results_dir = MagicMock()
        
    def get_state(self, key, default=None):
        return self.state.get(key, default)
        
    def set_state(self, key, value):
        self.state[key] = value
        
    def update_state(self, data):
        self.state.update(data)

    def get_all_state(self):
        return self.state.copy()

@pytest.fixture
def mock_context():
    return MockWorkflowContext()

class TestEnvironmentCheckStep:
    def test_step_initialization(self):
        step = EnvironmentCheckStep()
        assert step.name == "environment_check"
        assert "Check local environment" in step.description

    @patch("subprocess.run")
    @patch("shutil.disk_usage")
    @patch("psutil.virtual_memory")
    def test_execute_success(self, mock_psutil, mock_shutil, mock_run, mock_context):
        mock_run.return_value = MagicMock(returncode=0)
        mock_shutil.return_value = (1000, 500, 100 * 1024**3)
        mock_psutil.return_value = MagicMock(total=16 * 1024**3)
        
        step = EnvironmentCheckStep()
        result = step.execute(mock_context)
        
        assert result["environment_ready"] is True
        assert result["environment_info"]["gpu_available"] is True

class TestCodeFetchStep:
    def test_validate_no_idea(self, mock_context):
        step = CodeFetchStep(MagicMock())
        errors = step.validate(mock_context)
        assert "No selected_idea found" in errors[0]

    def test_execute_local_path(self, mock_context, tmp_path):
        code_dir = tmp_path / "code"
        code_dir.mkdir()
        (code_dir / "main.py").write_text("print('hello')")
        
        mock_context.set_state("selected_idea", {"local_code_path": str(code_dir)})
        
        step = CodeFetchStep(MagicMock())
        result = step.execute(mock_context)
        
        assert result["code_source"] == "local"
        assert result["code_dir"] == str(code_dir)

class TestDependencyInstallStep:
    def test_validate_no_code_dir(self, mock_context):
        step = DependencyInstallStep()
        errors = step.validate(mock_context)
        assert "No code_dir found" in errors[0]

    @patch("subprocess.run")
    def test_execute_requirements(self, mock_run, mock_context, tmp_path):
        code_dir = tmp_path / "code"
        code_dir.mkdir()
        (code_dir / "requirements.txt").write_text("torch\nnumpy\n")
        mock_context.set_state("code_dir", str(code_dir))
        mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
        
        step = DependencyInstallStep()
        result = step.execute(mock_context)
        
        assert result["dependencies_installed"] is True
        assert "torch" in result["installed_packages"]
