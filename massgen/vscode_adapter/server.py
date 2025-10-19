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

    async def _handle_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle query request from VSCode."""
        from massgen.agent_config import AgentConfig
        from massgen.orchestrator import Orchestrator

        query_text = params.get("text", "")
        config_path = params.get("config")

        if not query_text:
            raise ValueError("Query text is required")

        self._send_log(f"Processing query: {query_text[:50]}...")

        try:
            # Load configuration
            if config_path:
                config = self._load_config(config_path)
            else:
                # Use default single agent config
                config = self._get_default_config()

            # Create orchestrator
            orchestrator = Orchestrator(config)

            # Register event listener to stream events to VSCode
            def event_listener(event):
                self._send_event(event)

            # Hook into orchestrator events (we'll need to modify orchestrator)
            # For now, just execute the query
            self._send_event(
                {"type": "execution_start", "query": query_text, "timestamp": None}
            )

            # Execute query (simplified version)
            # In real implementation, we need async streaming support
            result = await self._execute_query_async(orchestrator, query_text)

            self._send_event({"type": "execution_complete", "result": result})

            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"Query execution error: {e}")
            self._send_event({"type": "error", "message": str(e)})
            raise

    async def _execute_query_async(
        self, orchestrator: "Orchestrator", query: str
    ) -> str:
        """Execute query asynchronously (placeholder)."""
        # This is a simplified version
        # Real implementation needs to integrate with orchestrator's async methods
        return "Query executed successfully (placeholder)"

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

        # Return a simple default config
        # This should be customizable
        return AgentConfig.from_dict(
            {
                "agent": {
                    "id": "default-agent",
                    "backend": {"type": "openai", "model": "gpt-4o-mini"},
                }
            }
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
