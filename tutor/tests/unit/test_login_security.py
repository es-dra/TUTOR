"""Login Security Tests

测试登录安全功能：
- 登录尝试次数限制
- 账户锁定
- 登录失败记录
"""

import pytest
import time
from unittest.mock import patch
import tempfile
import os


class TestLoginRateLimiter:
    """登录频率限制测试"""

    @pytest.fixture
    def rate_limiter(self):
        """创建登录频率限制器"""
        from tutor.core.auth.security import LoginRateLimiter
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        limiter = LoginRateLimiter(db_path=db_path, max_attempts=5, lockout_duration=300)
        yield limiter
        try:
            os.unlink(db_path)
        except:
            pass

    def test_record_failed_attempt(self, rate_limiter):
        """失败登录应该被记录"""
        username = "testuser"

        # 记录失败
        result = rate_limiter.record_failed_attempt(username)

        assert result is True
        assert rate_limiter.get_attempts(username) == 1

    def test_record_multiple_failed_attempts(self, rate_limiter):
        """多次失败登录"""
        username = "testuser"

        for i in range(3):
            rate_limiter.record_failed_attempt(username)

        assert rate_limiter.get_attempts(username) == 3

    def test_successful_login_clears_attempts(self, rate_limiter):
        """成功登录清除失败记录"""
        username = "testuser"

        # 失败3次
        for _ in range(3):
            rate_limiter.record_failed_attempt(username)

        # 成功登录
        rate_limiter.record_successful_login(username)

        assert rate_limiter.get_attempts(username) == 0

    def test_account_locked_after_max_attempts(self, rate_limiter):
        """超过最大尝试次数后账户被锁定"""
        username = "testuser"
        max_attempts = 5

        # 达到最大尝试次数
        for _ in range(max_attempts):
            rate_limiter.record_failed_attempt(username)

        # 再次失败尝试
        result = rate_limiter.record_failed_attempt(username)

        assert result is False  # 不允许
        assert rate_limiter.is_locked(username) is True

    def test_locked_account_rejects_login(self, rate_limiter):
        """锁定账户应拒绝登录"""
        username = "testuser"

        # 达到最大尝试次数
        for _ in range(5):
            rate_limiter.record_failed_attempt(username)

        # 检查是否锁定
        assert rate_limiter.is_locked(username) is True

    def test_get_remaining_attempts(self, rate_limiter):
        """获取剩余尝试次数"""
        username = "testuser"

        rate_limiter.record_failed_attempt(username)
        rate_limiter.record_failed_attempt(username)

        remaining = rate_limiter.get_remaining_attempts(username)
        assert remaining == 3  # 5 - 2 = 3

    def test_different_users_independent(self, rate_limiter):
        """不同用户的失败次数独立"""
        user1 = "user1"
        user2 = "user2"

        rate_limiter.record_failed_attempt(user1)
        rate_limiter.record_failed_attempt(user1)
        rate_limiter.record_failed_attempt(user2)

        assert rate_limiter.get_attempts(user1) == 2
        assert rate_limiter.get_attempts(user2) == 1

    def test_lockout_duration_respected(self, rate_limiter):
        """锁定时长应被遵守"""
        username = "testuser"
        lockout_duration = 300  # 5分钟

        # 锁定账户
        for _ in range(5):
            rate_limiter.record_failed_attempt(username)

        # 检查锁定
        is_locked, remaining = rate_limiter.is_locked_with_remaining(username)

        assert is_locked is True
        assert remaining > 0

    def test_auto_unlock_after_duration(self, rate_limiter):
        """锁定到期后自动解锁"""
        from tutor.core.auth.security import LoginRateLimiter
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        # 创建极短锁定期的限制器（用于测试）
        limiter = LoginRateLimiter(db_path=db_path, max_attempts=3, lockout_duration=1)

        username = "testuser"

        # 锁定账户
        for _ in range(3):
            limiter.record_failed_attempt(username)

        assert limiter.is_locked(username) is True

        # 等待锁定期过期
        time.sleep(2)

        # 应该已解锁
        assert limiter.is_locked(username) is False

        try:
            os.unlink(db_path)
        except:
            pass


class TestPasswordStrengthValidator:
    """密码强度验证测试"""

    def test_valid_password(self):
        """强密码应通过"""
        from tutor.core.auth.security import PasswordStrengthValidator

        validator = PasswordStrengthValidator()

        # 强密码
        assert validator.validate("StrongPass123!") is True

    def test_password_too_short(self):
        """太短的密码应失败"""
        from tutor.core.auth.security import PasswordStrengthValidator

        validator = PasswordStrengthValidator(min_length=8)

        assert validator.validate("Abc1!") is False

    def test_password_no_uppercase(self):
        """没有大写字母的密码应失败"""
        from tutor.core.auth.security import PasswordStrengthValidator

        validator = PasswordStrengthValidator(require_uppercase=True)

        assert validator.validate("lowercase123!") is False

    def test_password_no_lowercase(self):
        """没有小写字母的密码应失败"""
        from tutor.core.auth.security import PasswordStrengthValidator

        validator = PasswordStrengthValidator(require_lowercase=True)

        assert validator.validate("UPPERCASE123!") is False

    def test_password_no_number(self):
        """没有数字的密码应失败"""
        from tutor.core.auth.security import PasswordStrengthValidator

        validator = PasswordStrengthValidator(require_number=True)

        assert validator.validate("NoNumbers!") is False

    def test_password_no_special_char(self):
        """没有特殊字符的密码应失败"""
        from tutor.core.auth.security import PasswordStrengthValidator

        validator = PasswordStrengthValidator(require_special=True)

        assert validator.validate("NoSpecial123") is False

    def test_get_strength_score(self):
        """获取密码强度分数"""
        from tutor.core.auth.security import PasswordStrengthValidator

        validator = PasswordStrengthValidator()

        # 弱密码
        weak_score = validator.get_strength_score("abc")
        assert weak_score < 0.5

        # 强密码
        strong_score = validator.get_strength_score("Str0ng!Pass#word")
        assert strong_score > 0.7

    def test_common_password_rejected(self):
        """常见密码应被拒绝"""
        from tutor.core.auth.security import PasswordStrengthValidator

        validator = PasswordStrengthValidator()

        # 常见密码
        assert validator.validate("password123") is False
        assert validator.validate("12345678") is False
