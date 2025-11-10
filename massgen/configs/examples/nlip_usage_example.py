"""
NLIP Usage Example for MassGen

This example demonstrates how to use NLIP (Natural Language Interaction Protocol)
with MassGen agents and orchestrator.
"""

import asyncio
from massgen import ConfigurableAgent, Orchestrator
from massgen.agent_config import AgentConfig
from massgen.nlip import (
    NLIPMessage, NLIPRequest, NLIPResponse, NLIPToolCall,
    NLIPControlField, NLIPTokenField, NLIPFormatField,
    NLIPMessageType
)
import uuid
from datetime import datetime


async def example_1_basic_nlip_agent():
    """Example 1: Create a NLIP-enabled agent"""
    print("=" * 60)
    print("Example 1: Basic NLIP-Enabled Agent")
    print("=" * 60)

    # Create agent config with NLIP enabled
    config = AgentConfig(
        backend_params={
            "type": "openai",
            "model": "gpt-4o-mini"
        },
        agent_id="nlip_agent_1",
        enable_nlip=True,
        nlip_config={
            "router": {
                "enable_message_tracking": True,
                "session_timeout_hours": 24
            }
        }
    )

    print(f"✓ Created AgentConfig with NLIP enabled: {config.enable_nlip}")
    print(f"✓ NLIP config: {config.nlip_config}")

    # Note: Full agent creation would require backend initialization
    # This example shows the configuration structure


async def example_2_nlip_router_direct():
    """Example 2: Use NLIP Router directly"""
    print("\n" + "=" * 60)
    print("Example 2: Direct NLIP Router Usage")
    print("=" * 60)

    from massgen.nlip.router import NLIPRouter

    # Create NLIP router
    router = NLIPRouter(
        tool_manager=None,  # Would pass actual tool manager in real usage
        enable_nlip=True,
        config={}
    )

    print(f"✓ Created NLIPRouter, enabled: {router.is_enabled()}")

    # Create a simple NLIP request
    request = NLIPRequest(
        format=NLIPFormatField(
            content_type="application/json",
            encoding="utf-8",
            schema_version="1.0"
        ),
        control=NLIPControlField(
            message_type=NLIPMessageType.REQUEST,
            message_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow().isoformat() + "Z"
        ),
        token=NLIPTokenField(
            session_id="example_session",
            context_token=str(uuid.uuid4()),
            conversation_turn=1
        ),
        content={"query": "Example query"},
        tool_calls=[
            NLIPToolCall(
                tool_id="call_1",
                tool_name="example_tool",
                parameters={"param1": "value1"},
                require_confirmation=False
            )
        ]
    )

    print(f"✓ Created NLIP request with message_id: {request.control.message_id}")
    print(f"✓ Tool calls: {len(request.tool_calls or [])}")


async def example_3_multi_agent_nlip():
    """Example 3: Multi-agent orchestrator with NLIP"""
    print("\n" + "=" * 60)
    print("Example 3: Multi-Agent NLIP Orchestrator")
    print("=" * 60)

    # Create NLIP-enabled agent configs
    agent_configs = []
    for i in range(3):
        config = AgentConfig(
            backend_params={"type": "openai", "model": "gpt-4o-mini"},
            agent_id=f"nlip_agent_{i}",
            enable_nlip=True,
            nlip_config={
                "router": {
                    "enable_message_tracking": True
                }
            }
        )
        agent_configs.append(config)
        print(f"✓ Created config for agent_{i} with NLIP enabled")

    # In real usage, you would create agents from configs and orchestrator
    # agents = {config.agent_id: create_agent(config) for config in agent_configs}
    # orchestrator = Orchestrator(
    #     agents=agents,
    #     enable_nlip=True,
    #     nlip_config={"router": {"enable_message_tracking": True}}
    # )

    print("✓ Multi-agent NLIP configuration ready")


async def example_4_nlip_message_structure():
    """Example 4: NLIP Message Structure"""
    print("\n" + "=" * 60)
    print("Example 4: NLIP Message Structure")
    print("=" * 60)

    # Demonstrate NLIP message components
    format_field = NLIPFormatField(
        content_type="application/json",
        encoding="utf-8",
        schema_version="1.0"
    )
    print(f"✓ Format field: {format_field.content_type}, version {format_field.schema_version}")

    control_field = NLIPControlField(
        message_type=NLIPMessageType.REQUEST,
        message_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat() + "Z",
        priority=5
    )
    print(f"✓ Control field: type={control_field.message_type}, priority={control_field.priority}")

    token_field = NLIPTokenField(
        session_id="session_123",
        context_token="ctx_456",
        conversation_turn=3
    )
    print(f"✓ Token field: session={token_field.session_id}, turn={token_field.conversation_turn}")

    message = NLIPMessage(
        format=format_field,
        control=control_field,
        token=token_field,
        content={"message": "Example content"}
    )
    print(f"✓ Complete NLIP message created")


async def main():
    """Run all examples"""
    print("\n" + "=" * 60)
    print("NLIP Integration Examples for MassGen")
    print("=" * 60 + "\n")

    await example_1_basic_nlip_agent()
    await example_2_nlip_router_direct()
    await example_3_multi_agent_nlip()
    await example_4_nlip_message_structure()

    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
