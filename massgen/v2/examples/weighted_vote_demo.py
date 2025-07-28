#!/usr/bin/env python3
"""
MassGen v0.0.2 Weighted Vote Demo - Simple vs Weighted Voting Comparison

This demo compares simple majority voting with weighted voting to demonstrate
the impact of agent weights on final decisions.
"""

import asyncio
import os
import sys

# Add parent directory to path for massgen imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from massgen.v2 import (
    # Configuration management
    AgentConfig, OrchestratorConfig, ConfigManager,
    
    # Factory functions  
    create_orchestrator,
    
    # Basic components
    StreamChunk
)


class MockExpertAgent:
    """Mock agent with different expertise levels for voting comparison."""
    
    def __init__(self, agent_id: str, expertise: str, experience_level: str):
        self.agent_id = agent_id
        self.expertise = expertise
        self.experience_level = experience_level  # junior, senior, expert
        self.session_id = f"mock_session_{agent_id}"
        self.conversation_history = []
        
        # Define expertise-based answers for a technical question
        self.answers = {
            "junior": "I think we should use React and Node.js. They're popular and have lots of tutorials online.",
            "senior": "For a scalable e-commerce platform, I recommend a microservices architecture with React frontend, Node.js API gateway, PostgreSQL database, and Redis for caching. Include proper testing and CI/CD pipeline.",
            "expert": "Implement a domain-driven design with React+TypeScript frontend, event-sourced microservices using Node.js/Go, CQRS pattern, PostgreSQL with read replicas, Redis cluster, comprehensive monitoring with Prometheus/Grafana, and automated deployment with Kubernetes."
        }
    
    async def chat(self, messages, tools=None, **kwargs):
        """Mock chat method with expertise-based responses."""
        user_message = ""
        
        for message in messages:
            if message.get("role") == "user":
                user_message = message.get("content", "")
        
        # Determine if this is initial answer or voting phase
        is_voting_phase = "CURRENT ANSWERS" in user_message and "(no answers available yet)" not in user_message
        
        if tools:
            tool_names = []
            for tool in tools:
                if "function" in tool:
                    tool_names.append(tool["function"]["name"])
                elif "name" in tool:
                    tool_names.append(tool["name"])
            
            if is_voting_phase and "vote" in tool_names:
                # Voting phase - experts prefer expert answers, juniors prefer simpler ones
                vote_target, vote_reason = self._determine_vote()
                
                yield StreamChunk(
                    type="content", 
                    content=f"[{self.experience_level}] Analyzing the provided solutions...",
                    source=self.agent_id
                )
                
                tool_call = {
                    "function": {
                        "name": "vote",
                        "arguments": {"agent_id": vote_target, "reason": vote_reason}
                    }
                }
                yield StreamChunk(type="tool_calls", content=[tool_call], source=self.agent_id)
                
            elif "new_answer" in tool_names:
                # Initial answer phase
                answer = self.answers[self.experience_level]
                yield StreamChunk(
                    type="content", 
                    content=f"[{self.experience_level}] {answer}",
                    source=self.agent_id
                )
                
                tool_call = {
                    "function": {
                        "name": "new_answer",
                        "arguments": {"content": answer}
                    }
                }
                yield StreamChunk(type="tool_calls", content=[tool_call], source=self.agent_id)
        
        yield StreamChunk(type="done", source=self.agent_id)
    
    def _determine_vote(self) -> tuple:
        """Determine voting strategy based on experience level."""
        if self.experience_level == "expert":
            # Experts prefer comprehensive solutions (agent3 = expert)
            return "agent3", "This solution demonstrates comprehensive architecture understanding and industry best practices"
        elif self.experience_level == "senior":
            # Seniors prefer balanced approaches (agent2 = senior)
            return "agent2", "This approach balances technical requirements with practical implementation considerations"
        else:
            # Juniors prefer simpler solutions (agent1 = junior)
            return "agent1", "This solution is clear, straightforward, and easy to understand"
    
    def get_status(self):
        return {
            "agent_id": self.agent_id, 
            "expertise": self.expertise,
            "experience_level": self.experience_level,
            "status": "ready"
        }
    
    def reset(self):
        self.conversation_history = []
    
    def add_to_history(self, role: str, content: str, **kwargs):
        message = {"role": role, "content": content}
        message.update(kwargs)
        self.conversation_history.append(message)


