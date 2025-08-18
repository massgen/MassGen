#!/usr/bin/env python3
"""
List available Azure OpenAI deployments using Azure REST API.
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

async def list_deployments():
    """List available deployments using Azure REST API."""
    
    # Get environment variables
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    
    if not api_key or not endpoint:
        print("❌ Missing required environment variables")
        print("   AZURE_OPENAI_API_KEY:", "SET" if api_key else "NOT_SET")
        print("   AZURE_OPENAI_ENDPOINT:", "SET" if endpoint else "NOT_SET")
        return
    
    # Clean up endpoint URL
    if endpoint.endswith('/'):
        endpoint = endpoint[:-1]
    
    # Construct the deployments API URL
    deployments_url = f"{endpoint}/openai/deployments?api-version={api_version}"
    
    print("=== Azure OpenAI Deployments ===")
    print(f"Endpoint: {endpoint}")
    print(f"API Version: {api_version}")
    print(f"Deployments URL: {deployments_url}")
    print()
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "api-key": api_key,
                "Content-Type": "application/json"
            }
            
            async with session.get(deployments_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    deployments = data.get('data', [])
                    
                    if deployments:
                        print(f"✅ Found {len(deployments)} deployment(s):")
                        print()
                        for deployment in deployments:
                            deployment_id = deployment.get('id', 'Unknown')
                            model = deployment.get('model', 'Unknown')
                            status = deployment.get('status', 'Unknown')
                            created_at = deployment.get('created_at', 'Unknown')
                            
                            print(f"  📋 Deployment: {deployment_id}")
                            print(f"     Model: {model}")
                            print(f"     Status: {status}")
                            print(f"     Created: {created_at}")
                            print()
                        
                        print("💡 Use these deployment names in your MassGen configuration!")
                        print("   Example: uv run python -m massgen.cli --backend azure_openai --model <deployment_id> 'Your question'")
                        
                    else:
                        print("❌ No deployments found")
                        print("💡 You need to create deployments in your Azure OpenAI resource first")
                        
                elif response.status == 401:
                    print("❌ Unauthorized (401)")
                    print("💡 Check if your API key is correct and has the right permissions")
                    
                elif response.status == 404:
                    print("❌ Not Found (404)")
                    print("💡 Check if your endpoint URL is correct")
                    
                else:
                    print(f"❌ HTTP {response.status}")
                    error_text = await response.text()
                    print(f"   Error: {error_text}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Check your network connection and Azure OpenAI resource status")

if __name__ == "__main__":
    asyncio.run(list_deployments())
