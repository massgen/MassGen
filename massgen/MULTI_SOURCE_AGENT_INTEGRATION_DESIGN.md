# Multi-Source Agent Integration Design for MassGen

## Overview

This document outlines the design for extending MassGen to support agents from multiple sources and frameworks, inspired by Claude's subagent system. The goal is to enable MassGen to orchestrate not only native agents but also agents built on various frameworks (LangChain, AutoGen, AG2, LangGraph, OpenAI Assistants, SmolAgent) and agents running locally or in the cloud.

## Design Principles

### 1. Framework Agnostic Integration
- Support agents from any framework through a unified adapter interface
- Preserve framework-specific capabilities while maintaining MassGen coordination
- Enable parallel execution across heterogeneous agent types

### 2. Minimal Overhead
- Lightweight adapters that don't duplicate framework functionality
- Direct communication with framework agents when possible
- Preserve streaming and async capabilities

### 3. Orchestrator Compatibility
- Framework agents participate in MassGen's voting and new_answer workflow
- Leverage existing ConfigurableAgent for orchestrator integration
- Maintain binary decision framework for coordination

## Architecture

### Agent Adapter Interface

```python
class FrameworkAgentAdapter(ChatAgent):
    """
    Base adapter for integrating framework-specific agents into MassGen.
    Translates between MassGen's ChatAgent interface and framework-specific APIs.
    """
    
    async def chat(self, messages, tools=None, **kwargs) -> AsyncGenerator[StreamChunk, None]:
        # Translate MassGen messages to framework format
        # Execute framework agent
        # Stream responses back in MassGen format
        pass
```

### Framework-Specific Adapters

#### LangChain Adapter
```python
class LangChainAgentAdapter(FrameworkAgentAdapter):
    def __init__(self, chain_or_agent, agent_id=None):
        self.langchain_agent = chain_or_agent
        # Configure tools, memory, callbacks etc.
```

#### AutoGen/AG2 Adapter
```python
class AutoGenAgentAdapter(FrameworkAgentAdapter):
    def __init__(self, autogen_config, agent_id=None):
        self.autogen_assistant = AssistantAgent(config=autogen_config)
        # Handle conversation patterns, code execution
```

#### OpenAI Assistants Adapter
```python
class OpenAIAssistantAdapter(FrameworkAgentAdapter):
    def __init__(self, assistant_id, agent_id=None):
        self.assistant = client.beta.assistants.retrieve(assistant_id)
        self.thread = client.beta.threads.create()
        # Manage thread-based conversations
```

#### SmolAgent Adapter
```python
class SmolAgentAdapter(FrameworkAgentAdapter):
    def __init__(self, smol_agent, agent_id=None):
        self.agent = smol_agent
        # Handle SmolAgent's tool calling patterns
```

### Cloud Agent Integration

For agents running remotely (cloud services, microservices):

```python
class RemoteAgentAdapter(FrameworkAgentAdapter):
    def __init__(self, endpoint_url, auth_config=None, agent_id=None):
        self.endpoint = endpoint_url
        self.auth = auth_config
        # HTTP/WebSocket communication with remote agent
```

### Local Process Agents

For agents running as separate processes:

```python
class ProcessAgentAdapter(FrameworkAgentAdapter):
    def __init__(self, command, working_dir=None, agent_id=None):
        self.command = command
        self.process = None
        # Manage subprocess lifecycle and IPC
```

## Orchestrator Integration

### Making Framework Agents MassGen-Compatible

Framework agents are wrapped with ConfigurableAgent to enable participation in MassGen's coordination workflow:

```python
# Example: Wrapping a LangChain agent for orchestration
langchain_adapter = LangChainAgentAdapter(langchain_agent)
configurable_agent = ConfigurableAgent(
    backend=langchain_adapter,
    agent_id="langchain_expert",
    config=AgentConfig(
        message_templates=MessageTemplates()  # Provides vote/new_answer tools
    )
)
```

This allows framework agents to:
1. Receive evaluation contexts with other agents' answers
2. Vote on best approaches (Case 2)
3. Provide new answers when needed (Case 1)
4. Participate in the binary decision framework

### Parallel Execution

The orchestrator handles framework agents identically to native agents:

```python
orchestrator = Orchestrator(
    agents={
        "native_agent": SingleAgent(backend=OpenAIBackend()),
        "langchain_agent": ConfigurableAgent(backend=LangChainAdapter(...)),
        "autogen_agent": ConfigurableAgent(backend=AutoGenAdapter(...)),
        "cloud_agent": ConfigurableAgent(backend=RemoteAgentAdapter(...))
    }
)
```

All agents execute in parallel during coordination rounds, regardless of their implementation framework.

## Communication Protocol

### Message Translation

Framework adapters translate between MassGen's message format and framework-specific formats:

```python
# MassGen format
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tool_calls": [...]}
]

# Adapter translates to framework format (e.g., LangChain)
langchain_messages = [
    SystemMessage(content="..."),
    HumanMessage(content="..."),
    AIMessage(content="...", tool_calls=[...])
]
```

### Tool Integration

Framework agents can use their native tools while also supporting MassGen workflow tools:

```python
class FrameworkAgentAdapter:
    def merge_tools(self, framework_tools, massgen_tools):
        # Combine framework-specific tools with vote/new_answer
        # Translate tool schemas between formats
        return unified_tools
```

## Configuration System

### YAML Configuration Schema

```yaml
agents:
  - id: "agent_id"
    type: "framework"  # New field for framework agents
    framework: "langchain|autogen|ag2|langgraph|openai_assistant|smolagent"
    
    # Framework-specific configuration
    framework_config:
      # Varies by framework
      
    # Optional: Override with MassGen configuration
    massgen_config:
      message_templates: ...
      timeout_config: ...
```

### Dynamic Agent Loading

```python
def load_framework_agent(config):
    framework = config.get("framework")
    
    if framework == "langchain":
        return LangChainAgentAdapter(**config["framework_config"])
    elif framework == "autogen":
        return AutoGenAgentAdapter(**config["framework_config"])
    # ... other frameworks
    
    # Wrap with ConfigurableAgent for orchestration
    return ConfigurableAgent(
        backend=adapter,
        config=config.get("massgen_config", AgentConfig())
    )
```

## Detailed Implementation

### Base Framework Adapter

