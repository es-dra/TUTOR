#!/usr/bin/env python3
"""API Key Encryption Utility

This script encrypts API keys for secure storage in providers.yaml.

Usage:
    python encrypt_api_keys.py <api_key>

Example:
    python encrypt_api_keys.py sk-xxx123

The encrypted key can be stored in providers.yaml as:
    provider_api_key: "ENCRYPTED:<encrypted-value>"
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tutor.core.secure_config import encrypt_api_key


def main():
    if len(sys.argv) < 2:
        print("Usage: python encrypt_api_keys.py <api_key>")
        print("Example: python encrypt_api_keys.py sk-xxx123")
        sys.exit(1)

    api_key = sys.argv[1]

    # Get master key from environment or generate warning
    master_key = os.environ.get("TUTOR_MASTER_KEY", "")

    encrypted = encrypt_api_key(api_key, master_key=master_key if master_key else None)

    print(f"API Key: {api_key[:10]}...")
    print(f"Encrypted: {encrypted}")

    if not master_key:
        print("\n⚠️  Warning: TUTOR_MASTER_KEY not set.")
        print("The encrypted key will use a temporary key and cannot be decrypted later!")
        print("Set TUTOR_MASTER_KEY environment variable for persistent encryption.")

    print("\nAdd this to your providers.yaml:")
    print(f'  api_key: "{encrypted}"')


if __name__ == "__main__":
    main()
