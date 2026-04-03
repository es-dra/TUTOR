"""Secure Config - API Key 安全存储

使用 Fernet 对称加密存储敏感配置（API Keys）。
主密钥通过环境变量 TUTOR_MASTER_KEY 提供。
"""

import os
import base64
import logging
import yaml
from typing import Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class InvalidKeyError(Exception):
    """无效的加密 Key"""
    pass


class SecureConfigError(Exception):
    """安全配置错误"""
    pass


def _get_cryptography() -> "type[Fernet]":
    """延迟导入 cryptography"""
    try:
        from cryptography.fernet import Fernet
        return Fernet
    except ImportError:
        raise ImportError(
            "cryptography is required for secure config. "
            "Install with: pip install cryptography"
        )


def _generate_key() -> str:
    """生成随机密钥（Base64 编码）"""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def encrypt_api_key(api_key: str, master_key: Optional[str] = None) -> str:
    """加密 API Key

    Args:
        api_key: 明文 API Key
        master_key: 主密钥（Base64 编码），如果为 None 则从环境变量读取

    Returns:
        加密后的字符串，格式：ENCRYPTED:<base64-encoded-encrypted-data>
    """
    Fernet = _get_cryptography()

    if master_key is None:
        master_key = os.environ.get("TUTOR_MASTER_KEY", "")
        if not master_key:
            # 生成临时密钥用于开发模式（不推荐生产使用）
            logger.warning("No TUTOR_MASTER_KEY found, using temporary key (not secure!)")
            # Fernet 需要 32 字节的 url-safe base64 编码
            from cryptography.fernet import Fernet
            master_key = Fernet.generate_key().decode()

    # 确保密钥是有效的 Fernet 格式
    try:
        key_bytes = master_key.encode() if isinstance(master_key, str) else master_key
        fernet = Fernet(key_bytes)
    except Exception as e:
        raise SecureConfigError(f"Invalid master key: {e}")

    encrypted = fernet.encrypt(api_key.encode())
    encrypted_b64 = base64.urlsafe_b64encode(encrypted).decode()

    return f"ENCRYPTED:{encrypted_b64}"


def decrypt_api_key(encrypted_key: str, master_key: Optional[str] = None) -> str:
    """解密 API Key

    Args:
        encrypted_key: 加密后的字符串
        master_key: 主密钥

    Returns:
        解密后的明文 API Key

    Raises:
        InvalidKeyError: 无效的加密数据
    """
    Fernet = _get_cryptography()

    if not encrypted_key.startswith("ENCRYPTED:"):
        raise InvalidKeyError(f"Not an encrypted key: {encrypted_key[:20]}...")

    if master_key is None:
        master_key = os.environ.get("TUTOR_MASTER_KEY", "")
        if not master_key:
            raise SecureConfigError("No TUTOR_MASTER_KEY environment variable set")

    try:
        key_bytes = master_key.encode() if isinstance(master_key, str) else master_key
        fernet = Fernet(key_bytes)

        encrypted_b64 = encrypted_key[10:]  # Remove "ENCRYPTED:" prefix
        encrypted = base64.urlsafe_b64decode(encrypted_b64)

        decrypted_bytes = fernet.decrypt(encrypted)
        decrypted: str = decrypted_bytes.decode()
        return decrypted
    except Exception as e:
        raise InvalidKeyError(f"Failed to decrypt: {e}")


class SecureConfig:
    """安全配置管理器

    支持：
    - 加密存储敏感值
    - 从 YAML 文件加载
    - 保存到 YAML 文件
    - 自动解密访问

    用法：
        # 设置加密值
        config = SecureConfig()
        config.set_encrypted("OPENAI_API_KEY", "sk-xxx")

        # 获取时自动解密
        api_key = config.get("OPENAI_API_KEY")

        # 保存到文件
        config.save("config.yaml")

        # 从文件加载
        config = SecureConfig.load("config.yaml")
    """

    _instance: Optional["SecureConfig"] = None
    _master_key: Optional[bytes]
    _data: Dict[str, Any]
    _encrypted_keys: set[str]

    def __init__(self, master_key: Optional[str] = None):
        """初始化安全配置

        Args:
            master_key: 主密钥，如果为 None 则从环境变量读取
        """
        if master_key is None:
            master_key = os.environ.get("TUTOR_MASTER_KEY", "")

        if master_key:
            self._master_key: Optional[bytes] = master_key.encode() if isinstance(master_key, str) else master_key
        else:
            self._master_key = None
            logger.warning(
                "SecureConfig: No TUTOR_MASTER_KEY set. "
                "Encrypted values will not be decryptable!"
            )

        self._data: Dict[str, Any] = {}
        self._encrypted_keys: set[str] = set()

    @staticmethod
    def _generate_key() -> str:
        """生成新的主密钥（用于首次设置）"""
        from cryptography.fernet import Fernet
        return Fernet.generate_key().decode()

    def set(self, key: str, value: Any) -> None:
        """设置配置值

        Args:
            key: 配置键
            value: 配置值
        """
        self._data[key] = value

    def set_encrypted(self, key: str, value: str) -> None:
        """设置加密的配置值

        Args:
            key: 配置键
            value: 明文值（会被加密存储）
        """
        if self._master_key is None:
            raise SecureConfigError("Cannot encrypt without master key")

        encrypted = encrypt_api_key(value, self._master_key.decode() if isinstance(self._master_key, bytes) else self._master_key)
        self._data[key] = encrypted
        self._encrypted_keys.add(key)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（加密值自动解密）

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值（如果是加密值则自动解密）
        """
        value = self._data.get(key, default)

        if value is None:
            return default

        # 如果是加密值且需要解密
        if key in self._encrypted_keys and isinstance(value, str) and value.startswith("ENCRYPTED:"):
            if self._master_key is None:
                raise SecureConfigError("Cannot decrypt without master key")
            master = self._master_key.decode() if isinstance(self._master_key, bytes) else self._master_key
            return decrypt_api_key(value, master)

        return value

    def is_encrypted(self, key: str) -> bool:
        """检查配置值是否加密"""
        return key in self._encrypted_keys

    def to_dict(self) -> Dict[str, Any]:
        """导出配置字典

        Returns:
            配置字典
        """
        return self._data.copy()

    def save(self, path: str) -> None:
        """保存配置到 YAML 文件

        Args:
            path: 文件路径
        """
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(self._data, f, default_flow_style=False)

    @classmethod
    def load(cls, path: str, master_key: Optional[str] = None) -> "SecureConfig":
        """从 YAML 文件加载配置

        Args:
            path: 文件路径
            master_key: 主密钥（默认从环境变量读取）

        Returns:
            SecureConfig 实例
        """
        if master_key is None:
            master_key = os.environ.get("TUTOR_MASTER_KEY", "")

        config = cls(master_key=master_key)

        if not os.path.exists(path):
            logger.warning(f"Config file not found: {path}")
            return config

        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        config._data = data

        # 检测哪些值是加密的
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("ENCRYPTED:"):
                config._encrypted_keys.add(key)

        return config

    @classmethod
    def from_dict(cls, data: Dict[str, Any], master_key: Optional[str] = None) -> "SecureConfig":
        """从字典创建配置

        Args:
            data: 配置字典
            master_key: 主密钥

        Returns:
            SecureConfig 实例
        """
        config = cls(master_key=master_key)
        config._data = data.copy()

        # 检测加密值
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("ENCRYPTED:"):
                config._encrypted_keys.add(key)

        return config

    def __repr__(self) -> str:
        return f"<SecureConfig keys={list(self._data.keys())}>"