```python
# massgen/adapters/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio
import json
from dataclasses import dataclass

from ..backend.base import LLMBackend, StreamChunk
from ..chat_agent import ChatAgent

@dataclass
class FrameworkConfig:
    """Configuration for framework-specific settings."""
    framework_name: str
    connection_params: Dict[str, Any]
    tool_mapping: Dict[str, str] = None  # Map MassGen tools to framework tools
    message_format: str = "openai"  # openai, langchain, autogen, etc.
    supports_streaming: bool = True
    supports_async: bool = True
    retry_config: Dict[str, Any] = None

class FrameworkAgentAdapter(LLMBackend):
    """
    Base adapter for integrating framework-specific agents into MassGen.
    Implements LLMBackend interface to work with ConfigurableAgent.
    """
    
    def __init__(self, config: FrameworkConfig):
        self.config = config
        self.message_converter = MessageConverter(config.message_format)
        self.tool_converter = ToolConverter(config.tool_mapping)
        self._session_state = {}
        
    @abstractmethod
    async def _execute_framework_agent(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Any, None]:
        """Execute the framework-specific agent logic."""
        pass
    
    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Main entry point for MassGen integration.
        Translates messages, executes framework agent, and streams responses.
        """
        # Convert messages to framework format
        framework_messages = self.message_converter.to_framework(messages)
        
        # Merge MassGen workflow tools with framework tools
        if tools:
            framework_tools = self.tool_converter.merge_tools(
                tools, 
                self._get_framework_native_tools()
            )
        else:
            framework_tools = self._get_framework_native_tools()
        
        # Execute framework agent
        try:
            async for chunk in self._execute_framework_agent(
                framework_messages,
                framework_tools,
                agent_id=agent_id,
                session_id=session_id,
                **kwargs
            ):
                # Convert framework response to StreamChunk
                yield self._convert_to_stream_chunk(chunk, agent_id)
                
        except Exception as e:
            # Handle framework-specific errors
            yield self._create_error_chunk(str(e), agent_id)
    
    def _convert_to_stream_chunk(self, framework_chunk: Any, agent_id: str) -> StreamChunk:
        """Convert framework-specific chunk to MassGen StreamChunk."""
        if isinstance(framework_chunk, dict):
            return StreamChunk(
                content=framework_chunk.get("content", ""),
                chunk_type=framework_chunk.get("type", "content"),
                agent_id=agent_id,
                metadata=framework_chunk.get("metadata", {})
            )
        elif isinstance(framework_chunk, str):
            return StreamChunk(
                content=framework_chunk,
                chunk_type="content",
                agent_id=agent_id
            )
        else:
            # Handle other chunk types
            return StreamChunk(
                content=str(framework_chunk),
                chunk_type="content",
                agent_id=agent_id
            )
    
    def _get_framework_native_tools(self) -> List[Dict]:
        """Get native tools available in the framework."""
        return []
    
    def is_stateful(self) -> bool:
        """Check if the backend maintains conversation state."""
        return True  # Most frameworks maintain state
    
    async def reset_state(self) -> None:
        """Reset the framework agent's state."""
        self._session_state.clear()
```

### LangChain Adapter Implementation

```python
# massgen/adapters/langchain_adapter.py
from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio
from langchain.agents import AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain.schema import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain.tools import BaseTool
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

class LangChainAgentAdapter(FrameworkAgentAdapter):
    """Adapter for LangChain agents and chains."""
    
    def __init__(
        self, 
        agent_or_chain: Any,
        memory: Optional[Any] = None,
        tools: Optional[List[BaseTool]] = None,
        config: Optional[FrameworkConfig] = None
    ):
        if config is None:
            config = FrameworkConfig(
                framework_name="langchain",
                connection_params={},
                message_format="langchain",
                supports_streaming=True
            )
        super().__init__(config)
        
        self.agent = agent_or_chain
        self.memory = memory or ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        self.tools = tools or []
        self.streaming_handler = StreamingStdOutCallbackHandler()
        
    async def _execute_framework_agent(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """Execute LangChain agent with streaming support."""
        
        # Convert messages to LangChain format
        langchain_messages = self._convert_messages(messages)
        
        # Add tools if provided
        if tools:
            self._update_agent_tools(tools)
        
        # Create streaming callback
        stream_queue = asyncio.Queue()
        
        async def stream_callback(token: str):
            await stream_queue.put({
                "content": token,
                "type": "content"
            })
        
        # Execute agent asynchronously
        if isinstance(self.agent, AgentExecutor):
            # For agent executors
            response_task = asyncio.create_task(
                self._run_agent_executor(
                    langchain_messages[-1].content if langchain_messages else "",
                    stream_callback
                )
            )
        else:
            # For chains
            response_task = asyncio.create_task(
                self._run_chain(
                    langchain_messages,
                    stream_callback
                )
            )
        
        # Stream tokens as they arrive
        while True:
            try:
                chunk = await asyncio.wait_for(stream_queue.get(), timeout=0.1)
                yield chunk
            except asyncio.TimeoutError:
                if response_task.done():
                    break
                continue
        
        # Get final result
        result = await response_task
        
        # Handle tool calls if present
        if "tool_calls" in result:
            yield {
                "content": "",
                "type": "tool_calls",
                "metadata": {"tool_calls": result["tool_calls"]}
            }
    
    def _convert_messages(self, messages: List[Dict]) -> List[BaseMessage]:
        """Convert MassGen messages to LangChain messages."""
        langchain_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            elif role == "tool":
                # Handle tool messages
                langchain_messages.append(
                    HumanMessage(
                        content=f"Tool Result: {content}",
                        additional_kwargs={"tool_call_id": msg.get("tool_call_id")}
                    )
                )
        
        return langchain_messages
    
    async def _run_agent_executor(
        self, 
        input_text: str, 
        stream_callback: Any
    ) -> Dict:
        """Run AgentExecutor with streaming."""
        def sync_callback(token):
            asyncio.create_task(stream_callback(token))
        
        # Configure callbacks
        callbacks = [type('StreamCallback', (), {
            'on_llm_new_token': lambda token, **kwargs: sync_callback(token)
        })()]
        
        # Run agent
        result = await asyncio.to_thread(
            self.agent.arun,
            input_text,
            callbacks=callbacks
        )
        
        return {"content": result, "type": "final"}
    
    async def _run_chain(
        self,
        messages: List[BaseMessage],
        stream_callback: Any
    ) -> Dict:
        """Run a LangChain chain with streaming."""
        # Update memory with messages
        for msg in messages[:-1]:  # Add all but last message to memory
            self.memory.chat_memory.add_message(msg)
        
        # Run chain with last message
        result = await asyncio.to_thread(
            self.agent.arun,
            messages[-1].content if messages else ""
        )
        
        return {"content": result, "type": "final"}
```

### AutoGen/AG2 Adapter Implementation

