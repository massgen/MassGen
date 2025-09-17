'use client'

import { usePanelStore } from '@/store/usePanelStore'
import { useState } from 'react'

export default function DemoSimulation() {
  const { streamContent, updateAgentStatus, setPhase, setPrompt, setActiveAgentCount, setConfigFile, activeAgentCount } = usePanelStore()
  const [isRunning, setIsRunning] = useState(false)

  const runDemo = async () => {
    if (isRunning) return
    setIsRunning(true)

    // Set up demo environment (preserve current agent count)
    setPrompt("What is the best approach for building a scalable multi-agent coordination system?")
    
    // Load a sample config file
    const sampleConfig = `# Demo Configuration
agents:
  - id: "agent-1"
    backend:
      type: "claude"
      model: "claude-3.5-sonnet"
    system_message: "Architecture specialist"

  - id: "agent-2" 
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
    system_message: "Implementation expert"

  - id: "agent-3"
    backend:
      type: "openai" 
      model: "gpt-5-nano"
    system_message: "Performance analyst"

ui:
  display_type: "grid"
  coordination_timeout: 60`
  
    setConfigFile("demo_config.yaml", sampleConfig)

    // Phase 1: Starting
    setPhase('starting')
    await sleep(1000)

    streamContent('orchestrator', 'Demo simulation started\n')
    streamContent('orchestrator', 'Initializing agents...\n')

    // Phase 2: Coordinating
    setPhase('coordinating')
    
    // Set all active agents to working status
    for (let i = 1; i <= activeAgentCount; i++) {
      updateAgentStatus(`agent-${i}`, 'working')
    }

    await sleep(500)
    
    // Give each agent different mock content based on their role
    const agentRoles = [
      { emoji: '🔍', role: 'Architecture Analyst', content: 'Analyzing architectural patterns...\n\nKey considerations for multi-agent systems:\n- Communication protocols\n- Fault tolerance\n- Load balancing' },
      { emoji: '🛠️', role: 'Implementation Expert', content: 'Evaluating implementation strategies...\n\nRecommended technologies:\n- Message queues for async communication\n- Containerization for agent isolation\n- Health monitoring systems' },
      { emoji: '📊', role: 'Performance Analyst', content: 'Performance analysis perspective...\n\nScalability factors:\n- Horizontal scaling patterns\n- Resource allocation strategies\n- Coordination overhead optimization' },
      { emoji: '🔒', role: 'Security Specialist', content: 'Security assessment...\n\nSecurity considerations:\n- Authentication mechanisms\n- Data encryption at rest\n- Network security protocols' },
      { emoji: '🧠', role: 'AI Coordinator', content: 'AI coordination strategies...\n\nML considerations:\n- Model distribution patterns\n- Training data synchronization\n- Inference optimization' },
      { emoji: '⚡', role: 'Efficiency Expert', content: 'Efficiency optimization...\n\nPerformance improvements:\n- Resource pooling\n- Caching strategies\n- Network optimization' },
      { emoji: '🌐', role: 'Network Specialist', content: 'Network architecture...\n\nDistributed networking:\n- Load balancing strategies\n- Failover mechanisms\n- Latency optimization' },
      { emoji: '📡', role: 'Data Engineer', content: 'Data flow analysis...\n\nData considerations:\n- Stream processing\n- Data consistency\n- Batch operations' },
      { emoji: '🔧', role: 'DevOps Engineer', content: 'Infrastructure planning...\n\nDeployment strategies:\n- Container orchestration\n- CI/CD pipelines\n- Monitoring solutions' },
      { emoji: '🎯', role: 'Quality Assurance', content: 'Quality assessment...\n\nTesting strategies:\n- Integration testing\n- Load testing\n- Fault injection' },
      { emoji: '📝', role: 'Documentation', content: 'Documentation analysis...\n\nDocumentation needs:\n- API documentation\n- Architecture diagrams\n- User guides' },
      { emoji: '🔍', role: 'Research Analyst', content: 'Research findings...\n\nEmerging trends:\n- Latest algorithms\n- Industry standards\n- Best practices' },
      { emoji: '🚀', role: 'Innovation Lead', content: 'Innovation opportunities...\n\nFuture possibilities:\n- Emerging technologies\n- Optimization potential\n- Scalability roadmap' },
      { emoji: '💡', role: 'Solution Architect', content: 'Solution design...\n\nArchitecture decisions:\n- Technology stack\n- Integration patterns\n- Scalability design' },
      { emoji: '🔄', role: 'Process Engineer', content: 'Process optimization...\n\nWorkflow improvements:\n- Automation opportunities\n- Efficiency gains\n- Error reduction' },
      { emoji: '📈', role: 'Business Analyst', content: 'Business impact...\n\nBusiness considerations:\n- Cost optimization\n- ROI analysis\n- Market positioning' }
    ]

    // Stream content for each active agent
    for (let i = 1; i <= activeAgentCount; i++) {
      const role = agentRoles[(i - 1) % agentRoles.length]
      await sleep(400 + Math.random() * 400) // Random delay between 400-800ms
      streamContent(`agent-${i}`, `${role.emoji} ${role.content}\n`)
    }

    await sleep(1000)
    streamContent('orchestrator', 'Agents coordinating and sharing insights...\n')

    await sleep(800)
    // Give additional insights to all active agents
    const additionalInsights = [
      '💡 Additional insight: Event-driven architecture enables loose coupling between agents.',
      '🔧 Implementation note: Use circuit breakers to prevent cascade failures.',
      '📈 Metrics: Track coordination latency and throughput for optimization.',
      '🔒 Security note: Implement zero-trust architecture for agent communication.',
      '🧠 AI insight: Use ensemble methods for better decision making.',
      '⚡ Performance tip: Implement async processing for better throughput.',
      '🌐 Network insight: Use service mesh for better observability.',
      '📡 Data tip: Implement event sourcing for better traceability.',
      '🔧 DevOps note: Use blue-green deployment for zero-downtime updates.',
      '🎯 Quality tip: Implement chaos engineering for better resilience.',
      '📝 Documentation note: Keep API schemas version-controlled.',
      '🔍 Research insight: Monitor latest papers for algorithm improvements.',
      '🚀 Innovation tip: Prototype new features in isolated environments.',
      '💡 Architecture note: Design for horizontal scaling from day one.',
      '🔄 Process tip: Automate repetitive tasks to reduce human error.',
      '📈 Business insight: Measure user satisfaction alongside technical metrics.'
    ]
    
    for (let i = 1; i <= activeAgentCount; i++) {
      const insight = additionalInsights[(i - 1) % additionalInsights.length]
      streamContent(`agent-${i}`, `\n${insight}\n`)
    }

    // Phase 3: Voting
    setPhase('voting')
    
    // Set all active agents to voting status
    for (let i = 1; i <= activeAgentCount; i++) {
      updateAgentStatus(`agent-${i}`, 'voting')
    }

    await sleep(500)
    streamContent('orchestrator', '\n🗳️ Voting phase initiated\n')

    await sleep(1000)
    
    // Generate voting patterns for all active agents
    for (let i = 1; i <= activeAgentCount; i++) {
      const targetAgent = ((i % activeAgentCount) + 1) // Circular voting pattern
      const approaches = ['architectural approach', 'implementation strategy', 'performance optimization', 'security measures', 'AI coordination', 'efficiency improvements']
      const approach = approaches[(targetAgent - 1) % approaches.length]
      streamContent('orchestrator', `🗳️ Agent ${i} votes for: Agent ${targetAgent}'s ${approach}\n`)
      await sleep(200)
    }

    await sleep(800)
    const winnerAgent = Math.floor(Math.random() * activeAgentCount) + 1
    const approaches = ['architectural approach', 'implementation strategy', 'performance optimization', 'security measures', 'AI coordination', 'efficiency improvements']
    const winnerApproach = approaches[(winnerAgent - 1) % approaches.length]
    streamContent('orchestrator', `🗳️ Winner: Agent ${winnerAgent} (${winnerApproach}) - selected by orchestrator\n`)

    // Phase 4: Presenting
    setPhase('presenting')
    
    // Set all active agents to completed status
    for (let i = 1; i <= activeAgentCount; i++) {
      updateAgentStatus(`agent-${i}`, 'completed')
    }

    await sleep(500)
    streamContent('orchestrator', '\n🎯 Final Synthesis:\n\n')
    await sleep(800)
    streamContent('orchestrator', 'Based on agent collaboration, the optimal approach combines:\n\n')
    await sleep(1000)
    streamContent('orchestrator', '1. Event-driven Architecture (Agent 1)\n   - Loose coupling between agents\n   - Scalable communication patterns\n\n')
    await sleep(1200)
    streamContent('orchestrator', '2. Robust Implementation (Agent 2)\n   - Message queues for reliability\n   - Circuit breakers for fault tolerance\n   - Container-based isolation\n\n')
    await sleep(1000)
    streamContent('orchestrator', '3. Performance Optimization (Agent 3)\n   - Horizontal scaling strategies\n   - Metrics-driven optimization\n   - Resource allocation efficiency\n\n')
    await sleep(800)
    streamContent('orchestrator', '✅ Coordination complete! Multi-agent consensus achieved.\n')

    setIsRunning(false)
  }

  const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <button
        onClick={runDemo}
        disabled={isRunning}
        className={`px-4 py-2 rounded-lg text-white font-medium transition-colors ${
          isRunning 
            ? 'bg-gray-600 cursor-not-allowed' 
            : 'bg-purple-600 hover:bg-purple-700'
        }`}
      >
        {isRunning ? 'Running Demo...' : 'Run Demo Simulation'}
      </button>
    </div>
  )
}