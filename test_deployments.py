#!/usr/bin/env python3
"""
Test common Azure OpenAI deployment names to find which ones exist.
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

# Common deployment names to test
COMMON_DEPLOYMENTS = [
    "gpt-4",
    "gpt-4o", 
    "gpt-4o-mini",
    "gpt-35-turbo",
    "gpt-35-turbo-16k",
    "gpt-4-32k",
    "gpt-4-turbo",
    "gpt-4-turbo-preview"
]

async def test_deployment(client, deployment_name):
    """Test if a deployment name exists."""
    try:
        response = await client.chat.completions.create(
            model=deployment_name,
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        return True, None
    except Exception as e:
        return False, str(e)

async def main():
    # Create Azure OpenAI backend
    from massgen.backend.azure_openai import AzureOpenAIBackend
    backend = AzureOpenAIBackend()
    
    # Create OpenAI client
    import openai
    client = openai.AsyncOpenAI(
        api_key=backend.api_key,
        base_url=backend.config.get('base_url')
    )
    
    print("=== Testing Common Azure OpenAI Deployment Names ===")
    print(f"Endpoint: {backend.config.get('base_url')}")
    print()
    
    working_deployments = []
    
    for deployment in COMMON_DEPLOYMENTS:
        print(f"Testing '{deployment}'...", end=" ")
        success, error = await test_deployment(client, deployment)
        
        if success:
            print("✅ WORKING")
            working_deployments.append(deployment)
        else:
            if "404" in error:
                print("❌ NOT FOUND")
            elif "401" in error:
                print("❌ UNAUTHORIZED")
            else:
                print(f"❌ ERROR: {error[:50]}...")
    
    print()
    print("=== Results ===")
    if working_deployments:
        print("✅ Working deployments:")
        for deployment in working_deployments:
            print(f"  - {deployment}")
        print()
        print("💡 Use one of these deployment names in your MassGen configuration!")
    else:
        print("❌ No working deployments found.")
        print("💡 Check your Azure OpenAI resource and ensure deployments are created.")
    
    print()
    print("=== Next Steps ===")
    print("1. Use a working deployment name in your MassGen command:")
    if working_deployments:
        working_name = working_deployments[0]
        print(f"   uv run python -m massgen.cli --backend azure_openai --model {working_name} 'Your question'")
    print("2. Or update your config files to use a working deployment name")
    print("3. Check Azure Portal for the exact deployment names in your resource")

if __name__ == "__main__":
    asyncio.run(main())