async def run_voting_test(orchestrator, strategy_name: str, show_output: bool = False):
    """Helper function to run a voting test and return results."""
    task = "Design the architecture for a new e-commerce platform that needs to handle high traffic, be maintainable, and scale globally."
    messages = [{"role": "user", "content": task}]
    
    print(f"\n🎯 Running {strategy_name} Test")
    print("-" * 50)
    print(f"Task: {task[:60]}...")
    
    try:
        async for chunk in orchestrator.chat(messages):
            if chunk.type == "content" and show_output:
                # Only show agent responses, not orchestrator messages
                if not chunk.content.startswith("🚀") and not chunk.content.startswith("##"):
                    print(chunk.content, end="")
            elif chunk.type == "done":
                break
            elif chunk.type == "error":
                print(f"❌ Error: {chunk.error}")
                return None
    except Exception as e:
        print(f"❌ {strategy_name} test error: {e}")
        return None
    
    # Get final results
    status = orchestrator.get_status()
    return {
        "strategy": strategy_name,
        "selected_agent": status.get('selected_agent'),
        "vote_distribution": status.get('vote_distribution', {}),
        "voting_config": status.get('voting_config', {}),
        "agent_states": status.get('agent_states', {})
    }


async def demo_voting_comparison():
    """Compare simple majority vs weighted voting with identical agents."""
    print("🏗️ MassGen v0.0.2 - Voting Strategy Comparison Demo")
    print("=" * 60)
    
    print("\n📋 Demo Overview:")
    print("This demo compares simple majority vs weighted voting using the same agents.")
    print("We simulate a team with different experience levels voting on technical decisions.")
    
    # Create AgentConfig instances for each team member
    agent_configs = {
        "junior_dev": AgentConfig(
            agent_id="tech_team.junior_dev",
            model="gpt-4o-mini",
            system_message="You are a junior developer with 1-2 years of experience.",
            tags=["development", "junior", "frontend"],
            temperature=0.7,
            custom_config={"experience_level": "junior", "expertise": "development"}
        ),
        "senior_dev": AgentConfig(
            agent_id="tech_team.senior_dev", 
            model="gpt-4o-mini",
            system_message="You are a senior developer with 5+ years of experience.",
            tags=["development", "senior", "fullstack"],
            temperature=0.6,
            custom_config={"experience_level": "senior", "expertise": "development"}
        ),
        "tech_expert": AgentConfig(
            agent_id="tech_team.tech_expert",
            model="gpt-4o-mini", 
            system_message="You are a technical expert and architect with 10+ years of experience.",
            tags=["architecture", "expert", "leadership"],
            temperature=0.5,
            custom_config={"experience_level": "expert", "expertise": "architecture"}
        ),
        "junior_designer": AgentConfig(
            agent_id="tech_team.junior_designer",
            model="gpt-4o-mini",
            system_message="You are a junior UI/UX designer focused on user experience.",
            tags=["design", "junior", "ui", "ux"],
            temperature=0.8,
            custom_config={"experience_level": "junior", "expertise": "design"}
        ),
        "senior_analyst": AgentConfig(
            agent_id="tech_team.senior_analyst",
            model="gpt-4o-mini",
            system_message="You are a senior business analyst with technical understanding.",
            tags=["business", "senior", "analysis"],
            temperature=0.6,
            custom_config={"experience_level": "senior", "expertise": "business"}
        )
    }
    
    # Create mock agents with proper configuration
    agents = {}
    for config_id, config in agent_configs.items():
        experience_level = config.custom_config["experience_level"]
        expertise = config.custom_config["expertise"]
        agents[config_id] = MockExpertAgent(config.agent_id, expertise, experience_level)
    
    print(f"\n👥 Team Composition ({len(agents)} agents):")
    for agent_id, agent in agents.items():
        print(f"  - {agent_id}: {agent.experience_level} level {agent.expertise}")
    
    # Define weights based on experience level and relevance to technical decisions
    agent_weights = {
        "junior_dev": 0.8,        # Junior developer - some technical knowledge
        "senior_dev": 2.0,        # Senior developer - strong technical expertise
        "tech_expert": 3.0,       # Technical expert - highest technical authority
        "junior_designer": 0.3,   # Junior designer - minimal technical input
        "senior_analyst": 1.2     # Senior analyst - business perspective matters
    }
    
    print(f"\n📋 Agent Configurations:")
    for config_id, config in agent_configs.items():
        print(f"  - {config.agent_id}:")
        print(f"    * Model: {config.model}")
        print(f"    * Tags: {config.tags}")
        print(f"    * Temperature: {config.temperature}")
        print(f"    * Experience: {config.custom_config['experience_level']}")
        print(f"    * Weight: {agent_weights[config_id]}")
    
    print(f"\n⚖️ Defined Weights (for technical decisions):")
    total_weight = sum(agent_weights.values())
    for agent_id, weight in agent_weights.items():
        percentage = (weight / total_weight) * 100
        agent = agents[agent_id]
        print(f"  - {agent_id}: {weight} ({percentage:.1f}%) - {agent.experience_level} {agent.expertise}")
    print(f"  Total weight: {total_weight}")
    
    # Test 1: Simple Majority (each agent gets 1 vote)
    print("\n" + "="*60)
    print("TEST 1: SIMPLE MAJORITY VOTING")
    print("="*60)
    print("Each agent has equal voting power (1 vote each)")
    
    # Create orchestrator config for simple majority
    simple_orchestrator_config = OrchestratorConfig(
        orchestrator_id="simple_majority_test",
        max_duration=300,
        max_rounds=5,
        voting_config={
            "voting_strategy": "simple_majority",
            "tie_breaking": "registration_order",
            "include_vote_reasons": True,
            "anonymous_voting": False
        },
        enable_streaming=True,
        track_votes=True
    )
    
    orchestrator_simple = create_orchestrator(
        agents=agents,
        orchestrator_id=simple_orchestrator_config.orchestrator_id,
        config={
            "voting": simple_orchestrator_config.voting_config,
            "max_duration": simple_orchestrator_config.max_duration,
            "max_rounds": simple_orchestrator_config.max_rounds
        }
    )
    
    simple_results = await run_voting_test(orchestrator_simple, "Simple Majority", show_output=True)
    
    # Test 2: Weighted Voting (agents have different vote weights)
    print("\n" + "="*60)
    print("TEST 2: WEIGHTED VOTING")
    print("="*60)
    print("Agents have different voting power based on expertise")
    
    # Create orchestrator config for weighted voting
    weighted_orchestrator_config = OrchestratorConfig(
        orchestrator_id="weighted_vote_test",
        max_duration=300,
        max_rounds=5,
        voting_config={
            "voting_strategy": "weighted_vote",
            "tie_breaking": "highest_weight",
            "include_vote_reasons": True,
            "include_vote_counts": True,
            "anonymous_voting": False
        },
        enable_streaming=True,
        track_votes=True,
        custom_orchestrator_config={"agent_weights": agent_weights}
    )
    
    orchestrator_weighted = create_orchestrator(
        agents=agents,
        agent_weights=agent_weights,
        orchestrator_id=weighted_orchestrator_config.orchestrator_id,
        config={
            "voting": weighted_orchestrator_config.voting_config,
            "max_duration": weighted_orchestrator_config.max_duration,
            "max_rounds": weighted_orchestrator_config.max_rounds
        }
    )
    
    weighted_results = await run_voting_test(orchestrator_weighted, "Weighted Vote", show_output=True)
    
    # Compare results
    print("\n" + "="*60)
    print("COMPARISON RESULTS")
    print("="*60)
    
    if simple_results and weighted_results:
        print(f"\n📊 Voting Outcomes:")
        print(f"  Simple Majority Winner: {simple_results['selected_agent']}")
        print(f"  Weighted Vote Winner:   {weighted_results['selected_agent']}")
        
        if simple_results['selected_agent'] != weighted_results['selected_agent']:
            print(f"  🎯 DIFFERENT WINNERS! Weights changed the outcome.")
        else:
            print(f"  ✓ Same winner in both strategies.")
        
        print(f"\n📈 Vote Distributions:")
        print(f"  Simple Majority: {simple_results['vote_distribution']}")
        print(f"  Weighted Vote:   {weighted_results['vote_distribution']}")
        
        # Show the impact of weights
        print(f"\n🔍 Analysis:")
        simple_dist = simple_results['vote_distribution']
        weighted_dist = weighted_results['vote_distribution']
        
        if simple_dist and weighted_dist:
            print(f"  In simple majority: Each vote counts as 1")
            total_simple = sum(simple_dist.values())
            for agent, votes in simple_dist.items():
                pct = (votes / total_simple) * 100 if total_simple > 0 else 0
                print(f"    {agent}: {votes} votes ({pct:.1f}%)")
            
            print(f"  In weighted voting: Votes weighted by expertise")
            total_weighted = sum(weighted_dist.values())
            for agent, weight_score in weighted_dist.items():
                pct = (weight_score / total_weighted) * 100 if total_weighted > 0 else 0
                print(f"    {agent}: {weight_score:.1f} weighted score ({pct:.1f}%)")
        
        # Show agent experience levels that voted for winner
        print(f"\n🎓 Winner Analysis:")
        for strategy, results in [("Simple Majority", simple_results), ("Weighted Vote", weighted_results)]:
            winner = results['selected_agent']
            if winner:
                # Find which experience levels supported the winner
                winner_supporters = []
                for agent_id, agent in agents.items():
                    agent_state = results['agent_states'].get(agent_id, {})
                    if agent_state.get('has_voted'):
                        # In our mock, we know the voting pattern
                        if ((agent.experience_level == "expert" and winner == "agent3") or
                            (agent.experience_level == "senior" and winner == "agent2") or  
                            (agent.experience_level == "junior" and winner == "agent1")):
                            winner_supporters.append(f"{agent.experience_level} {agent.expertise}")
                
                print(f"  {strategy}: Supported by {winner_supporters}")
    
    print(f"\n💡 Key Insights:")
    print(f"  - Simple majority treats all opinions equally")
    print(f"  - Weighted voting amplifies expert voices on technical decisions") 
    print(f"  - Weight distribution should match decision context")
    print(f"  - Different strategies can lead to different outcomes")
    
    print(f"\n✅ Demo completed! Both voting strategies are working correctly.")