```python
# massgen/adapters/autogen_adapter.py
from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio
from autogen import AssistantAgent, UserProxyAgent, ConversableAgent
from autogen.code_utils import extract_code

class AutoGenAgentAdapter(FrameworkAgentAdapter):
    """Adapter for AutoGen/AG2 agents."""
    
    def __init__(
        self,
        agent_config: Dict[str, Any],
        code_execution_config: Optional[Dict] = None,
        human_input_mode: str = "NEVER",
        max_consecutive_auto_reply: int = 10,
        config: Optional[FrameworkConfig] = None
    ):
        if config is None:
            config = FrameworkConfig(
                framework_name="autogen",
                connection_params=agent_config,
                supports_streaming=False  # AutoGen doesn't natively support streaming
            )
        super().__init__(config)
        
        # Create AutoGen assistant
        self.assistant = AssistantAgent(
            name=agent_config.get("name", "assistant"),
            llm_config=agent_config.get("llm_config"),
            system_message=agent_config.get("system_message", ""),
            max_consecutive_auto_reply=max_consecutive_auto_reply,
            human_input_mode=human_input_mode
        )
        
        # Create user proxy for execution
        self.user_proxy = UserProxyAgent(
            name="user_proxy",
            code_execution_config=code_execution_config or {"use_docker": False},
            human_input_mode="NEVER",
            max_consecutive_auto_reply=0
        )
        
        self.conversation_history = []
        
    async def _execute_framework_agent(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """Execute AutoGen agent."""
        
        # Process conversation history
        for msg in messages:
            if msg["role"] == "user":
                user_message = msg["content"]
                break
        else:
            user_message = "Continue the conversation"
        
        # Register tools as functions if provided
        if tools:
            self._register_tools_as_functions(tools)
        
        # Create message queue for pseudo-streaming
        response_parts = []
        
        # Execute in thread pool since AutoGen is sync
        def run_autogen():
            # Initiate chat
            self.user_proxy.initiate_chat(
                self.assistant,
                message=user_message,
                clear_history=False
            )
            
            # Get response from conversation
            last_message = self.assistant.last_message()
            return last_message["content"]
        
        # Run AutoGen in thread
        response = await asyncio.to_thread(run_autogen)
        
        # Parse response for code blocks
        code_blocks = extract_code(response)
        
        # Stream response in chunks
        if code_blocks:
            # First yield the text before code
            text_parts = response.split("```")
            if text_parts[0]:
                yield {
                    "content": text_parts[0],
                    "type": "content"
                }
            
            # Yield code blocks
            for code in code_blocks:
                yield {
                    "content": f"```{code[0]}\n{code[1]}\n```",
                    "type": "code",
                    "metadata": {"language": code[0]}
                }
            
            # Yield remaining text
            if len(text_parts) > 2:
                yield {
                    "content": text_parts[-1],
                    "type": "content"
                }
        else:
            # Stream response in smaller chunks for better UX
            chunk_size = 50
            for i in range(0, len(response), chunk_size):
                yield {
                    "content": response[i:i+chunk_size],
                    "type": "content"
                }
                await asyncio.sleep(0.01)  # Small delay for streaming effect
    
    def _register_tools_as_functions(self, tools: List[Dict]):
        """Register MassGen tools as AutoGen functions."""
        for tool in tools:
            if tool.get("function"):
                func_schema = tool["function"]
                
                # Create a wrapper function
                async def tool_wrapper(**kwargs):
                    # Call the actual tool
                    return await self._execute_tool(func_schema["name"], kwargs)
                
                # Register with assistant
                self.assistant.register_function(
                    function_map={
                        func_schema["name"]: tool_wrapper
                    }
                )
```

### Black Box Agent Support

MassGen supports integrating any pre-existing agent as a "black box" without requiring knowledge of its internal implementation. This allows you to:
- Use agents written in any language (Python, JavaScript, Go, etc.)
- Integrate proprietary or closed-source agents
- Connect to agents running as microservices
- Use agents with complex dependencies without installing them locally

#### Black Box Agent Interface

```python
# massgen/adapters/blackbox.py
from typing import Protocol, Dict, List, Any, Optional, AsyncGenerator
import subprocess
import asyncio
import json
from abc import ABC, abstractmethod

class BlackBoxAgentProtocol(Protocol):
    """Minimal interface that any black box agent must implement."""
    
    async def chat(self, messages: List[Dict], **kwargs) -> AsyncGenerator[Dict, None]:
        """Send messages and receive streaming response."""
        ...
    
    async def health_check(self) -> bool:
        """Check if agent is responsive."""
        ...

