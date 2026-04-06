#!/usr/bin/env python3
"""
测试API连接
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tutor.core.model import ModelGateway

print("=" * 80)
print("测试API连接")
print("=" * 80)

# 测试DeepSeek API
print("\n1. 测试DeepSeek API...")
deepseek_config = {
    "provider": "deepseek",
    "api_key": "sk-d66cf9782040462e8d52d1c957e6c9b9",
    "api_base": "https://api.deepseek.com",
    "models": {
        "default": "deepseek-chat",
    }
}

try:
    gateway = ModelGateway(deepseek_config)
    print("✅ DeepSeek网关创建成功")
    
    # 简单测试
    response = gateway.chat(
        "default",
        [{"role": "user", "content": "Hello! 你好！"}]
    )
    print(f"✅ DeepSeek响应: {response[:100]}...")
except Exception as e:
    print(f"❌ DeepSeek测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
