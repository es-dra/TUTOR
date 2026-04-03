"""Login Security - Rate Limiting and Password Validation

Features:
- Login attempt rate limiting with account locking
- Password strength validation
- Common password detection
"""

import sqlite3
import time
from typing import Optional, Tuple
import re


class LoginRateLimiter:
    """Login rate limiter with account locking

    Uses SQLite to persist failed attempt tracking across restarts.
    """

    def __init__(self, db_path: str = ":memory:", max_attempts: int = 5, lockout_duration: int = 300):
        """Initialize rate limiter

        Args:
            db_path: Path to SQLite database for persistence
            max_attempts: Maximum failed attempts before lockout
            lockout_duration: Seconds to lock out account after max attempts
        """
        self.db_path = db_path
        self.max_attempts = max_attempts
        self.lockout_duration = lockout_duration
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                username TEXT PRIMARY KEY,
                attempts INTEGER DEFAULT 0,
                locked_until REAL DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def _get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    def record_failed_attempt(self, username: str) -> bool:
        """Record a failed login attempt

        Args:
            username: The username that failed to login

        Returns:
            True if attempt was recorded, False if account is locked
        """
        if self.is_locked(username):
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        # Get current attempts
        cursor.execute(
            "SELECT attempts, locked_until FROM login_attempts WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()

        if row is None:
            attempts = 0
            locked_until = 0.0
        else:
            attempts, locked_until = row

        # Check if newly unlocked
        now = time.time()
        if locked_until > 0 and now >= locked_until:
            attempts = 0
            locked_until = 0.0

        attempts += 1

        if attempts >= self.max_attempts:
            # Lock the account
            locked_until = now + self.lockout_duration
            cursor.execute(
                "INSERT OR REPLACE INTO login_attempts (username, attempts, locked_until) VALUES (?, ?, ?)",
                (username, attempts, locked_until)
            )
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO login_attempts (username, attempts, locked_until) VALUES (?, ?, ?)",
                (username, attempts, locked_until)
            )

        conn.commit()
        conn.close()
        return True

    def record_successful_login(self, username: str) -> None:
        """Clear failed attempts after successful login

        Args:
            username: The username that successfully logged in
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO login_attempts (username, attempts, locked_until) VALUES (?, 0, 0)",
            (username,)
        )
        conn.commit()
        conn.close()

    def get_attempts(self, username: str) -> int:
        """Get number of failed attempts for username

        Args:
            username: The username to check

        Returns:
            Number of failed attempts
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT attempts FROM login_attempts WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return 0
        return row[0]

    def is_locked(self, username: str) -> bool:
        """Check if account is locked

        Args:
            username: The username to check

        Returns:
            True if locked, False otherwise
        """
        is_locked, _ = self.is_locked_with_remaining(username)
        return is_locked

    def is_locked_with_remaining(self, username: str) -> Tuple[bool, int]:
        """Check if account is locked and get remaining time

        Args:
            username: The username to check

        Returns:
            Tuple of (is_locked, remaining_seconds)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT locked_until FROM login_attempts WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        conn.close()

        if row is None or row[0] == 0:
            return False, 0

        now = time.time()
        remaining = row[0] - now

        if remaining <= 0:
            return False, 0

        return True, int(remaining)

    def get_remaining_attempts(self, username: str) -> int:
        """Get remaining login attempts before lockout

        Args:
            username: The username to check

        Returns:
            Number of remaining attempts
        """
        attempts = self.get_attempts(username)
        return max(0, self.max_attempts - attempts)


class PasswordStrengthValidator:
    """Password strength validator

    Validates passwords against configurable requirements.
    """

    # Common passwords that should be rejected
    COMMON_PASSWORDS = {
        "password", "password123", "12345678", "123456789",
        "qwerty", "abc123", "monkey", "1234567",
        "letmein", "welcome", "shadow", "sunshine",
        "princess", "admin", "login", "passw0rd",
    }

    def __init__(
        self,
        min_length: int = 8,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_number: bool = True,
        require_special: bool = True,
    ):
        """Initialize validator

        Args:
            min_length: Minimum password length
            require_uppercase: Require at least one uppercase letter
            require_lowercase: Require at least one lowercase letter
            require_number: Require at least one digit
            require_special: Require at least one special character
        """
        self.min_length = min_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_number = require_number
        self.require_special = require_special

    def validate(self, password: str) -> bool:
        """Validate password meets requirements

        Args:
            password: The password to validate

        Returns:
            True if password meets all requirements
        """
        # Check length
        if len(password) < self.min_length:
            return False

        # Check uppercase
        if self.require_uppercase and not re.search(r"[A-Z]", password):
            return False

        # Check lowercase
        if self.require_lowercase and not re.search(r"[a-z]", password):
            return False

        # Check number
        if self.require_number and not re.search(r"\d", password):
            return False

        # Check special character
        if self.require_special and not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
            return False

        # Check common passwords
        if password.lower() in self.COMMON_PASSWORDS:
            return False

        return True

    def get_strength_score(self, password: str) -> float:
        """Calculate password strength score

        Args:
            password: The password to score

        Returns:
            Score from 0.0 (weak) to 1.0 (strong)
        """
        if not password:
            return 0.0

        score = 0.0

        # Length scoring
        if len(password) >= 8:
            score += 0.2
        if len(password) >= 12:
            score += 0.1
        if len(password) >= 16:
            score += 0.1

        # Character type scoring
        if re.search(r"[a-z]", password):
            score += 0.15
        if re.search(r"[A-Z]", password):
            score += 0.15
        if re.search(r"\d", password):
            score += 0.15
        if re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
            score += 0.15

        # Bonus for mixing types
        type_count = sum([
            bool(re.search(r"[a-z]", password)),
            bool(re.search(r"[A-Z]", password)),
            bool(re.search(r"\d", password)),
            bool(re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password)),
        ])
        if type_count >= 3:
            score += 0.1
        if type_count >= 4:
            score += 0.1

        # Penalty for common passwords
        if password.lower() in self.COMMON_PASSWORDS:
            score = 0.1

        return min(1.0, score)