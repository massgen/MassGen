"""
API request/response helpers for backend implementations.
Provides common patterns for building requests and parsing responses.
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional, Union


class APIRequestBuilder:
    """
    Build API requests with common patterns across different providers.
    """
    
    @staticmethod
    def add_safety_settings(params: Dict[str, Any], provider: str) -> Dict[str, Any]:
        """
        Add provider-specific safety settings to API parameters.
        
        Args:
            params: API parameters
            provider: Provider name (openai, claude, gemini, etc.)
            
        Returns:
            Updated parameters with safety settings
        """
        if provider.lower() == "gemini":
            # Gemini safety settings
            params["safety_settings"] = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH", 
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        
        elif provider.lower() == "claude":
            # Claude typically doesn't need explicit safety settings
            # but we ensure max_tokens is set
            if "max_tokens" not in params:
                params["max_tokens"] = 4096
        
        elif provider.lower() == "openai":
            # OpenAI safety can be controlled via moderation endpoint
            # No inline safety settings needed
            pass
        
        return params
    
    @staticmethod
    def add_generation_config(
        params: Dict[str, Any],
        config: Dict[str, Any],
        provider: str = "openai"
    ) -> Dict[str, Any]:
        """
        Add generation configuration to API parameters.
        
        Args:
            params: Base API parameters
            config: Generation configuration
            provider: Provider name for specific formatting
            
        Returns:
            Updated parameters with generation config
        """
        # Common parameters that most providers support
        common_params = [
            "temperature", "top_p", "top_k", "max_tokens",
            "presence_penalty", "frequency_penalty", "stop"
        ]
        
        for param in common_params:
            if param in config:
                params[param] = config[param]
        
        # Provider-specific parameter mapping
        if provider.lower() == "gemini":
            # Gemini uses generation_config wrapper
            gen_config = {}
            for param in ["temperature", "top_p", "top_k", "max_output_tokens"]:
                if param in config:
                    gen_config[param] = config[param]
                elif param == "max_output_tokens" and "max_tokens" in config:
                    gen_config["max_output_tokens"] = config["max_tokens"]
            
            if gen_config:
                params["generation_config"] = gen_config
        
        elif provider.lower() == "claude":
            # Claude uses max_tokens instead of max_output_tokens
            if "max_tokens" in config:
                params["max_tokens"] = config["max_tokens"]
            elif "max_output_tokens" in config:
                params["max_tokens"] = config["max_output_tokens"]
        
        # Handle special parameters
        if "stream" in config:
            params["stream"] = config["stream"]
        
        if "tools" in config and config["tools"]:
            params["tools"] = config["tools"]
            
            # Tool choice handling
            if "tool_choice" in config:
                if provider.lower() == "openai":
                    params["tool_choice"] = config["tool_choice"]
                elif provider.lower() == "claude":
                    # Claude uses tool_choice differently
                    if config["tool_choice"] == "auto":
                        params["tool_choice"] = {"type": "auto"}
                    elif config["tool_choice"] == "none":
                        params["tool_choice"] = {"type": "none"}
        
        return params
    
    @staticmethod
    def build_retry_config(provider: str) -> Dict[str, Any]:
        """
        Build provider-specific retry configuration.
        
        Args:
            provider: Provider name
            
        Returns:
            Retry configuration dictionary
        """
        config = {
            "max_retries": 3,
            "retry_delay": 1.0,
            "retry_multiplier": 2.0,
            "retry_errors": ["rate_limit", "timeout", "server_error"]
        }
        
        # Provider-specific adjustments
        if provider.lower() == "openai":
            config["retry_errors"].append("insufficient_quota")
        elif provider.lower() == "claude":
            config["retry_errors"].append("overloaded_error")
        elif provider.lower() == "gemini":
            config["retry_errors"].append("resource_exhausted")
        
        return config
    
    @staticmethod
    def add_streaming_options(params: Dict[str, Any], provider: str) -> Dict[str, Any]:
        """
        Add streaming-specific options for providers.
        
        Args:
            params: API parameters
            provider: Provider name
            
        Returns:
            Updated parameters with streaming options
        """
        params["stream"] = True
        
        if provider.lower() == "openai":
            # OpenAI streaming options
            params["stream_options"] = {"include_usage": True}
        
        elif provider.lower() == "claude":
            # Claude streaming doesn't need special options
            pass
        
        elif provider.lower() == "gemini":
            # Gemini uses different streaming mechanism
            params["stream"] = True
        
        return params


class ResponseParser:
    """
    Parse responses from different LLM APIs into standardized format.
    """
    
    @staticmethod
    def extract_content(response: Dict[str, Any], provider: str) -> str:
        """
        Extract text content from provider response.
        
        Args:
            response: Raw API response
            provider: Provider name
            
        Returns:
            Extracted text content
        """
        if provider.lower() == "openai":
            # OpenAI Chat Completions format
            choices = response.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                return message.get("content", "")
        
        elif provider.lower() == "claude":
            # Claude Response API format
            content = response.get("content", [])
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                return "\n".join(text_parts)
            elif isinstance(content, str):
                return content
        
        elif provider.lower() == "gemini":
            # Gemini format
            candidates = response.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                text_parts = []
                for part in parts:
                    if isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                return "\n".join(text_parts)
        
        elif provider.lower() == "response_api":
            # OpenAI Response API format
            return response.get("response", {}).get("content", "")
        
        return ""
    
    @staticmethod
    def extract_tool_calls(response: Dict[str, Any], provider: str) -> List[Dict[str, Any]]:
        """
        Extract tool calls from provider response.
        
        Args:
            response: Raw API response
            provider: Provider name
            
        Returns:
            List of tool calls in standardized format
        """
        tool_calls = []
        
        if provider.lower() == "openai":
            choices = response.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                tool_calls = message.get("tool_calls", [])
        
        elif provider.lower() == "claude":
            content = response.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id"),
                            "type": "function",
                            "function": {
                                "name": block.get("name"),
                                "arguments": json.dumps(block.get("input", {}))
                            }
                        })
        
        elif provider.lower() == "gemini":
            candidates = response.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                for part in parts:
                    if isinstance(part, dict) and "functionCall" in part:
                        func_call = part["functionCall"]
                        tool_calls.append({
                            "id": f"call_{len(tool_calls)}",
                            "type": "function",
                            "function": {
                                "name": func_call.get("name"),
                                "arguments": json.dumps(func_call.get("args", {}))
                            }
                        })
        
        return tool_calls
    
    @staticmethod
    def extract_usage(response: Dict[str, Any], provider: str) -> Dict[str, int]:
        """
        Extract token usage information from response.
        
        Args:
            response: Raw API response
            provider: Provider name
            
        Returns:
            Dictionary with usage information
        """
        usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
        
        if provider.lower() == "openai":
            api_usage = response.get("usage", {})
            usage["prompt_tokens"] = api_usage.get("prompt_tokens", 0)
            usage["completion_tokens"] = api_usage.get("completion_tokens", 0)
            usage["total_tokens"] = api_usage.get("total_tokens", 0)
        
        elif provider.lower() == "claude":
            api_usage = response.get("usage", {})
            usage["prompt_tokens"] = api_usage.get("input_tokens", 0)
            usage["completion_tokens"] = api_usage.get("output_tokens", 0)
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        
        elif provider.lower() == "gemini":
            metadata = response.get("usageMetadata", {})
            usage["prompt_tokens"] = metadata.get("promptTokenCount", 0)
            usage["completion_tokens"] = metadata.get("candidatesTokenCount", 0)
            usage["total_tokens"] = metadata.get("totalTokenCount", 0)
        
        return usage
    
    @staticmethod
    def extract_finish_reason(response: Dict[str, Any], provider: str) -> Optional[str]:
        """
        Extract finish reason from response.
        
        Args:
            response: Raw API response
            provider: Provider name
            
        Returns:
            Finish reason string or None
        """
        if provider.lower() == "openai":
            choices = response.get("choices", [])
            if choices:
                return choices[0].get("finish_reason")
        
        elif provider.lower() == "claude":
            return response.get("stop_reason")
        
        elif provider.lower() == "gemini":
            candidates = response.get("candidates", [])
            if candidates:
                return candidates[0].get("finishReason")
        
        return None
    
    @staticmethod
    def is_error_response(response: Dict[str, Any], provider: str) -> bool:
        """
        Check if response indicates an error.
        
        Args:
            response: Raw API response
            provider: Provider name
            
        Returns:
            True if response contains an error
        """
        if "error" in response:
            return True
        
        if provider.lower() == "openai":
            return "error" in response
        
        elif provider.lower() == "claude":
            return response.get("type") == "error"
        
        elif provider.lower() == "gemini":
            # Check for blocked content or errors
            candidates = response.get("candidates", [])
            if candidates:
                for candidate in candidates:
                    if candidate.get("finishReason") in ["SAFETY", "RECITATION"]:
                        return True
            return "error" in response
        
        return False
    
    @staticmethod
    def extract_error_message(response: Dict[str, Any], provider: str) -> str:
        """
        Extract error message from response.
        
        Args:
            response: Raw API response
            provider: Provider name
            
        Returns:
            Error message string
        """
        if "error" in response:
            error = response["error"]
            if isinstance(error, dict):
                return error.get("message", str(error))
            return str(error)
        
        if provider.lower() == "claude":
            if response.get("type") == "error":
                return response.get("error", {}).get("message", "Unknown error")
        
        elif provider.lower() == "gemini":
            # Check for safety blocks
            candidates = response.get("candidates", [])
            if candidates:
                for candidate in candidates:
                    reason = candidate.get("finishReason")
                    if reason == "SAFETY":
                        return "Response blocked due to safety filters"
                    elif reason == "RECITATION":
                        return "Response blocked due to recitation filters"
        
        return "Unknown error occurred"


class ProviderEndpoints:
    """
    Provider-specific endpoint configurations.
    """
    
    ENDPOINTS = {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "chat": "/chat/completions",
            "models": "/models"
        },
        "claude": {
            "base_url": "https://api.anthropic.com/v1",
            "messages": "/messages",
            "complete": "/complete"
        },
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "generate": "/models/{model}:generateContent",
            "stream": "/models/{model}:streamGenerateContent"
        },
        "azure": {
            "base_url": "https://{resource}.openai.azure.com",
            "chat": "/openai/deployments/{deployment}/chat/completions"
        }
    }
    
    @classmethod
    def get_endpoint(cls, provider: str, endpoint_type: str, **kwargs) -> str:
        """
        Get full endpoint URL for a provider.
        
        Args:
            provider: Provider name
            endpoint_type: Type of endpoint (chat, models, etc.)
            **kwargs: Additional parameters for URL formatting
            
        Returns:
            Full endpoint URL
        """
        provider_config = cls.ENDPOINTS.get(provider.lower(), {})
        base_url = provider_config.get("base_url", "")
        endpoint = provider_config.get(endpoint_type, "")
        
        # Format URL with provided parameters
        if kwargs:
            base_url = base_url.format(**kwargs)
            endpoint = endpoint.format(**kwargs)
        
        return base_url + endpoint


# Missing import for json
import json