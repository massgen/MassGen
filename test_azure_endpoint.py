#!/usr/bin/env python3
"""
Test different Azure OpenAI endpoint formats and API versions.
"""

import os
import sys
import asyncio
import aiohttp
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from massgen.cli import load_env_file
load_env_file()

async def test_endpoint_format():
    """Test different endpoint formats and API versions."""
    
    # Get environment variables
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    base_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    
    if not api_key or not base_endpoint:
        print("❌ Missing required environment variables")
        return
    
    # Clean up base endpoint
    if base_endpoint.endswith('/'):
        base_endpoint = base_endpoint[:-1]
    
    # Different endpoint formats to test
    endpoint_formats = [
        f"{base_endpoint}/openai",
        f"{base_endpoint}/openai/v1",
        f"{base_endpoint}/v1",
        base_endpoint
    ]
    
    # Different API versions to test
    api_versions = [
        "2024-02-15-preview",
        "2024-12-01-preview", 
        "2024-06-01-preview",
        "2024-03-01-preview",
        "2023-12-01-preview"
    ]
    
    print("=== Testing Azure OpenAI Endpoint Formats ===")
    print(f"Base endpoint: {base_endpoint}")
    print(f"API Key: {'SET' if api_key else 'NOT_SET'}")
    print()
    
    working_combinations = []
    
    for endpoint_format in endpoint_formats:
        for api_version in api_versions:
            # Test deployments endpoint
            deployments_url = f"{endpoint_format}/deployments?api-version={api_version}"
            
            print(f"Testing: {endpoint_format} (API v{api_version})")
            
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {
                        "api-key": api_key,
                        "Content-Type": "application/json"
                    }
                    
                    async with session.get(deployments_url, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            print(f"  ✅ SUCCESS - Status: {response.status}")
                            working_combinations.append((endpoint_format, api_version))
                            
                            # Try to get deployment data
                            try:
                                data = await response.json()
                                deployments = data.get('data', [])
                                print(f"     Found {len(deployments)} deployment(s)")
                                
                                if deployments:
                                    for deployment in deployments[:3]:  # Show first 3
                                        deployment_id = deployment.get('id', 'Unknown')
                                        model = deployment.get('model', 'Unknown')
                                        print(f"       - {deployment_id} ({model})")
                                        
                            except Exception as e:
                                print(f"     Could not parse response: {e}")
                                
                        elif response.status == 401:
                            print(f"  ❌ UNAUTHORIZED - Status: {response.status}")
                        elif response.status == 404:
                            print(f"  ❌ NOT FOUND - Status: {response.status}")
                        else:
                            print(f"  ❌ HTTP {response.status}")
                            
            except asyncio.TimeoutError:
                print(f"  ❌ TIMEOUT")
            except Exception as e:
                print(f"  ❌ ERROR: {str(e)[:50]}...")
            
            print()
    
    print("=== Results ===")
    if working_combinations:
        print("✅ Working endpoint combinations:")
        for endpoint, api_version in working_combinations:
            print(f"  - {endpoint} (API v{api_version})")
        
        # Test the first working combination with a simple chat completion
        print("\n=== Testing Chat Completion with Working Endpoint ===")
        working_endpoint, working_api_version = working_combinations[0]
        
        # Test with a simple model name (this might work even without deployments)
        test_url = f"{working_endpoint}/chat/completions?api-version={working_api_version}"
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "api-key": api_key,
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "gpt-4",  # Try with a standard model name
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 5
                }
                
                async with session.post(test_url, headers=headers, json=payload, timeout=10) as response:
                    if response.status == 200:
                        print("✅ Chat completion endpoint working!")
                        print("💡 Your Azure OpenAI resource is properly configured")
                    elif response.status == 400:
                        print("✅ Chat completion endpoint accessible!")
                        print("💡 The endpoint works, but you need to create deployments")
                        print("💡 Or use the correct deployment names")
                    else:
                        print(f"❌ Chat completion failed: HTTP {response.status}")
                        
        except Exception as e:
            print(f"❌ Chat completion test failed: {e}")
            
    else:
        print("❌ No working endpoint combinations found")
        print("💡 Check your Azure OpenAI resource configuration")
        print("💡 Ensure the OpenAI service is enabled in your resource")

if __name__ == "__main__":
    asyncio.run(test_endpoint_format())
