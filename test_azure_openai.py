#!/usr/bin/env python3
"""
Simple test script to debug Azure OpenAI connection issues.
"""

import os
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from massgen.cli import load_env_file
load_env_file()

# Test Azure OpenAI backend creation
print("=== Testing Azure OpenAI Backend Creation ===")
try:
    from massgen.backend.azure_openai import AzureOpenAIBackend
    backend = AzureOpenAIBackend()
    print("✅ Backend created successfully")
    print(f"  Provider: {backend.get_provider_name()}")
    print(f"  Base URL: {backend.config.get('base_url')}")
    print(f"  API Key: {'SET' if backend.api_key else 'NOT_SET'}")
    if backend.api_key:
        print(f"  API Key (first 10 chars): {backend.api_key[:10]}...")
except Exception as e:
    print(f"❌ Failed to create backend: {e}")
    sys.exit(1)

# Test OpenAI client creation
print("\n=== Testing OpenAI Client Creation ===")
try:
    import openai
    client = openai.AsyncOpenAI(
        api_key=backend.api_key,
        base_url=backend.config.get('base_url')
    )
    print("✅ OpenAI client created successfully")
    print(f"  Base URL: {client.base_url}")
except Exception as e:
    print(f"❌ Failed to create OpenAI client: {e}")
    sys.exit(1)

# Test simple API call (this will likely fail with 404, but we'll see the exact error)
print("\n=== Testing API Call ===")
print("Note: This will likely fail with 404 if the deployment doesn't exist, but we'll see the exact error message")
try:
    import asyncio
    
    async def test_api_call():
        try:
            response = await client.chat.completions.create(
                model="gpt-4.1",  # This is the deployment name
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            print("✅ API call successful!")
            print(f"  Response: {response.choices[0].message.content}")
        except Exception as e:
            print(f"❌ API call failed: {e}")
            print(f"  Error type: {type(e).__name__}")
            if hasattr(e, 'response'):
                print(f"  Response status: {e.response.status_code}")
                print(f"  Response body: {e.response.text}")
    
    asyncio.run(test_api_call())
    
except Exception as e:
    print(f"❌ Failed to test API call: {e}")

print("\n=== Troubleshooting Tips ===")
print("1. Check if the deployment name 'gpt-4.1' exists in your Azure OpenAI resource")
print("2. Verify the endpoint URL is correct")
print("3. Check if the API key has the right permissions")
print("4. Verify the deployment is active and not in a failed state")
print("5. Check the Azure OpenAI resource region and ensure it's accessible")