class BlackBoxAdapter(FrameworkAgentAdapter):
    """
    Universal adapter for black box agents.
    Requires only a communication protocol, not framework knowledge.
    """
    
    def __init__(
        self,
        communication_method: str,  # "http", "websocket", "pipe", "file", "grpc"
        connection_config: Dict[str, Any],
        protocol_version: str = "1.0",
        config: Optional[FrameworkConfig] = None
    ):
        if config is None:
            config = FrameworkConfig(
                framework_name="blackbox",
                connection_params=connection_config,
                supports_streaming=True
            )
        super().__init__(config)
        
        self.communication_method = communication_method
        self.connection_config = connection_config
        self.protocol_version = protocol_version
        
        # Initialize appropriate communicator
        self.communicator = self._create_communicator()
    
    def _create_communicator(self):
        """Create appropriate communicator based on method."""
        if self.communication_method == "http":
            return HTTPCommunicator(self.connection_config)
        elif self.communication_method == "pipe":
            return PipeCommunicator(self.connection_config)
        elif self.communication_method == "file":
            return FileCommunicator(self.connection_config)
        elif self.communication_method == "grpc":
            return GRPCCommunicator(self.connection_config)
        else:
            raise ValueError(f"Unknown communication method: {self.communication_method}")
    
    async def _execute_framework_agent(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """Execute black box agent through standardized protocol."""
        
        # Prepare standardized request
        request = {
            "version": self.protocol_version,
            "messages": messages,
            "tools": tools,
            "options": kwargs
        }
        
        # Send request and stream response
        async for response in self.communicator.exchange(request):
            yield response
```

#### Communication Methods

##### 1. HTTP/REST Black Box Agent

```python
# massgen/adapters/blackbox/http_communicator.py
class HTTPCommunicator:
    """Communicate with black box agents via HTTP."""
    
    def __init__(self, config: Dict[str, Any]):
        self.endpoint = config["endpoint"]
        self.headers = config.get("headers", {})
        self.timeout = config.get("timeout", 300)
        
    async def exchange(self, request: Dict) -> AsyncGenerator[Dict, None]:
        """Send request via HTTP and stream response."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint,
                json=request,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                # Handle streaming or non-streaming response
                if "stream" in response.headers.get("content-type", ""):
                    async for line in response.content:
                        if line:
                            yield json.loads(line.decode())
                else:
                    result = await response.json()
                    yield result
```

##### 2. Local Process Black Box Agent

```python
# massgen/adapters/blackbox/pipe_communicator.py
class PipeCommunicator:
    """Communicate with black box agents via stdin/stdout pipes."""
    
    def __init__(self, config: Dict[str, Any]):
        self.command = config["command"]  # e.g., ["python", "my_agent.py"]
        self.working_dir = config.get("working_dir", ".")
        self.env = config.get("env", {})
        self.process = None
        
    async def exchange(self, request: Dict) -> AsyncGenerator[Dict, None]:
        """Send request via pipe and stream response."""
        if not self.process:
            await self._start_process()
        
        # Send request as JSON line
        request_line = json.dumps(request) + "\n"
        self.process.stdin.write(request_line.encode())
        await self.process.stdin.drain()
        
        # Read streaming response
        while True:
            line = await self.process.stdout.readline()
            if not line:
                break
            
            response = json.loads(line.decode())
            if response.get("type") == "end":
                break
            
            yield response
    
    async def _start_process(self):
        """Start the black box agent process."""
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
            env={**os.environ, **self.env}
        )
```

##### 3. File-Based Black Box Agent

```python
# massgen/adapters/blackbox/file_communicator.py
class FileCommunicator:
    """Communicate with black box agents via file system."""
    
    def __init__(self, config: Dict[str, Any]):
        self.input_file = config["input_file"]
        self.output_file = config["output_file"]
        self.trigger_command = config.get("trigger_command")  # Optional command to trigger processing
        self.polling_interval = config.get("polling_interval", 0.1)
        
    async def exchange(self, request: Dict) -> AsyncGenerator[Dict, None]:
        """Send request via file and read response."""
        # Write request to input file
        with open(self.input_file, 'w') as f:
            json.dump(request, f)
        
        # Trigger processing if command provided
        if self.trigger_command:
            await asyncio.create_subprocess_shell(self.trigger_command)
        
        # Poll output file for response
        output_path = Path(self.output_file)
        while not output_path.exists():
            await asyncio.sleep(self.polling_interval)
        
        # Read streaming response from file
        with open(self.output_file, 'r') as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)
        
        # Clean up
        output_path.unlink()
```

#### Black Box Agent Wrapper Scripts

For non-Python agents, provide wrapper scripts that implement the protocol:

##### Node.js Wrapper Example

```javascript
// blackbox_wrapper.js
const readline = require('readline');
const { MyCustomAgent } = require('./my_agent');

const agent = new MyCustomAgent();
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

rl.on('line', async (line) => {
    const request = JSON.parse(line);
    
    // Call your agent
    const response = await agent.chat(request.messages);
    
    // Stream response
    for (const chunk of response) {
        console.log(JSON.stringify({
            type: 'content',
            content: chunk
        }));
    }
    
    // Signal completion
    console.log(JSON.stringify({ type: 'end' }));
});
```

##### Python Wrapper Example

```python
# blackbox_wrapper.py
import sys
import json
from my_custom_agent import MyAgent  # Your existing agent

agent = MyAgent()

while True:
    line = sys.stdin.readline()
    if not line:
        break
    
    request = json.loads(line)
    
    # Call your agent
    response = agent.process(request['messages'])
    
    # Stream response
    for chunk in response:
        print(json.dumps({
            'type': 'content',
            'content': chunk
        }))
        sys.stdout.flush()
    
    # Signal completion
    print(json.dumps({'type': 'end'}))
    sys.stdout.flush()
```

### Remote/Cloud Agent Adapter

```python
# massgen/adapters/remote_adapter.py
import aiohttp
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
import json
from urllib.parse import urljoin

class RemoteAgentAdapter(FrameworkAgentAdapter):
    """Adapter for agents running as remote services."""
    
    def __init__(
        self,
        endpoint_url: str,
        auth_config: Optional[Dict] = None,
        protocol: str = "http",  # http, websocket
        timeout: int = 300,
        retry_config: Optional[Dict] = None,
        config: Optional[FrameworkConfig] = None
    ):
        if config is None:
            config = FrameworkConfig(
                framework_name="remote",
                connection_params={"endpoint": endpoint_url},
                supports_streaming=protocol == "websocket",
                retry_config=retry_config or {"max_retries": 3, "backoff": 2}
            )
        super().__init__(config)
        
        self.endpoint_url = endpoint_url
        self.auth_config = auth_config or {}
        self.protocol = protocol
        self.timeout = timeout
        self.session = None
        
    async def _ensure_session(self):
        """Ensure HTTP session exists."""
        if self.session is None:
            timeout_config = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout_config,
                headers=self._get_auth_headers()
            )
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Build authentication headers."""
        headers = {"Content-Type": "application/json"}
        
        if self.auth_config.get("api_key"):
            headers["Authorization"] = f"Bearer {self.auth_config['api_key']}"
        elif self.auth_config.get("custom_headers"):
            headers.update(self.auth_config["custom_headers"])
        
        return headers
    
    async def _execute_framework_agent(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """Execute remote agent via HTTP or WebSocket."""
        
        if self.protocol == "websocket":
            async for chunk in self._execute_websocket(messages, tools, **kwargs):
                yield chunk
        else:
            async for chunk in self._execute_http(messages, tools, **kwargs):
                yield chunk
    
    async def _execute_http(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """Execute via HTTP with SSE streaming support."""
        await self._ensure_session()
        
        payload = {
            "messages": messages,
            "tools": tools,
            "stream": True,
            **kwargs
        }
        
        # Retry logic
        retries = 0
        max_retries = self.config.retry_config.get("max_retries", 3)
        
        while retries < max_retries:
            try:
                async with self.session.post(
                    urljoin(self.endpoint_url, "/chat"),
                    json=payload
                ) as response:
                    if response.status != 200:
                        raise Exception(f"Remote agent error: {response.status}")
                    
                    # Handle Server-Sent Events (SSE) streaming
                    if response.headers.get("Content-Type", "").startswith("text/event-stream"):
                        async for line in response.content:
                            line = line.decode("utf-8").strip()
                            if line.startswith("data: "):
                                data = line[6:]  # Remove "data: " prefix
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    yield chunk
                                except json.JSONDecodeError:
                                    continue
                    else:
                        # Non-streaming response
                        result = await response.json()
                        yield {
                            "content": result.get("response", ""),
                            "type": "final",
                            "metadata": result.get("metadata", {})
                        }
                    break
                    
            except asyncio.TimeoutError:
                retries += 1
                if retries >= max_retries:
                    yield {
                        "content": "Remote agent timeout",
                        "type": "error"
                    }
                await asyncio.sleep(self.config.retry_config.get("backoff", 2) ** retries)
            except Exception as e:
                retries += 1
                if retries >= max_retries:
                    yield {
                        "content": f"Remote agent error: {str(e)}",
                        "type": "error"
                    }
                await asyncio.sleep(self.config.retry_config.get("backoff", 2) ** retries)
    
    async def _execute_websocket(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """Execute via WebSocket for real-time streaming."""
        import aiohttp
        
        ws_url = self.endpoint_url.replace("http://", "ws://").replace("https://", "wss://")
        
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                ws_url,
                headers=self._get_auth_headers()
            ) as ws:
                # Send request
                await ws.send_json({
                    "messages": messages,
                    "tools": tools,
                    **kwargs
                })
                
                # Receive streaming response
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "done":
                            break
                        yield data
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        yield {
                            "content": f"WebSocket error: {ws.exception()}",
                            "type": "error"
                        }
                        break
    
    async def cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()
```

### Message and Tool Converters

```python
# massgen/adapters/converters.py
from typing import List, Dict, Any, Optional
import json

class MessageConverter:
    """Convert messages between MassGen and framework formats."""
    
    def __init__(self, target_format: str = "openai"):
        self.target_format = target_format
        self.converters = {
            "openai": self._to_openai,
            "langchain": self._to_langchain,
            "autogen": self._to_autogen,
            "custom": self._to_custom
        }
    
    def to_framework(self, messages: List[Dict]) -> Any:
        """Convert MassGen messages to framework format."""
        converter = self.converters.get(self.target_format, self._to_openai)
        return converter(messages)
    
    def from_framework(self, framework_response: Any) -> Dict:
        """Convert framework response to MassGen format."""
        if self.target_format == "langchain":
            return self._from_langchain(framework_response)
        elif self.target_format == "autogen":
            return self._from_autogen(framework_response)
        else:
            return self._from_openai(framework_response)
    
    def _to_openai(self, messages: List[Dict]) -> List[Dict]:
        """Already in OpenAI format."""
        return messages
    
    def _to_langchain(self, messages: List[Dict]) -> List:
        """Convert to LangChain message objects."""
        # This would import and create actual LangChain message objects
        # Simplified for illustration
        return [
            {"type": msg["role"], "content": msg["content"]}
            for msg in messages
        ]
    
    def _to_autogen(self, messages: List[Dict]) -> List[Dict]:
        """Convert to AutoGen format."""
        autogen_messages = []
        for msg in messages:
            if msg["role"] == "system":
                # AutoGen uses system message differently
                continue
            autogen_messages.append({
                "role": msg["role"],
                "content": msg["content"],
                "name": msg.get("name", msg["role"])
            })
        return autogen_messages
    
    def _to_custom(self, messages: List[Dict]) -> Any:
        """Custom format conversion."""
        # Implement custom conversion logic
        return messages

class ToolConverter:
    """Convert and merge tools between MassGen and frameworks."""
    
    def __init__(self, tool_mapping: Optional[Dict[str, str]] = None):
        self.tool_mapping = tool_mapping or {}
    
    def merge_tools(
        self, 
        massgen_tools: List[Dict],
        framework_tools: List[Dict]
    ) -> List[Dict]:
        """Merge MassGen workflow tools with framework native tools."""
        merged = []
        
        # Add MassGen tools (vote, new_answer)
        for tool in massgen_tools:
            if self._is_workflow_tool(tool):
                merged.append(self._convert_workflow_tool(tool))
            else:
                merged.append(tool)
        
        # Add framework native tools
        for tool in framework_tools:
            if not self._is_duplicate(tool, merged):
                merged.append(tool)
        
        return merged
    
    def _is_workflow_tool(self, tool: Dict) -> bool:
        """Check if tool is a MassGen workflow tool."""
        name = tool.get("function", {}).get("name", "")
        return name in ["vote", "new_answer"]
    
    def _convert_workflow_tool(self, tool: Dict) -> Dict:
        """Convert MassGen workflow tool for framework."""
        # Keep workflow tools as-is for framework to handle
        return tool
    
    def _is_duplicate(self, tool: Dict, existing: List[Dict]) -> bool:
        """Check if tool already exists."""
        tool_name = tool.get("function", {}).get("name", "")
        for existing_tool in existing:
            if existing_tool.get("function", {}).get("name", "") == tool_name:
                return True
        return False
```

### Factory and Registry

```python
# massgen/adapters/factory.py
from typing import Dict, Any, Optional, Type
from .base import FrameworkAgentAdapter
from .langchain_adapter import LangChainAgentAdapter
from .autogen_adapter import AutoGenAgentAdapter
from .remote_adapter import RemoteAgentAdapter

class FrameworkAdapterRegistry:
    """Registry for framework adapters."""
    
    _adapters: Dict[str, Type[FrameworkAgentAdapter]] = {
        # Framework-specific adapters
        "langchain": LangChainAgentAdapter,
        "autogen": AutoGenAgentAdapter,
        "ag2": AutoGenAgentAdapter,  # AG2 uses same adapter
        "langgraph": LangGraphAdapter,
        "openai_assistant": OpenAIAssistantAdapter,
        "smolagent": SmolAgentAdapter,
        
        # Black box adapters
        "blackbox": BlackBoxAdapter,
        
        # Remote adapters
        "remote": RemoteAgentAdapter,
        "cloud": RemoteAgentAdapter,
    }
    
    @classmethod
    def register(cls, name: str, adapter_class: Type[FrameworkAgentAdapter]):
        """Register a new adapter."""
        cls._adapters[name] = adapter_class
    
    @classmethod
    def create(cls, framework: str, config: Dict[str, Any]) -> FrameworkAgentAdapter:
        """Create an adapter instance."""
        adapter_class = cls._adapters.get(framework)
        if not adapter_class:
            raise ValueError(f"Unknown framework: {framework}")
        
        return adapter_class(**config)

def load_framework_agent(config: Dict[str, Any]) -> ChatAgent:
    """Load a framework agent from configuration."""
    from ..chat_agent import ConfigurableAgent
    from ..agent_config import AgentConfig
    
    framework = config.get("framework")
    framework_config = config.get("framework_config", {})
    massgen_config = config.get("massgen_config")
    
    # Create adapter
    adapter = FrameworkAdapterRegistry.create(framework, framework_config)
    
    # Wrap with ConfigurableAgent for orchestration
    agent_config = AgentConfig(**massgen_config) if massgen_config else AgentConfig()
    
    return ConfigurableAgent(
        backend=adapter,
        agent_id=config.get("id"),
        config=agent_config
    )
```

## File Structure and Organization

### Directory Layout

```
massgen/
├── adapters/                      # All framework adapter implementations
│   ├── __init__.py               # Export main adapter classes
│   ├── base.py                   # Base FrameworkAgentAdapter class
│   ├── converters.py             # MessageConverter and ToolConverter classes
│   ├── factory.py                # FrameworkAdapterRegistry and load_framework_agent
│   │
│   ├── blackbox/                 # Black box agent support
│   │   ├── __init__.py
│   │   ├── blackbox_adapter.py  # BlackBoxAdapter main class
│   │   ├── communicators.py     # All communicator implementations
│   │   ├── http_communicator.py # HTTP/REST communication
│   │   ├── pipe_communicator.py # Stdin/stdout pipe communication
│   │   ├── file_communicator.py # File-based communication
│   │   └── grpc_communicator.py # gRPC communication (optional)
│   │
│   ├── frameworks/               # Framework-specific adapters
│   │   ├── __init__.py
│   │   ├── langchain_adapter.py # LangChainAgentAdapter
│   │   ├── autogen_adapter.py   # AutoGenAgentAdapter (also for AG2)
│   │   ├── langgraph_adapter.py # LangGraphAdapter
│   │   ├── openai_assistant_adapter.py # OpenAIAssistantAdapter
│   │   └── smolagent_adapter.py # SmolAgentAdapter
│   │
│   ├── remote/                   # Remote and cloud agent adapters
│   │   ├── __init__.py
│   │   ├── remote_adapter.py    # RemoteAgentAdapter (HTTP/WebSocket)
│   │   ├── cloud_adapter.py     # CloudAgentAdapter (extends RemoteAdapter)
│   │   └── process_adapter.py   # ProcessAgentAdapter (local subprocess)
│   │
│   └── utils/                    # Adapter utilities
│       ├── __init__.py
│       ├── streaming.py          # Streaming helpers and queue management
│       ├── retry.py              # Retry logic and exponential backoff
│       ├── auth.py               # Authentication helpers
│       └── protocol.py           # Protocol definitions and validators
│
├── backend/                      # Existing backend implementations
│   ├── base.py                  # LLMBackend base class (already exists)
│   └── ...                      # Other existing backends
│
├── configs/                      # Configuration files
│   ├── examples/                # Example configurations
│   │   ├── framework_agents/    # Framework-specific examples
│   │   │   ├── langchain_team.yaml
│   │   │   ├── autogen_team.yaml
│   │   │   ├── mixed_framework_team.yaml
│   │   │   └── cloud_agents.yaml
│   │   └── ...                  # Existing examples
│   └── ...                      # Existing configs
│
└── tests/                       # Test files
    ├── adapters/                # Adapter-specific tests
    │   ├── test_base_adapter.py
    │   ├── test_langchain_adapter.py
    │   ├── test_autogen_adapter.py
    │   ├── test_remote_adapter.py
    │   ├── test_converters.py
    │   └── test_factory.py
    └── ...                      # Existing tests
```

### File Contents Specification

#### 1. Core Base Classes

**`massgen/adapters/base.py`**
```python
# Contains:
- FrameworkConfig dataclass
- FrameworkAgentAdapter abstract base class
- Common adapter utilities
```

**`massgen/adapters/converters.py`**
```python
# Contains:
- MessageConverter class
- ToolConverter class
- Format conversion utilities
```

**`massgen/adapters/factory.py`**
```python
# Contains:
- FrameworkAdapterRegistry class
- load_framework_agent() function
- Dynamic adapter registration
```

#### 2. Framework-Specific Adapters

**`massgen/adapters/frameworks/langchain_adapter.py`**
```python
# Contains:
- LangChainAgentAdapter class
- LangChain-specific message conversion
- Chain and AgentExecutor handling
```

**`massgen/adapters/frameworks/autogen_adapter.py`**
```python
# Contains:
- AutoGenAgentAdapter class
- AG2 compatibility layer
- Code execution integration
```

**`massgen/adapters/frameworks/langgraph_adapter.py`**
```python
# Contains:
- LangGraphAdapter class
- Graph-based agent workflow support
- State machine integration
```

**`massgen/adapters/frameworks/openai_assistant_adapter.py`**
```python
# Contains:
- OpenAIAssistantAdapter class
- Thread management
- Assistant API integration
```

**`massgen/adapters/frameworks/smolagent_adapter.py`**
```python
# Contains:
- SmolAgentAdapter class
- SmolAgent tool integration
- Lightweight agent support
```

#### 3. Remote Agent Adapters

**`massgen/adapters/remote/remote_adapter.py`**
```python
# Contains:
- RemoteAgentAdapter class
- HTTP/HTTPS client implementation
- WebSocket client implementation
- SSE (Server-Sent Events) handling
```

**`massgen/adapters/remote/cloud_adapter.py`**
```python
# Contains:
- CloudAgentAdapter class (extends RemoteAgentAdapter)
- Cloud provider specific authentication
- Service discovery mechanisms
```

**`massgen/adapters/remote/process_adapter.py`**
```python
# Contains:
- ProcessAgentAdapter class
- Subprocess management
- IPC (Inter-Process Communication) handling
- Local agent process lifecycle
```

#### 4. Utility Modules

**`massgen/adapters/utils/streaming.py`**
```python
# Contains:
- StreamQueue class for async streaming
- ChunkProcessor for format conversion
- StreamMerger for combining multiple streams
```

**`massgen/adapters/utils/retry.py`**
```python
# Contains:
- RetryPolicy class
- ExponentialBackoff implementation
- Circuit breaker pattern
```

**`massgen/adapters/utils/auth.py`**
```python
# Contains:
- AuthProvider interface
- OAuth2Provider class
- APIKeyProvider class
- Custom header management
```

### Integration Points

#### 1. Modify Existing Files

**`massgen/chat_agent.py`**
```python
# No changes needed - ConfigurableAgent already supports custom backends
```

**`massgen/orchestrator.py`**
```python
# Minor addition to support framework agent loading:
def _load_agents_from_config(self, config: Dict) -> Dict[str, ChatAgent]:
    """Load agents including framework agents."""
    agents = {}
    for agent_config in config.get("agents", []):
        if agent_config.get("type") == "framework":
            from .adapters.factory import load_framework_agent
            agents[agent_config["id"]] = load_framework_agent(agent_config)
        else:
            # Existing agent loading logic
            pass
    return agents
```

**`massgen/cli.py`**
```python
# Add framework agent support in configuration loading:
def load_configuration(config_path: str) -> Dict:
    """Enhanced to support framework agent configurations."""
    # Existing loading logic
    # Add validation for framework agent configs
    pass
```

**`massgen/__init__.py`**
```python
# Export new adapter classes:
from .adapters.factory import (
    FrameworkAdapterRegistry,
    load_framework_agent
)
from .adapters.base import FrameworkAgentAdapter

__all__ = [
    # ... existing exports ...
    "FrameworkAdapterRegistry",
    "load_framework_agent",
    "FrameworkAgentAdapter",
]
```

### Configuration Schema Updates

**`massgen/schemas/agent_config_schema.json`** (new file)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "definitions": {
    "frameworkAgent": {
      "type": "object",
      "required": ["id", "type", "framework", "framework_config"],
      "properties": {
        "id": {"type": "string"},
        "type": {"const": "framework"},
        "framework": {
          "enum": ["langchain", "autogen", "ag2", "langgraph", 
                   "openai_assistant", "smolagent", "remote", "cloud"]
        },
        "framework_config": {"type": "object"},
        "massgen_config": {"$ref": "#/definitions/massgenConfig"}
      }
    },
    "nativeAgent": {
      "type": "object",
      "required": ["id", "backend"],
      "properties": {
        "id": {"type": "string"},
        "backend": {"type": "object"},
        "system_message": {"type": "string"}
      }
    }
  }
}
```

### Testing Structure

**`massgen/tests/adapters/test_base_adapter.py`**
```python
# Tests for:
- FrameworkAgentAdapter abstract methods
- Message conversion pipeline
- Tool merging logic
- Streaming functionality
```

**`massgen/tests/adapters/test_langchain_adapter.py`**
```python
# Tests for:
- LangChain agent execution
- Memory management
- Tool registration
- Streaming callbacks
```

**`massgen/tests/adapters/test_factory.py`**
```python
# Tests for:
- Registry registration/lookup
- Dynamic adapter creation
- Configuration loading
- ConfigurableAgent wrapping
```

### Import Structure

The main entry points for using framework agents:

```python
# For users of the library:
from massgen import load_framework_agent, FrameworkAdapterRegistry

# For extending with custom frameworks:
from massgen.adapters.base import FrameworkAgentAdapter

# For direct adapter usage:
from massgen.adapters.frameworks import (
    LangChainAgentAdapter,
    AutoGenAgentAdapter
)
from massgen.adapters.remote import RemoteAgentAdapter
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)
**Goal**: Establish the foundation for framework-agnostic agent integration

**Tasks**:
- Create `massgen/adapters/` directory structure with all subdirectories
- Implement `base.py` with:
  - `FrameworkConfig` dataclass
  - `FrameworkAgentAdapter` abstract base class inheriting from `LLMBackend`
  - Core streaming and state management methods
- Implement `converters.py` with:
  - `MessageConverter` class for format translations
  - `ToolConverter` class for tool schema mappings
  - Support for OpenAI, LangChain, and AutoGen formats
- Create `factory.py` with:
  - `FrameworkAdapterRegistry` class
  - `load_framework_agent()` function
  - Dynamic adapter registration mechanism
- Write unit tests for core components in `tests/adapters/`
- Update `massgen/__init__.py` with new exports

**Deliverables**:
- Working adapter base infrastructure
- Message/tool conversion pipeline
- Registry pattern implementation
- 90%+ test coverage for core components

### Phase 2: Black Box Agent Support (Week 2-3)
**Goal**: Enable integration of any existing agent without framework knowledge

**Tasks**:
- Implement `blackbox/blackbox_adapter.py` with:
  - `BlackBoxAdapter` class
  - Protocol version negotiation
  - Generic request/response handling
- Create communicator implementations:
  - `pipe_communicator.py` for stdin/stdout communication
  - `http_communicator.py` for REST API communication
  - `file_communicator.py` for file-based communication
- Develop wrapper script templates:
  - Python wrapper example (`examples/wrappers/python_wrapper.py`)
  - Node.js wrapper example (`examples/wrappers/nodejs_wrapper.js`)
  - Shell script wrapper (`examples/wrappers/shell_wrapper.sh`)
- Create protocol documentation:
  - Request/response format specification
  - Error handling guidelines
  - Performance best practices
- Write integration tests with mock black box agents
- Create example configurations for common use cases

**Deliverables**:
- Complete black box agent support
- Multiple communication methods
- Wrapper script templates in 3+ languages
- Protocol specification document
- Working examples with Docker containers

### Phase 3: Popular Framework Adapters (Week 3-5)
**Goal**: Implement adapters for the most widely-used agent frameworks

**Tasks**:
- **LangChain Adapter**:
  - Implement `frameworks/langchain_adapter.py`
  - Support for chains, agents, and tools
  - Memory management integration
  - Streaming callback implementation
  - Test with ReAct and ConversationalAgent examples
- **AutoGen/AG2 Adapter**:
  - Implement `frameworks/autogen_adapter.py`
  - AssistantAgent and UserProxyAgent support
  - Code execution configuration
  - Multi-agent conversation handling
  - Test with code generation and data analysis examples
- **OpenAI Assistants Adapter**:
  - Implement `frameworks/openai_assistant_adapter.py`
  - Thread management
  - File handling and retrieval
  - Function calling support
  - Test with existing OpenAI assistants
- Create framework-specific example configurations
- Write framework-specific integration tests
- Document framework-specific limitations and workarounds

**Deliverables**:
- 3 fully functional framework adapters
- Framework-specific test suites
- Example configurations for each framework
- Performance benchmarks comparing frameworks

### Phase 4: Remote and Cloud Integration (Week 4-5)
**Goal**: Enable distributed agent architectures

**Tasks**:
- Implement `remote/remote_adapter.py` with:
  - HTTP/HTTPS client with retry logic
  - WebSocket client for real-time streaming
  - SSE (Server-Sent Events) support
  - Connection pooling and keepalive
- Add `remote/cloud_adapter.py` with:
  - AWS Lambda integration
  - Google Cloud Functions support
  - Azure Functions compatibility
  - Generic webhook support
- Implement `remote/process_adapter.py` with:
  - Local subprocess management
  - Process lifecycle control
  - Resource monitoring
  - Automatic restart on failure
- Create `utils/auth.py` with:
  - OAuth2 authentication
  - API key management
  - JWT token handling
  - Custom header injection
- Develop cloud deployment templates:
  - Terraform configurations
  - Kubernetes manifests
  - Docker Compose files
- Write stress tests for remote agents

**Deliverables**:
- Complete remote agent support
- Cloud provider integrations
- Authentication utilities
- Deployment templates and guides
- Load testing results

### Phase 5: Advanced Features and Optimization (Week 5-6)
**Goal**: Add remaining frameworks and optimize performance

**Tasks**:
- **Additional Framework Adapters**:
  - Implement `frameworks/langgraph_adapter.py`
  - Implement `frameworks/smolagent_adapter.py`
  - Add support for CrewAI (if needed)
- **Streaming and Performance**:
  - Implement `utils/streaming.py` with queue management
  - Add chunk batching and buffering
  - Implement backpressure handling
  - Add metrics collection
- **Reliability Features**:
  - Implement `utils/retry.py` with exponential backoff
  - Add circuit breaker pattern
  - Implement health checks
  - Add connection pooling
- **Orchestrator Enhancements**:
  - Update orchestrator for framework agent loading
  - Add framework-aware scheduling
  - Implement cost-based agent selection
  - Add framework-specific timeout handling
- Create comprehensive documentation:
  - Integration guide for new frameworks
  - Performance tuning guide
  - Troubleshooting guide
  - API reference documentation

**Deliverables**:
- 2+ additional framework adapters
- Performance optimization utilities
- Reliability features
- Complete documentation suite
- Performance benchmarks

### Phase 6: Testing and Documentation (Week 6-7)
**Goal**: Ensure production readiness

**Tasks**:
- **Testing**:
  - End-to-end integration tests with mixed agent teams
  - Stress testing with 10+ concurrent agents
  - Failure scenario testing
  - Performance regression tests
  - Security audit of authentication mechanisms
- **Documentation**:
  - Update README with framework integration examples
  - Create migration guide from single-framework setups
  - Write best practices guide
  - Add troubleshooting section
  - Create video tutorials
- **Examples and Templates**:
  - 10+ example configurations for different use cases
  - Project templates for common scenarios
  - Jupyter notebooks with demonstrations
  - CLI tool for generating configurations
- **Community Preparation**:
  - Create contribution guidelines for new adapters
  - Set up GitHub issue templates
  - Prepare release notes
  - Create blog post announcing the feature

**Deliverables**:
- 95%+ test coverage
- Complete documentation
- 10+ working examples
- Release-ready codebase

## Example Configurations

### Black Box Agent Configuration Examples

#### Example 1: Using a Pre-existing Local Agent

```yaml
# blackbox_local_agent.yaml
agents:
  - id: "my_existing_agent"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["python", "/path/to/my/agent.py"]
      working_dir: "/path/to/my/agent"
      env:
        MY_AGENT_CONFIG: "production"
    system_message: |
      You are integrated as a black box agent. Process requests and provide responses.

  - id: "nodejs_agent"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["node", "/path/to/agent/wrapper.js"]
      working_dir: "/path/to/agent"
    
  - id: "native_agent"
    type: "native"
    backend:
      type: "openai"
      model: "gpt-4o-mini"

orchestrator:
  timeout_config:
    orchestrator_timeout_seconds: 600

ui:
  type: "rich_terminal"
```

Run commands with specific prompts:
```bash
uv run python -m massgen.cli --config blackbox_local_agent.yaml "Convert this request to SQL: Show me all customers who made purchases over $1000 in the last month"

```

#### Example 2: Using a Cloud-based Black Box Agent

```yaml
# blackbox_cloud_agent.yaml
agents:
  - id: "proprietary_cloud_agent"
    type: "blackbox"
    communication_method: "http"
    connection_config:
      endpoint: "https://api.mycompany.com/agent/chat"
      headers:
        Authorization: "Bearer ${MY_API_KEY}"
        X-Agent-Version: "2.0"
      timeout: 300
    
  - id: "microservice_agent"
    type: "blackbox"
    communication_method: "http"
    connection_config:
      endpoint: "http://agent-service.internal:8080/process"
      headers:
        Content-Type: "application/json"
    
  - id: "analysis_agent"
    type: "native"
    backend:
      type: "claude"
      model: "claude-3-sonnet"

orchestrator:
  snapshot_storage: "blackbox_snapshots"

ui:
  type: "rich_terminal"
```

Run commands with specific prompts:
```bash
# Natural language to SQL
uv run python -m massgen.cli --config blackbox_cloud_agent.yaml "Convert this request to SQL: Show me all customers who made purchases over $1000 in the last month"
```

#### Example 3: File-based Black Box Agent

```yaml
# blackbox_file_agent.yaml
agents:
  - id: "legacy_system_agent"
    type: "blackbox"
    communication_method: "file"
    connection_config:
      input_file: "/tmp/agent_input.json"
      output_file: "/tmp/agent_output.json"
      trigger_command: "/usr/local/bin/process_agent_request"
      polling_interval: 0.5
    
  - id: "batch_processor"
    type: "blackbox"
    communication_method: "file"
    connection_config:
      input_file: "/shared/input/request.json"
      output_file: "/shared/output/response.json"
      trigger_command: "docker run --rm -v /shared:/data my-agent:latest"
```

Run commands with specific prompts:
```bash
# Batch data transformation
uv run python -m massgen.cli --config blackbox_file_agent.yaml "Transform the daily transaction logs from fixed-width format to JSON and apply business rules validation"
```

### Framework Agent Configuration Examples
### Example 1: Research Team with Mixed Frameworks

```yaml
# research_mixed_team.yaml
agents:
  - id: "web_researcher"
    type: "framework"
    framework: "langchain"
    framework_config:
      chain_type: "ReActChain"
      llm:
        provider: "openai"
        model: "gpt-4o-mini"
      tools:
        - "google_search"
        - "wikipedia"
        - "arxiv"
      memory:
        type: "conversation_buffer"
        max_tokens: 2000
    
  - id: "data_analyst"
    type: "native"
    backend:
      type: "openai"
      model: "gpt-5-nano"
      enable_code_interpreter: true
    system_message: |
      You are a data analysis expert. Analyze data, create visualizations,
      and provide statistical insights.
  
  - id: "report_writer"
    type: "framework"
    framework: "autogen"
    framework_config:
      llm_config:
        model: "claude-3-sonnet"
        temperature: 0.7
      human_input_mode: "NEVER"
      code_execution_config:
        work_dir: "./autogen_workspace"
        use_docker: false
    system_message: |
      You are a technical report writer. Synthesize research findings
      into clear, structured reports with executive summaries.

orchestrator:
  snapshot_storage: "research_snapshots"
  agent_temporary_workspace: "research_workspace"
  
ui:
  type: "rich_terminal"
  logging_enabled: true
```

Run commands with specific prompts:
```bash
# Analyze market trends
uv run python -m massgen.cli --config research_mixed_team.yaml "Analyze current market trends in renewable energy technology and identify top investment opportunities"
```

### Example 2: Parallel Data Science Agents

```yaml
# data_science_team.yaml
agents:
  - id: "claude_code"
    type: "native"
    backend:
      type: "claude_code"
      cwd: "claude_workspace"
      model: "claude-opus-4-1"
      allowed_tools:
        - "Read"
        - "Write"
        - "Edit"
        - "Bash"
        - "WebSearch"
        - "TodoWrite"
        - "NotebookEdit"
        - "mcp__ide__executeCode"
    system_message: |
      You are Claude Code, an expert data science assistant with comprehensive
      development tools. Focus on exploratory data analysis, feature engineering,
      and model prototyping.
  
  - id: "ag2_specialist"
    type: "framework"
    framework: "ag2"
    framework_config:
      agent_type: "AssistantAgent"
      name: "DataScienceSpecialist"
      llm_config:
        config_list:
          - model: "gpt-5-mini"
            api_key: "${OPENAI_API_KEY}"
        temperature: 0.5
      code_execution_config:
        last_n_messages: 2
        work_dir: "./ag2_workspace"
        use_docker: false
      max_consecutive_auto_reply: 10
      human_input_mode: "NEVER"
      system_message: |
        You are an AG2-based data science specialist. Excel at statistical analysis,
        machine learning model development, and automated experimentation.
        Use your code execution capabilities for complex computations.
  
  - id: "smolagent_analyst"
    type: "framework"
    framework: "smolagent"
    framework_config:
      model_id: "Qwen/Qwen2.5-72B-Instruct"
      tools:
        - name: "PythonInterpreter"
        - name: "Calculator"
        - name: "DataVisualizer"
        - name: "FileManager"
      max_steps: 20
      memory:
        type: "working_memory"
        max_messages: 10
    system_message: |
      You are a SmolAgent-powered data analyst specializing in automated
      data processing pipelines and visualization. Focus on efficiency
      and creating reusable analysis workflows.

orchestrator:
  snapshot_storage: "data_science_snapshots"
  agent_temporary_workspace: "data_science_workspaces"
  timeout_config:
    orchestrator_timeout_seconds: 3600  # 1 hour for complex analyses

ui:
  type: "rich_terminal"
  logging_enabled: true
```

Run commands with specific prompts:
```bash
# Analyze sales data and create visualizations
uv run python -m massgen.cli --config data_science_team.yaml "Analyze the sales_data.csv file and create visualizations showing revenue trends by region and product category"

# Build a predictive model for customer churn
uv run python -m massgen.cli --config data_science_team.yaml "Build and evaluate a machine learning model to predict customer churn using the customer_behavior.parquet dataset"
```

## Black Box Agent Advantages

### Why Use Black Box Agents?

1. **Language Independence**: Your agent can be written in any language (Python, JavaScript, Go, Rust, Java, etc.)
2. **No Framework Lock-in**: Use any existing agent regardless of its underlying framework
3. **Proprietary Code Protection**: Keep your agent's implementation private
4. **Complex Dependencies**: Avoid dependency conflicts by isolating agents
5. **Legacy System Integration**: Integrate older systems without modification
6. **Microservice Architecture**: Use agents deployed as independent services

### Common Use Cases

#### 1. Enterprise Integration
```yaml
# Integrate proprietary company agents
agents:
  - id: "company_knowledge_base"
    type: "blackbox"
    communication_method: "http"
    connection_config:
      endpoint: "https://internal.company.com/ai-agent/v2"
      headers:
        Authorization: "Bearer ${COMPANY_TOKEN}"
```

#### 2. Multi-Language Teams
```yaml
# Team members can contribute agents in their preferred language
agents:
  - id: "rust_performance_analyzer"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["./rust_agent"]
  
  - id: "golang_data_processor"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["./go_agent"]
```

#### 3. Docker Container Agents
```yaml
# Run agents in isolated Docker containers
agents:
  - id: "containerized_agent"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["docker", "run", "--rm", "-i", "my-agent:latest"]
```

#### 4. Serverless Functions
```yaml
# Use AWS Lambda or similar as agents
agents:
  - id: "lambda_agent"
    type: "blackbox"
    communication_method: "http"
    connection_config:
      endpoint: "https://api.gateway.url/prod/agent"
      headers:
        X-API-Key: "${AWS_API_KEY}"
```

### Protocol Specification

The black box protocol is intentionally simple to make integration easy:

#### Request Format
```json
{
  "version": "1.0",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "tools": [],  // Optional
  "options": {   // Optional
    "temperature": 0.7,
    "max_tokens": 1000
  }
}
```

#### Response Format (Streaming)
```json
{"type": "content", "content": "Hello! "}
{"type": "content", "content": "How can I help?"}
{"type": "tool_call", "tool": "search", "args": {...}}
{"type": "end"}
```

#### Response Format (Non-streaming)
```json
{
  "type": "final",
  "content": "Hello! How can I help you today?",
  "metadata": {
    "tokens_used": 15,
    "model": "custom-model-v1"
  }
}
```

## Benefits

### 1. Framework Diversity
- Leverage best-in-class capabilities from each framework
- Use specialized agents for specific domains
- Avoid framework lock-in

### 2. Scalability
- Distribute agents across local and cloud resources
- Scale individual agents independently
- Optimize resource usage per agent type

### 3. Compatibility
- Preserve existing MassGen coordination logic
- Framework agents participate as first-class citizens
- Unified configuration and management

### 4. Extensibility
- Easy to add new framework adapters
- Support for custom agent implementations
- Plugin architecture for specialized agents

## Future Considerations

### Dynamic Agent Selection
- Orchestrator could dynamically choose which framework agents to activate based on task requirements
- Cost-aware agent selection (prefer local/cheaper agents when suitable)

### Cross-Framework Communication
- Direct agent-to-agent communication bypassing orchestrator for efficiency
- Shared memory/context between framework agents

### Framework-Specific Optimizations
- Batch processing for certain frameworks
- Connection pooling for remote agents
- Caching of framework agent responses

## Conclusion

This design enables MassGen to become a universal orchestrator for agents regardless of their implementation framework. By wrapping framework agents with ConfigurableAgent and providing appropriate adapters, we maintain full compatibility with MassGen's proven binary decision coordination while leveraging the unique strengths of each framework. The parallel execution model ensures efficient multi-agent collaboration, and the flexible configuration system makes it easy to compose teams of heterogeneous agents for any task.