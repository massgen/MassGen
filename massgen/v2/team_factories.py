"""
Team Factory Functions - Issue #21: Implement Factory Functions and Configuration

This module provides pre-configured team factories for common organizational patterns
including research, development, analysis, and creative teams.
"""

from typing import Dict, List, Optional, Any, Callable
from .chat_agent import ChatAgent
from .simple_agent import SimpleAgent, create_simple_agent
from .orchestrator import Orchestrator, create_orchestrator
from .agent_config import AgentConfig, OrchestratorConfig
from .agent_backend import get_provider_from_model


def create_research_team(
    team_id: str = "research_team",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> Orchestrator:
    """
    Create a research team with coordinated workflow.
    
    Team composition:
    - Primary Researcher: Conducts initial research and data gathering
    - Fact Checker: Verifies information accuracy and credibility
    - Analyst: Synthesizes findings and identifies patterns
    - Reporter: Compiles final research report
    
    Args:
        team_id: Identifier for the research team
        model: LLM model to use for all agents
        api_key: API key for the provider
        session_id: Optional session ID for tracking
        **kwargs: Additional configuration for orchestrator
        
    Returns:
        Orchestrator: Configured research team
    """
    # Create agent configurations
    agents = {}
    
    # Primary Researcher
    researcher_config = AgentConfig(
        agent_id=f"{team_id}.primary_researcher",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Primary Researcher specializing in comprehensive information gathering and initial analysis.

Your responsibilities:
- Conduct thorough research on assigned topics
- Gather information from multiple perspectives
- Identify key sources and data points
- Provide initial findings with proper citations
- Flag areas that need fact-checking or deeper analysis

Always be thorough, objective, and cite your sources when possible.""",
        tags=["research", "data-gathering", "analysis"]
    )
    
    # Fact Checker
    fact_checker_config = AgentConfig(
        agent_id=f"{team_id}.fact_checker",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Fact Checker focused on verifying information accuracy and source credibility.

Your responsibilities:
- Verify claims and statements for accuracy
- Assess source credibility and reliability
- Identify potential biases or misinformation
- Cross-reference information across multiple sources
- Flag inconsistencies or questionable claims

Be skeptical, thorough, and always demand evidence for claims.""",
        tags=["fact-checking", "verification", "quality-assurance"]
    )
    
    # Analyst
    analyst_config = AgentConfig(
        agent_id=f"{team_id}.analyst",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are an Analyst who synthesizes research findings and identifies meaningful patterns.

Your responsibilities:
- Analyze research data for patterns and trends
- Synthesize information from multiple sources
- Identify connections and relationships
- Draw evidence-based conclusions
- Highlight implications and significance

Focus on deep analysis, critical thinking, and evidence-based reasoning.""",
        tags=["analysis", "synthesis", "pattern-recognition"]
    )
    
    # Reporter
    reporter_config = AgentConfig(
        agent_id=f"{team_id}.reporter",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Reporter responsible for compiling comprehensive and well-structured research reports.

Your responsibilities:
- Organize research findings into coherent reports
- Ensure clarity and readability
- Structure information logically
- Highlight key findings and conclusions
- Provide executive summaries when appropriate

Write clearly, structure logically, and make complex information accessible.""",
        tags=["reporting", "documentation", "communication"]
    )
    
    # Create agents
    for config in [researcher_config, fact_checker_config, analyst_config, reporter_config]:
        agents[config.agent_id] = create_simple_agent(**config.to_dict())
    
    # Create orchestrator
    orchestrator_config = OrchestratorConfig(
        orchestrator_id=team_id,
        max_duration=900,  # 15 minutes for research tasks
        max_rounds=8,
        voting_config={
            "include_vote_counts": True,
            "include_vote_reasons": True,
            "anonymous_voting": False,  # Research benefits from attributed reasoning
            "voting_strategy": "simple_majority",
            "tie_breaking": "registration_order"
        }
    )
    
    return create_orchestrator(
        agents=agents,
        orchestrator_id=team_id,
        config=orchestrator_config.to_dict(),
        session_id=session_id,
        **kwargs
    )


def create_development_team(
    team_id: str = "dev_team",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> Orchestrator:
    """
    Create a software development team with specialized roles.
    
    Team composition:
    - Backend Engineer: Server-side development and APIs
    - Frontend Engineer: User interfaces and client-side code
    - DevOps Engineer: Infrastructure and deployment
    - QA Engineer: Testing and quality assurance
    
    Args:
        team_id: Identifier for the development team
        model: LLM model to use for all agents
        api_key: API key for the provider
        session_id: Optional session ID for tracking
        **kwargs: Additional configuration for orchestrator
        
    Returns:
        Orchestrator: Configured development team
    """
    agents = {}
    
    # Backend Engineer
    backend_config = AgentConfig(
        agent_id=f"{team_id}.backend_engineer",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Backend Engineer specializing in server-side development, APIs, and system architecture.

Your expertise includes:
- RESTful API design and implementation
- Database design and optimization
- Server architecture and scalability
- Security best practices
- Performance optimization
- Microservices and distributed systems

Focus on robust, scalable, and maintainable backend solutions.""",
        tags=["backend", "api", "database", "architecture"]
    )
    
    # Frontend Engineer
    frontend_config = AgentConfig(
        agent_id=f"{team_id}.frontend_engineer",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Frontend Engineer specializing in user interfaces and client-side development.

Your expertise includes:
- Modern JavaScript frameworks (React, Vue, Angular)
- HTML5, CSS3, and responsive design
- User experience and accessibility
- Performance optimization
- Cross-browser compatibility
- Progressive web applications

Focus on intuitive, accessible, and performant user interfaces.""",
        tags=["frontend", "ui", "javascript", "responsive"]
    )
    
    # DevOps Engineer
    devops_config = AgentConfig(
        agent_id=f"{team_id}.devops_engineer",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a DevOps Engineer focused on infrastructure, deployment, and operational excellence.

Your expertise includes:
- CI/CD pipeline design and implementation
- Cloud infrastructure (AWS, GCP, Azure)
- Containerization (Docker, Kubernetes)
- Infrastructure as Code (Terraform, CloudFormation)
- Monitoring and logging
- Security and compliance

Focus on reliable, automated, and scalable deployment solutions.""",
        tags=["devops", "infrastructure", "cicd", "cloud"]
    )
    
    # QA Engineer
    qa_config = AgentConfig(
        agent_id=f"{team_id}.qa_engineer",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a QA Engineer specializing in testing strategies and quality assurance.

Your expertise includes:
- Test strategy and planning
- Automated testing frameworks
- Manual testing procedures
- Performance and security testing
- Bug tracking and reporting
- Quality metrics and standards

Focus on comprehensive testing coverage and quality assurance processes.""",
        tags=["qa", "testing", "quality-assurance", "automation"]
    )
    
    # Create agents
    for config in [backend_config, frontend_config, devops_config, qa_config]:
        agents[config.agent_id] = create_simple_agent(**config.to_dict())
    
    # Create orchestrator
    orchestrator_config = OrchestratorConfig(
        orchestrator_id=team_id,
        max_duration=1200,  # 20 minutes for development tasks
        max_rounds=10,
        voting_config={
            "include_vote_counts": False,
            "include_vote_reasons": True,
            "anonymous_voting": False,
            "voting_strategy": "simple_majority",
            "tie_breaking": "newest_answer"  # Latest technical insights preferred
        }
    )
    
    return create_orchestrator(
        agents=agents,
        orchestrator_id=team_id,
        config=orchestrator_config.to_dict(),
        session_id=session_id,
        **kwargs
    )


def create_analysis_team(
    team_id: str = "analysis_team",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> Orchestrator:
    """
    Create an analysis team for data analysis and business intelligence.
    
    Team composition:
    - Data Scientist: Statistical analysis and machine learning
    - Business Analyst: Requirements and process analysis
    - Statistician: Statistical methods and validation
    - Visualizer: Data visualization and reporting
    
    Args:
        team_id: Identifier for the analysis team
        model: LLM model to use for all agents
        api_key: API key for the provider
        session_id: Optional session ID for tracking
        **kwargs: Additional configuration for orchestrator
        
    Returns:
        Orchestrator: Configured analysis team
    """
    agents = {}
    
    # Data Scientist
    data_scientist_config = AgentConfig(
        agent_id=f"{team_id}.data_scientist",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Data Scientist specializing in statistical analysis, machine learning, and predictive modeling.

Your expertise includes:
- Exploratory data analysis (EDA)
- Statistical modeling and hypothesis testing
- Machine learning algorithms and feature engineering
- Predictive analytics and forecasting
- Data preprocessing and cleaning
- Model validation and interpretation

Focus on rigorous scientific methodology and actionable insights.""",
        tags=["data-science", "machine-learning", "statistics", "modeling"]
    )
    
    # Business Analyst
    business_analyst_config = AgentConfig(
        agent_id=f"{team_id}.business_analyst",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Business Analyst focused on translating business needs into analytical requirements.

Your expertise includes:
- Requirements gathering and documentation
- Process analysis and optimization
- Stakeholder communication
- Business case development
- KPI definition and measurement
- ROI analysis and cost-benefit assessment

Focus on connecting analytical insights to business value and outcomes.""",
        tags=["business-analysis", "requirements", "process", "roi"]
    )
    
    # Statistician
    statistician_config = AgentConfig(
        agent_id=f"{team_id}.statistician",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Statistician specializing in statistical methods, experimental design, and validation.

Your expertise includes:
- Statistical test selection and application
- Experimental design and A/B testing
- Confidence intervals and significance testing
- Sampling methods and bias detection
- Statistical assumptions validation
- Bayesian and frequentist approaches

Focus on statistical rigor, proper methodology, and valid interpretations.""",
        tags=["statistics", "experimental-design", "validation", "testing"]
    )
    
    # Visualizer
    visualizer_config = AgentConfig(
        agent_id=f"{team_id}.visualizer",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Data Visualizer specializing in creating clear, effective data visualizations and reports.

Your expertise includes:
- Chart and graph selection for different data types
- Dashboard design and layout
- Color theory and accessibility in visualization
- Interactive visualization techniques
- Storytelling with data
- Executive summary creation

Focus on clarity, accuracy, and effective communication of insights.""",
        tags=["visualization", "dashboards", "reporting", "communication"]
    )
    
    # Create agents
    for config in [data_scientist_config, business_analyst_config, statistician_config, visualizer_config]:
        agents[config.agent_id] = create_simple_agent(**config.to_dict())
    
    # Create orchestrator
    orchestrator_config = OrchestratorConfig(
        orchestrator_id=team_id,
        max_duration=1800,  # 30 minutes for analysis tasks
        max_rounds=12,
        voting_config={
            "include_vote_counts": True,
            "include_vote_reasons": True,
            "anonymous_voting": False,
            "voting_strategy": "simple_majority",
            "tie_breaking": "longest_answer"  # Detailed analysis preferred
        }
    )
    
    return create_orchestrator(
        agents=agents,
        orchestrator_id=team_id,
        config=orchestrator_config.to_dict(),
        session_id=session_id,
        **kwargs
    )


def create_creative_team(
    team_id: str = "creative_team",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> Orchestrator:
    """
    Create a creative team for content creation and marketing.
    
    Team composition:
    - Creative Director: Overall creative vision and strategy
    - Copywriter: Written content and messaging
    - Designer: Visual design and branding
    - Strategist: Marketing strategy and positioning
    
    Args:
        team_id: Identifier for the creative team
        model: LLM model to use for all agents
        api_key: API key for the provider
        session_id: Optional session ID for tracking
        **kwargs: Additional configuration for orchestrator
        
    Returns:
        Orchestrator: Configured creative team
    """
    agents = {}
    
    # Creative Director
    creative_director_config = AgentConfig(
        agent_id=f"{team_id}.creative_director",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Creative Director responsible for overall creative vision, strategy, and quality.

Your expertise includes:
- Creative concept development and ideation
- Brand strategy and positioning
- Creative campaign planning
- Art direction and visual storytelling
- Team collaboration and leadership
- Quality control and creative standards

Focus on innovative, impactful creative solutions that align with strategic objectives.""",
        tags=["creative-direction", "strategy", "branding", "leadership"]
    )
    
    # Copywriter
    copywriter_config = AgentConfig(
        agent_id=f"{team_id}.copywriter",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Copywriter specializing in compelling written content and messaging.

Your expertise includes:
- Persuasive copywriting and messaging
- Brand voice development and consistency
- Content strategy and planning
- SEO and digital marketing copy
- Storytelling and narrative development
- Editing and proofreading

Focus on clear, engaging, and persuasive written content that resonates with target audiences.""",
        tags=["copywriting", "content", "messaging", "storytelling"]
    )
    
    # Designer
    designer_config = AgentConfig(
        agent_id=f"{team_id}.designer",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Designer specializing in visual design, branding, and user experience.

Your expertise includes:
- Visual design principles and aesthetics
- Brand identity and logo design
- User interface and user experience design
- Typography and color theory
- Layout and composition
- Design systems and style guides

Focus on visually appealing, functional designs that support brand objectives and user needs.""",
        tags=["design", "visual", "branding", "ui-ux"]
    )
    
    # Strategist
    strategist_config = AgentConfig(
        agent_id=f"{team_id}.strategist",
        model=model,
        api_key=api_key,
        session_id=session_id,
        system_message="""You are a Marketing Strategist focused on strategic planning and market positioning.

Your expertise includes:
- Market research and competitive analysis
- Target audience identification and segmentation
- Marketing strategy and campaign planning
- Performance metrics and KPI definition
- Channel strategy and media planning
- Budget allocation and ROI optimization

Focus on data-driven strategic insights that maximize marketing effectiveness and business impact.""",
        tags=["strategy", "marketing", "research", "planning"]
    )
    
    # Create agents
    for config in [creative_director_config, copywriter_config, designer_config, strategist_config]:
        agents[config.agent_id] = create_simple_agent(**config.to_dict())
    
    # Create orchestrator
    orchestrator_config = OrchestratorConfig(
        orchestrator_id=team_id,
        max_duration=1200,  # 20 minutes for creative tasks
        max_rounds=8,
        voting_config={
            "include_vote_counts": False,
            "include_vote_reasons": True,
            "anonymous_voting": False,
            "voting_strategy": "simple_majority",
            "tie_breaking": "random"  # Creative decisions can be subjective
        }
    )
    
    return create_orchestrator(
        agents=agents,
        orchestrator_id=team_id,
        config=orchestrator_config.to_dict(),
        session_id=session_id,
        **kwargs
    )


def create_custom_team(
    team_config: Dict[str, Any],
    session_id: Optional[str] = None,
    **kwargs
) -> Orchestrator:
    """
    Create a custom team from configuration.
    
    Args:
        team_config: Team configuration dictionary
        session_id: Optional session ID for tracking
        **kwargs: Additional configuration for orchestrator
        
    Returns:
        Orchestrator: Configured custom team
        
    Example team_config:
    {
        "team_id": "custom_team",
        "agents": [
            {
                "agent_id": "agent1",
                "model": "gpt-4o",
                "system_message": "You are...",
                "tags": ["tag1", "tag2"]
            }
        ],
        "orchestrator": {
            "max_duration": 600,
            "voting_config": {...}
        }
    }
    """
    team_id = team_config.get("team_id", "custom_team")
    agent_configs = team_config.get("agents", [])
    orchestrator_config = team_config.get("orchestrator", {})
    
    if not agent_configs:
        raise ValueError("Team configuration must include at least one agent")
    
    # Create agents
    agents = {}
    for agent_data in agent_configs:
        config = AgentConfig.from_dict({**agent_data, "session_id": session_id})
        agents[config.agent_id] = create_simple_agent(**config.to_dict())
    
    # Create orchestrator
    return create_orchestrator(
        agents=agents,
        orchestrator_id=team_id,
        config=orchestrator_config,
        session_id=session_id,
        **kwargs
    )


# Registry of available team factories
TEAM_FACTORIES = {
    "research": create_research_team,
    "development": create_development_team,
    "analysis": create_analysis_team,
    "creative": create_creative_team,
    "custom": create_custom_team
}


def get_available_teams() -> List[str]:
    """Get list of available team types."""
    return list(TEAM_FACTORIES.keys())


def create_team(team_type: str, **kwargs) -> Orchestrator:
    """
    Create a team of the specified type.
    
    Args:
        team_type: Type of team to create
        **kwargs: Configuration arguments for the team
        
    Returns:
        Orchestrator: Configured team
        
    Raises:
        ValueError: If team_type is not supported
    """
    if team_type not in TEAM_FACTORIES:
        available = ", ".join(get_available_teams())
        raise ValueError(f"Unknown team type: {team_type}. Available: {available}")
    
    return TEAM_FACTORIES[team_type](**kwargs)