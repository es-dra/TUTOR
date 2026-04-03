"""密码哈希与验证模块

使用 argon2-cffi 进行安全的密码哈希。
"""

from passlib.context import CryptContext

# Argon2 是目前最安全的密码哈希算法
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    """对密码进行哈希化

    Args:
        password: 明文密码

    Returns:
        哈希后的密码字符串
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码是否匹配

    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码

    Returns:
        密码是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)