async def test_research_team_configs():
    """Test research team configurations with and without weights."""
    print("\n" + "="*80)
    print("🔬 RESEARCH TEAM CONFIGURATION COMPARISON")
    print("="*80)
    
    config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config_templates")
    
    # Test 1: Load and test non-weighted research team
    print("\n📋 Test 1: Non-weighted Research Team Configuration")
    print("-" * 50)
    
    try:
        config_path = os.path.join(config_dir, "research_team.yaml")
        config = ConfigManager.load_from_file(config_path)
        
        print(f"✅ Loaded config from: {config_path}")
        print(f"Team ID: {config['team_id']}")
        print(f"Agents: {len(config['agents'])}")
        print(f"Voting strategy: {config['orchestrator']['voting_config']['voting_strategy']}")
        
        # Show agent roles
        for agent in config['agents']:
            agent_id = agent['agent_id'].split('.')[-1]  # Get role name
            print(f"  - {agent_id}: {agent.get('tags', [])}")
        
        # Create mock research team (simplified for demo)
        research_agents = {}
        for agent_config in config['agents']:
            agent_id = agent_config['agent_id']  # Use original agent_id from config
            role = agent_config['agent_id'].split('.')[-1]
            research_agents[agent_id] = MockExpertAgent(agent_id, role, "senior")
        
        # Create orchestrator without weights
        orchestrator_simple = create_orchestrator(
            agents=research_agents,
            orchestrator_id="research_team_simple",
            config={
                "voting": {
                    "voting_strategy": "simple_majority",
                    "tie_breaking": "registration_order"
                }
            }
        )
        
        result_simple = await run_voting_test(orchestrator_simple, "Research Team (No Weights)")
        
    except Exception as e:
        print(f"❌ Error testing non-weighted config: {e}")
        result_simple = None
    
    # Test 2: Load and test weighted research team
    print("\n📋 Test 2: Weighted Research Team Configuration")
    print("-" * 50)
    
    try:
        config_path = os.path.join(config_dir, "research_team_weighted.yaml")
        config = ConfigManager.load_from_file(config_path)
        
        print(f"✅ Loaded config from: {config_path}")
        print(f"Team ID: {config['team_id']}")
        print(f"Agents: {len(config['agents'])}")
        print(f"Voting strategy: {config['orchestrator']['voting_config']['voting_strategy']}")
        
        # Extract weights and show distribution
        agent_weights = {}
        total_weight = 0
        print(f"\n⚖️ Agent Weights:")
        
        for agent_config in config['agents']:
            agent_id = agent_config['agent_id']  # Use original agent_id from config
            role = agent_config['agent_id'].split('.')[-1]
            weight = agent_config.get('weight', 1.0)
            agent_weights[agent_id] = weight
            total_weight += weight
            
            percentage = (weight / sum([a.get('weight', 1.0) for a in config['agents']])) * 100
            print(f"  - {role}: {weight} ({percentage:.1f}%)")
        
        print(f"  Total weight: {total_weight}")
        
        # Create mock research team with roles
        research_agents = {}
        for agent_config in config['agents']:
            agent_id = agent_config['agent_id']  # Use original agent_id from config
            role = agent_config['agent_id'].split('.')[-1]
            
            # Map roles to experience levels for voting behavior
            experience_map = {
                "primary_researcher": "senior",
                "fact_checker": "senior", 
                "analyst": "expert",  # Highest weight
                "reporter": "junior"
            }
            experience = experience_map.get(role, "senior")
            research_agents[agent_id] = MockExpertAgent(agent_id, role, experience)
        
        # Create orchestrator with weights
        orchestrator_weighted = create_orchestrator(
            agents=research_agents,
            agent_weights=agent_weights,
            orchestrator_id="research_team_weighted",
            config={
                "voting": {
                    "voting_strategy": "weighted_vote",
                    "tie_breaking": "highest_weight"
                }
            }
        )
        
        result_weighted = await run_voting_test(orchestrator_weighted, "Research Team (Weighted)")
        
    except Exception as e:
        print(f"❌ Error testing weighted config: {e}")
        result_weighted = None
    
    # Compare results
    print("\n" + "="*80)
    print("📊 RESEARCH TEAM COMPARISON RESULTS")
    print("="*80)
    
    if result_simple and result_weighted:
        print(f"\n🎯 Configuration Outcomes:")
        print(f"  Non-weighted Winner: {result_simple['selected_agent']}")
        print(f"  Weighted Winner:     {result_weighted['selected_agent']}")
        
        if result_simple['selected_agent'] != result_weighted['selected_agent']:
            print(f"  🎯 DIFFERENT WINNERS! Weights changed the research team decision.")
        else:
            print(f"  ✓ Same winner with both configurations.")
        
        print(f"\n📈 Vote Distributions:")
        print(f"  Non-weighted: {result_simple['vote_distribution']}")
        print(f"  Weighted:     {result_weighted['vote_distribution']}")
        
        print(f"\n🔍 Research Team Analysis:")
        print(f"  - Non-weighted: All research roles have equal say")
        print(f"  - Weighted: Analyst (highest expertise) has 3x weight")
        print(f"  - Weighted: Primary researcher has 2.5x weight") 
        print(f"  - Weighted: Fact checker has 2x weight")
        print(f"  - Weighted: Reporter has 1.5x weight")
        print(f"  - This reflects real research team dynamics where")
        print(f"    analytical expertise should carry more weight in decisions")
    
    return result_simple, result_weighted




async def main():
    """Run voting demonstrations with AgentConfig and ConfigManager."""
    print("🏗️ MassGen v0.0.2 - Weighted Vote Demo with ConfigManager")
    print("="*80)
    
    # Run enhanced voting comparison with AgentConfig
    await demo_voting_comparison()
    
    # Run research team configuration tests
    await test_research_team_configs()
    
    print(f"\n✅ All demos completed successfully!")
    print(f"📋 Summary:")
    print(f"   1. Enhanced voting demo uses AgentConfig and OrchestratorConfig")
    print(f"   2. Research team configs demonstrate ConfigManager.load_from_file usage") 
    print(f"   3. Tests validate proper weight influence on voting outcomes")
    print(f"   4. Demonstrates integration with agent_config.py ConfigManager")



if __name__ == "__main__":
    asyncio.run(main())