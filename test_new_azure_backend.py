#!/usr/bin/env python3
"""
Test the new Azure OpenAI backend using the official AzureOpenAI client.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from massgen.cli import load_env_file
load_env_file()

async def test_new_azure_backend():
    """Test the new Azure OpenAI backend."""
    
    print("=== Testing New Azure OpenAI Backend ===")
    
    try:
        # Check if Azure OpenAI is available
        from massgen.backend.azure_openai import AzureOpenAIBackend, AZURE_OPENAI_AVAILABLE
        
        if not AZURE_OPENAI_AVAILABLE:
            print("❌ Azure OpenAI client not available")
            print("💡 Install with: pip install openai")
            return
        
        print("✅ Azure OpenAI client available")
        
        # Create backend
        backend = AzureOpenAIBackend()
        print("✅ Backend created successfully")
        print(f"  Provider: {backend.get_provider_name()}")
        print(f"  Azure Endpoint: {backend.azure_endpoint}")
        print(f"  API Version: {backend.api_version}")
        print(f"  API Key: {'SET' if backend.api_key else 'NOT_SET'}")
        
        # Test cost calculation
        cost = backend.calculate_cost(1000, 500, "gpt-4.1")
        print(f"  Cost calculation for gpt-4.1 (1000 input, 500 output tokens): ${cost:.6f}")
        
        # Test simple API call
        print("\n=== Testing Simple API Call ===")
        print("Note: This will test if the deployment exists and is accessible")
        
        try:
            response = backend.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello"}
                ],
                model="gpt-4.1",  # This should be your deployment name
                max_tokens=10
            )
            print("✅ API call successful!")
            print(f"  Response: {response.choices[0].message.content}")
            print(f"  Model: {response.model}")
            print(f"  Usage: {response.usage}")
            
        except Exception as e:
            print(f"❌ API call failed: {e}")
            print(f"  Error type: {type(e).__name__}")
            
            if "404" in str(e):
                print("💡 404 error means the deployment 'gpt-4.1' doesn't exist")
                print("💡 Check your Azure OpenAI resource for available deployments")
            elif "401" in str(e):
                print("💡 401 error means authentication failed")
                print("💡 Check your API key and permissions")
            elif "400" in str(e):
                print("💡 400 error means bad request")
                print("💡 Check your deployment name and parameters")
        
        print("\n=== Next Steps ===")
        print("1. If API call succeeded: Your Azure OpenAI integration is working!")
        print("2. If 404 error: Create deployment 'gpt-4.1' in Azure OpenAI")
        print("3. Test with MassGen: uv run python -m massgen.cli --backend azure_openai --model gpt-4.1 'Your question'")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_new_azure_backend())
