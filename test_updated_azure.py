#!/usr/bin/env python3
"""
Test the updated Azure OpenAI backend with the correct endpoint format.
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

async def test_updated_backend():
    """Test the updated Azure OpenAI backend."""
    
    print("=== Testing Updated Azure OpenAI Backend ===")
    
    try:
        from massgen.backend.azure_openai import AzureOpenAIBackend
        
        # Create backend
        backend = AzureOpenAIBackend()
        print("✅ Backend created successfully")
        print(f"  Provider: {backend.get_provider_name()}")
        print(f"  Base URL: {backend.config.get('base_url')}")
        print(f"  API Key: {'SET' if backend.api_key else 'NOT_SET'}")
        
        # Test the base URL format
        base_url = backend.config.get('base_url')
        if '/openai/deployments/' not in base_url:
            print("✅ Base URL format correct (no /openai/deployments/ yet)")
        else:
            print("✅ Base URL format correct")
        
        # Test cost calculation for gpt-4.1
        cost = backend.calculate_cost(1000, 500, "gpt-4.1")
        print(f"  Cost calculation for gpt-4.1 (1000 input, 500 output tokens): ${cost:.6f}")
        
        # Test the deployment URL construction
        print("\n=== Testing Deployment URL Construction ===")
        
        # Simulate what happens in stream_with_tools
        deployment_name = "gpt-4.1"
        original_base_url = backend.config['base_url']
        deployment_base_url = f"{original_base_url}/openai/deployments/{deployment_name}"
        
        print(f"  Original base URL: {original_base_url}")
        print(f"  Deployment base URL: {deployment_base_url}")
        print(f"  Expected format: endpoint/openai/deployments/{deployment_name}")
        
        # Check if this matches the working agentweb format
        # Clean up the endpoint to remove trailing slash for comparison
        clean_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT').rstrip('/')
        expected_format = f"{clean_endpoint}/openai/deployments/{deployment_name}"
        print(f"  Working format (cleaned): {expected_format}")
        
        if deployment_base_url == expected_format:
            print("✅ URL format matches working implementation!")
        else:
            print("❌ URL format does not match working implementation")
            print("   This might cause 404 errors")
        
        print("\n=== Next Steps ===")
        print("1. Ensure you have a deployment named 'gpt-4.1' in your Azure OpenAI resource")
        print("2. Test with: uv run python -m massgen.cli --backend azure_openai --model gpt-4.1 'Your question'")
        print("3. If still getting 404, check the deployment name in Azure Portal")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_updated_backend())
