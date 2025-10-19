#!/usr/bin/env python3
"""
JSON-RPC Server for VSCode Extension

Communicates with VSCode extension via stdio using JSON-RPC protocol.
"""

import asyncio
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


class VSCodeServer:
    """JSON-RPC server for VSCode extension communication."""

    def __init__(self):
        """Initialize the server."""
        self.handlers: Dict[str, Callable] = {}
        self.event_callbacks: List[Callable] = []
        self.request_id = 0
        self._setup_handlers()

    def _setup_handlers(self):
        """Register request handlers."""
        self.handlers = {
            "initialize": self._handle_initialize,
            "query": self._handle_query,
            "configure": self._handle_configure,
            "analyze": self._handle_analyze,
            "list_configs": self._handle_list_configs,
            "test_connection": self._handle_test_connection,
            "get_available_models": self._handle_get_available_models,
        }

    async def start(self):
        """Start the JSON-RPC server and listen for requests."""
        logger.info("VSCode adapter server starting...")
        self._send_log("Server started successfully")

        try:
            while True:
                # Read line from stdin
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )

                if not line:
                    logger.info("EOF received, shutting down")
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    logger.debug(f"Received request: {request.get('method')}")

                    response = await self._handle_request(request)

                    # Send response
                    self._send_response(response)

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                    self._send_error(None, -32700, "Parse error")
                except Exception as e:
                    logger.error(f"Error handling request: {e}")
                    logger.error(traceback.format_exc())
                    self._send_error(None, -32603, str(e))

        except KeyboardInterrupt:
            logger.info("Server interrupted")
        finally:
            logger.info("Server shutdown")

    async def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        if method not in self.handlers:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        try:
            handler = self.handlers[method]
            result = await handler(params)

            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        except Exception as e:
            logger.error(f"Handler error: {e}")
            logger.error(traceback.format_exc())
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialization request."""
        logger.info("Initializing VSCode adapter")
        return {
            "success": True,
            "version": "0.1.0",
            "capabilities": {
                "query": True,
                "configure": True,
                "analyze": True,
                "streaming": True,
            },
        }

    async def _handle_test_connection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle test connection request."""
        return {"success": True, "message": "Connection successful"}

    async def _handle_get_available_models(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get available models request."""
        from massgen.utils import MODEL_MAPPINGS

        # Get models from MassGen's official model mappings
        models_by_provider = {
            "OpenAI": {
                "models": MODEL_MAPPINGS.get("openai", []),
                "popular": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
            },
            "Claude": {
                "models": MODEL_MAPPINGS.get("claude", []),
                "popular": [
                    "claude-3-5-sonnet-latest",
                    "claude-3-5-haiku-latest",
                ],
            },
            "Gemini": {
                "models": MODEL_MAPPINGS.get("gemini", []),
                "popular": ["gemini-2.5-flash", "gemini-2.5-pro"],
            },
            "Grok": {
                "models": MODEL_MAPPINGS.get("grok", []),
                "popular": ["grok-3", "grok-3-mini"],
            },
            "Zai": {
                "models": MODEL_MAPPINGS.get("zai", []),
                "popular": ["glm-4.5"],
            },
        }

        return {"success": True, "models_by_provider": models_by_provider}

    async def _handle_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle query request from VSCode."""
        query_text = params.get("text", "")
        config_path = params.get("config")
        models = params.get("models", [])

        if not query_text:
            raise ValueError("Query text is required")

        self._send_log(f"Processing query: {query_text[:50]}...")

        try:
            # If models are specified, use multi-agent execution
            if models and len(models) > 0:
                return await self._handle_multi_agent_query(query_text, models)
            else:
                return await self._handle_single_agent_query(query_text, config_path)

        except Exception as e:
            logger.error(f"Query execution error: {e}")
            self._send_event({"type": "error", "message": str(e)})
            raise

    async def _handle_single_agent_query(
        self, query_text: str, config_path: Optional[str]
    ) -> Dict[str, Any]:
        """Handle single agent query."""
        from massgen.agent_config import AgentConfig
        from massgen.orchestrator import Orchestrator
        from massgen.cli import create_backend
        from massgen.chat_agent import create_simple_agent

        # Load configuration
        if config_path:
            config = self._load_config(config_path)
        else:
            # Use default single agent config
            config = self._get_default_config()

        # Create a single agent from the config
        agent_id = config.agent_id or "agent-1"

        # Extract backend type and other params
        backend_params = config.backend_params.copy()
        backend_type = backend_params.pop("backend", "openai")

        # Create backend
        backend = create_backend(backend_type, **backend_params)

        # Wrap backend in a ChatAgent
        agent = create_simple_agent(
            backend=backend,
            system_message="You are a helpful AI assistant.",
            agent_id=agent_id,
        )

        # Create agents dictionary
        agents = {agent_id: agent}

        # Create orchestrator with agents
        orchestrator = Orchestrator(
            agents=agents,
            config=config,
        )

        # Send execution start event
        self._send_event(
            {"type": "execution_start", "query": query_text, "timestamp": None}
        )

        # Execute query
        result = await self._execute_query_async(orchestrator, query_text)

        self._send_event({"type": "execution_complete", "result": result})

        return {"success": True, "result": result}

    async def _handle_multi_agent_query(
        self, query_text: str, models: List[str]
    ) -> Dict[str, Any]:
        """Handle multi-agent query with specified models."""
        from massgen.cli import create_agents_from_config, create_simple_config
        from massgen.orchestrator import Orchestrator
        from massgen.utils import get_backend_type_from_model

        self._send_log(f"Creating multi-agent system with models: {models}")

        # Send execution start event
        self._send_event(
            {
                "type": "execution_start",
                "query": query_text,
                "models": models,
                "timestamp": None,
            }
        )

        try:
            # Create agent configurations for each model
            agents_config = []
            for i, model in enumerate(models):
                backend_type = get_backend_type_from_model(model)
                agent_config = {
                    "agent_id": f"agent_{i+1}",
                    "backend": {
                        "type": backend_type,
                        "model": model,
                    },
                    "system_message": "You are a helpful AI assistant with expertise in various domains.",
                }
                agents_config.append(agent_config)

            # Create full config dict
            config_dict = {
                "agents": agents_config,
                "orchestrator": {
                    "max_duration": 600,
                    "consensus_threshold": 0.5,
                    "max_debate_rounds": 2,
                },
                "ui": {
                    "display_type": "simple",
                    "logging_enabled": False,
                },
            }

            # Create agents from config
            orchestrator_cfg = config_dict.get("orchestrator", {})
            agents = create_agents_from_config(config_dict, orchestrator_cfg)

            if not agents:
                raise ValueError("Failed to create agents from models")

            # Create orchestrator
            orchestrator = Orchestrator(agents=agents)

            # Send agent update events
            for model in models:
                self._send_event(
                    {
                        "type": "agent_update",
                        "agent": model,
                        "status": "working",
                        "message": "Starting...",
                    }
                )

            # Execute query using orchestrator's chat_simple
            full_response = ""
            async for chunk in orchestrator.chat_simple(query_text):
                if chunk.type == "content":
                    self._send_event(
                        {
                            "type": "stream_chunk",
                            "content": chunk.content,
                            "source": chunk.source,  # Include source to identify which agent is speaking
                        }
                    )
                    full_response += chunk.content
                elif chunk.type == "error":
                    raise Exception(chunk.error)

            # Mark all agents as complete
            for model in models:
                self._send_event(
                    {
                        "type": "agent_update",
                        "agent": model,
                        "status": "complete",
                        "message": "Completed",
                    }
                )

            self._send_event({"type": "execution_complete", "result": full_response})

            return {"success": True, "result": full_response}

        except Exception as e:
            logger.error(f"Multi-agent execution error: {e}")
            logger.error(traceback.format_exc())
            # Mark all agents as error
            for model in models:
                self._send_event(
                    {
                        "type": "agent_update",
                        "agent": model,
                        "status": "error",
                        "message": str(e),
                    }
                )
            raise

    async def _execute_query_async(
        self, orchestrator: "Orchestrator", query: str
    ) -> str:
        """Execute query asynchronously."""
        try:
            # Use chat_simple which returns an async generator
            full_response = ""

            async for chunk in orchestrator.chat_simple(query):
                # Send streaming events to VSCode
                if chunk.type == "content":
                    self._send_event({
                        "type": "stream_chunk",
                        "content": chunk.content,
                    })
                    full_response += chunk.content
                elif chunk.type == "error":
                    self._send_event({
                        "type": "error",
                        "message": chunk.error,
                    })
                    raise Exception(chunk.error)

            return full_response

        except Exception as e:
            logger.error(f"Orchestrator execution error: {e}")
            raise

    async def _handle_configure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle configuration request."""
        config_data = params.get("config")
        save_path = params.get("save_path")

        if save_path:
            # Save configuration to file
            config_file = Path(save_path)
            config_file.parent.mkdir(parents=True, exist_ok=True)

            import yaml

            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

            return {"success": True, "message": f"Configuration saved to {save_path}"}

        return {"success": True, "config": config_data}

    async def _handle_analyze(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle code analysis request."""
        code = params.get("code", "")
        language = params.get("language", "python")

        if not code:
            raise ValueError("Code is required for analysis")

        # Create analysis query
        query = f"Analyze this {language} code:\n\n```{language}\n{code}\n```"

        # Execute as a query
        return await self._handle_query({"text": query, "config": None})

    async def _handle_list_configs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available configuration files."""
        try:
            from importlib.resources import files

            configs_root = files("massgen") / "configs"
            config_files = []

            # Find all YAML config files
            for config_file in configs_root.rglob("*.yaml"):
                relative_path = config_file.relative_to(configs_root)
                config_files.append(
                    {
                        "name": config_file.name,
                        "path": str(relative_path),
                        "full_path": str(config_file),
                    }
                )

            return {"success": True, "configs": config_files}

        except Exception as e:
            logger.error(f"Error listing configs: {e}")
            return {"success": False, "error": str(e), "configs": []}

    def _load_config(self, config_path: str) -> "AgentConfig":
        """Load configuration from file."""
        import yaml

        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_file) as f:
            config_data = yaml.safe_load(f)

        from massgen.agent_config import AgentConfig

        return AgentConfig.from_dict(config_data)

    def _get_default_config(self) -> "AgentConfig":
        """Get default single-agent configuration."""
        from massgen.agent_config import AgentConfig

        # Return a simple default config using backend_params
        return AgentConfig(
            backend_params={
                "backend": "openai",
                "model": "gpt-4o-mini",
            },
            agent_id="vscode-default-agent",
        )

    def _send_response(self, response: Dict[str, Any]):
        """Send JSON-RPC response to stdout."""
        try:
            response_str = json.dumps(response)
            sys.stdout.write(response_str + "\n")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Error sending response: {e}")

    def _send_error(self, req_id: Optional[int], code: int, message: str):
        """Send JSON-RPC error response."""
        error_response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
        self._send_response(error_response)

    def _send_event(self, event: Dict[str, Any]):
        """Send event notification to VSCode (not a response)."""
        notification = {"jsonrpc": "2.0", "method": "event", "params": event}
        try:
            event_str = json.dumps(notification)
            sys.stdout.write(event_str + "\n")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Error sending event: {e}")

    def _send_log(self, message: str, level: str = "info"):
        """Send log message to VSCode."""
        self._send_event({"type": "log", "level": level, "message": message})


async def main():
    """Main entry point for VSCode adapter server."""
    # Set up logging to stderr (stdout is used for JSON-RPC)
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")

    server = VSCodeServer()
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
