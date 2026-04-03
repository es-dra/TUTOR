"""Secure Config 单元测试

测试 API Key 安全存储功能：
- Fernet 对称加密
- 加密/解密 API Keys
- 环境变量存储主密钥
"""

import pytest
from unittest.mock import patch, MagicMock
import os
import tempfile


# 固定的测试用主密钥 (必须是有效的 Fernet key 格式)
# 使用 python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 生成
TEST_MASTER_KEY = "d7o7go6szFVBh1tD8JeAmjndY_uHyvkiGD6TbuUlq_U="


class TestSecureConfig:
    """安全配置测试"""

    def test_encrypt_decrypt_roundtrip(self):
        """加密后解密应该得到原值"""
        from tutor.core.secure_config import encrypt_api_key, decrypt_api_key

        api_key = "sk-abc123xyz789"
        encrypted = encrypt_api_key(api_key, master_key=TEST_MASTER_KEY)

        # 加密后不应该等于原值
        assert encrypted != api_key

        # 解密后应该等于原值
        decrypted = decrypt_api_key(encrypted, master_key=TEST_MASTER_KEY)
        assert decrypted == api_key

    def test_different_encryptions_for_same_value(self):
        """同一值每次加密应该不同（salt）"""
        from tutor.core.secure_config import encrypt_api_key, decrypt_api_key

        api_key = "sk-test123"
        enc1 = encrypt_api_key(api_key, master_key=TEST_MASTER_KEY)
        enc2 = encrypt_api_key(api_key, master_key=TEST_MASTER_KEY)

        # 每次加密结果不同（因为有随机 salt）
        assert enc1 != enc2

        # 但都能解密回原值
        assert decrypt_api_key(enc1, master_key=TEST_MASTER_KEY) == api_key
        assert decrypt_api_key(enc2, master_key=TEST_MASTER_KEY) == api_key

    def test_encrypted_key_format(self):
        """加密后的 key 应该有特定格式"""
        from tutor.core.secure_config import encrypt_api_key

        api_key = "sk-test"
        encrypted = encrypt_api_key(api_key, master_key=TEST_MASTER_KEY)

        # 应该是字符串
        assert isinstance(encrypted, str)
        # 应该以特定前缀开头
        assert encrypted.startswith("ENCRYPTED:")

    def test_decrypt_invalid_key_raises(self):
        """解密无效 key 应该抛出异常"""
        from tutor.core.secure_config import decrypt_api_key, InvalidKeyError

        with pytest.raises(InvalidKeyError):
            decrypt_api_key("invalid-encrypted-key", master_key=TEST_MASTER_KEY)

    def test_load_config_with_encrypted_keys(self):
        """加载包含加密 key 的配置"""
        from tutor.core.secure_config import SecureConfig

        with patch.dict(os.environ, {"TUTOR_MASTER_KEY": TEST_MASTER_KEY}):
            config = SecureConfig()

            # 设置加密值 - 使用 set_encrypted
            config.set_encrypted("OPENAI_API_KEY", "sk-secret123")

            # 获取时应该自动解密
            assert config.get("OPENAI_API_KEY") == "sk-secret123"

    def test_get_unencrypted_key(self):
        """获取非加密的 key"""
        from tutor.core.secure_config import SecureConfig

        with patch.dict(os.environ, {"TUTOR_MASTER_KEY": TEST_MASTER_KEY}):
            config = SecureConfig()
            config.set("TEST_KEY", "plain-value")

            assert config.get("TEST_KEY") == "plain-value"

    def test_master_key_from_env(self):
        """主密钥应从环境变量读取"""
        from tutor.core.secure_config import SecureConfig

        with patch.dict(os.environ, {"TUTOR_MASTER_KEY": TEST_MASTER_KEY}):
            config = SecureConfig()
            assert config._master_key == TEST_MASTER_KEY.encode()


class TestSecureConfigYAML:
    """安全配置 YAML 集成测试"""

    def test_save_and_load_encrypted_config(self):
        """保存并加载加密配置"""
        from tutor.core.secure_config import SecureConfig
        import tempfile

        with patch.dict(os.environ, {"TUTOR_MASTER_KEY": TEST_MASTER_KEY}):
            config = SecureConfig()

            # 设置加密值
            config.set_encrypted("api_key", "sk-secret123")
            config.set("provider", "openai")

            # 保存到临时文件
            fd, path = tempfile.mkstemp(suffix=".yaml")
            os.close(fd)

            try:
                config.save(path)

                # 重新加载
                loaded_config = SecureConfig.load(path)

                assert loaded_config.get("provider") == "openai"
                assert loaded_config.get("api_key") == "sk-secret123"
            finally:
                os.unlink(path)

    def test_load_yaml_with_encrypted_api_key(self):
        """加载包含加密 API Key 的 YAML"""
        from tutor.core.secure_config import SecureConfig
        import tempfile
        import yaml

        # 使用固定的密钥生成加密值
        from tutor.core.secure_config import encrypt_api_key
        encrypted_key = encrypt_api_key("sk-live-abc123", master_key=TEST_MASTER_KEY)

        config_yaml = f"""
provider: openai
api_key: "{encrypted_key}"
"""

        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.write(fd, config_yaml.encode())
        os.close(fd)

        try:
            with patch.dict(os.environ, {"TUTOR_MASTER_KEY": TEST_MASTER_KEY}):
                config = SecureConfig.load(path)
                assert config.get("api_key") == "sk-live-abc123"
        finally:
            os.unlink(path)
