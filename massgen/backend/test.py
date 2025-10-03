from autogen import ConversableAgent, LLMConfig
from dotenv import load_dotenv
import os
load_dotenv()

# Create LLM configuration first
llm_config= LLMConfig(config_list={"api_type": "openai", "model": "gpt-5-nano","api_key":os.getenv("OPENAI_API_KEY")})

# Create the agent using the context manager approach
my_agent = ConversableAgent(
    name="helpful_agent",  # Give your agent a unique name
    system_message="You are a helpful AI assistant",  # Define its personality and purpose
    human_input_mode="NEVER",
    llm_config=llm_config  # Pass the LLM configuration
)

async def run_agent():
    reply = await my_agent.a_generate_reply(
        messages=[{"role": "user", "content": "Tell me about quantum computing."}]
    )
    print("Reply:", reply)


import asyncio
asyncio.run(run_agent())
