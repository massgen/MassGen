'use client'

import { usePanelStore } from '@/store/usePanelStore'
import { useState } from 'react'

export default function DemoSimulation() {
  const { streamContent, updateAgentStatus, updatePanelContent, setPhase, setPrompt, setActiveAgentCount, setConfigFile, activeAgentCount } = usePanelStore()
  const [isRunning, setIsRunning] = useState(false)

  const runDemo = async () => {
    if (isRunning) return
    setIsRunning(true)

    // Set up demo environment (preserve current agent count)
    setPrompt("What is the best approach for building a scalable multi-agent coordination system?")
    
    // Clear all agent panels before starting demo
    for (let i = 1; i <= 16; i++) {
      updatePanelContent(`agent-${i}`, `Agent ${i} is initializing...\n`)
      updateAgentStatus(`agent-${i}`, 'idle')
    }
    
    // Generate dynamic config file for all active agents
    const agentBackends = [
      { type: "claude", model: "claude-3.5-sonnet" },
      { type: "gemini", model: "gemini-2.5-flash" },
      { type: "openai", model: "gpt-5-nano" },
      { type: "grok", model: "grok-3-mini" },
      { type: "claude", model: "claude-3.5-haiku" },
      { type: "openai", model: "gpt-4o" },
      { type: "gemini", model: "gemini-pro" },
      { type: "azure", model: "gpt-4-turbo" },
      { type: "openai", model: "gpt-5-mini" },
      { type: "claude", model: "claude-3-opus" },
      { type: "gemini", model: "gemini-ultra" },
      { type: "grok", model: "grok-2" },
      { type: "openai", model: "gpt-4" },
      { type: "claude", model: "claude-instant" },
      { type: "gemini", model: "gemini-flash" },
      { type: "openai", model: "gpt-3.5-turbo" }
    ]
    
    const agentRoleNames = [
      "Architecture specialist", "Implementation expert", "Performance analyst", "Security specialist",
      "AI coordinator", "Efficiency expert", "Network specialist", "Data engineer",
      "DevOps engineer", "Quality assurance", "Documentation specialist", "Research analyst",
      "Innovation lead", "Solution architect", "Process engineer", "Business analyst"
    ]
    
    let configAgents = ""
    for (let i = 1; i <= activeAgentCount; i++) {
      const backend = agentBackends[(i - 1) % agentBackends.length]
      const role = agentRoleNames[(i - 1) % agentRoleNames.length]
      configAgents += `  - id: "agent-${i}"
    backend:
      type: "${backend.type}"
      model: "${backend.model}"
    system_message: "${role}"

`
    }
    
    const sampleConfig = `# Demo Configuration (${activeAgentCount} agents)
agents:
${configAgents}ui:
  display_type: "grid"
  coordination_timeout: 60`
  
    setConfigFile("demo_config.yaml", sampleConfig)

    // Phase 1: Starting
    setPhase('starting')
    await sleep(1000)

    streamContent('orchestrator', 'Demo simulation started\n')
    streamContent('orchestrator', 'Initializing agents...\n')
    
    // Initialize visual log
    streamContent('visual-log', 'PHASE: STARTING\n')
    streamContent('visual-log', 'Initializing demo with agents...\n')
    for (let i = 1; i <= activeAgentCount; i++) {
      streamContent('visual-log', `Agent ${i}: INITIALIZED\n`)
    }

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
    streamContent('visual-log', 'COORDINATION PHASE\n')
    for (let i = 1; i <= activeAgentCount; i++) {
      const role = agentRoles[(i - 1) % agentRoles.length]
      await sleep(400 + Math.random() * 400) // Random delay between 400-800ms
      streamContent(`agent-${i}`, `${role.emoji} ${role.content}\n`)
      
      // Add visual log entry for agent working
      streamContent('visual-log', `Agent ${i}: working\n`)
    }

    await sleep(1000)
    streamContent('orchestrator', 'Agents coordinating and sharing insights...\n')
    
    // Visual log for cross-agent communication
    streamContent('visual-log', 'Communication phase\n')
    for (let i = 1; i <= activeAgentCount; i++) {
      const targetAgent = ((i % activeAgentCount) + 1)
      streamContent('visual-log', `Agent ${i} communicates with Agent ${targetAgent}\n`)
      await sleep(200) // Small delay to see connections appear
    }

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
    
    // Visual log for voting phase
    streamContent('visual-log', 'VOTING PHASE\n')
    for (let i = 1; i <= activeAgentCount; i++) {
      streamContent('visual-log', `Agent ${i}: voting\n`)
    }

    await sleep(1000)
    
    // Generate voting patterns for all active agents
    for (let i = 1; i <= activeAgentCount; i++) {
      const targetAgent = ((i % activeAgentCount) + 1) // Circular voting pattern
      const approaches = ['architectural approach', 'implementation strategy', 'performance optimization', 'security measures', 'AI coordination', 'efficiency improvements']
      const approach = approaches[(targetAgent - 1) % approaches.length]
      streamContent('orchestrator', `🗳️ Agent ${i} votes for: Agent ${targetAgent}'s ${approach}\n`)
      
      // Visual log for each vote
      streamContent('visual-log', `Agent ${i} votes for Agent ${targetAgent}\n`)
      
      await sleep(200)
    }

    await sleep(800)
    const winnerAgent = Math.floor(Math.random() * activeAgentCount) + 1
    const approaches = ['architectural approach', 'implementation strategy', 'performance optimization', 'security measures', 'AI coordination', 'efficiency improvements']
    const winnerApproach = approaches[(winnerAgent - 1) % approaches.length]
    streamContent('orchestrator', `🗳️ Winner: Agent ${winnerAgent} (${winnerApproach}) - selected by orchestrator\n`)
    
    // Visual log for winner announcement
    streamContent('visual-log', `Winner: Agent ${winnerAgent}\n`)
    streamContent('visual-log', `Approach: ${winnerApproach}\n`)

    // Phase 4: Presenting
    setPhase('presenting')
    
    // Set all active agents to completed status
    for (let i = 1; i <= activeAgentCount; i++) {
      updateAgentStatus(`agent-${i}`, 'completed')
    }

    // Visual log for completion
    streamContent('visual-log', 'COMPLETION\n')
    for (let i = 1; i <= activeAgentCount; i++) {
      streamContent('visual-log', `Agent ${i}: completed\n`)
    }

    await sleep(500)
    streamContent('orchestrator', '\n🎯 Final Synthesis:\n\n')
    await sleep(800)
    streamContent('orchestrator', 'Based on agent collaboration, the optimal approach combines insights from all agents:\n\n')
    
    // Generate dynamic synthesis for all active agents
    const synthesisPoints = [
      { title: 'Event-driven Architecture', details: ['Loose coupling between agents', 'Scalable communication patterns', 'Asynchronous processing'] },
      { title: 'Robust Implementation', details: ['Message queues for reliability', 'Circuit breakers for fault tolerance', 'Container-based isolation'] },
      { title: 'Performance Optimization', details: ['Horizontal scaling strategies', 'Metrics-driven optimization', 'Resource allocation efficiency'] },
      { title: 'Security Framework', details: ['Zero-trust architecture', 'Data encryption protocols', 'Access control mechanisms'] },
      { title: 'AI Coordination', details: ['Ensemble decision making', 'Model distribution patterns', 'Training synchronization'] },
      { title: 'Efficiency Engineering', details: ['Resource pooling strategies', 'Caching optimization', 'Network efficiency'] },
      { title: 'Network Architecture', details: ['Load balancing strategies', 'Failover mechanisms', 'Latency optimization'] },
      { title: 'Data Engineering', details: ['Stream processing design', 'Data consistency models', 'Batch operation efficiency'] },
      { title: 'DevOps Integration', details: ['Container orchestration', 'CI/CD pipeline automation', 'Monitoring solutions'] },
      { title: 'Quality Assurance', details: ['Integration testing frameworks', 'Load testing strategies', 'Fault injection methods'] },
      { title: 'Documentation Strategy', details: ['API documentation standards', 'Architecture diagram maintenance', 'User guide development'] },
      { title: 'Research Integration', details: ['Latest algorithm adoption', 'Industry standard compliance', 'Best practice implementation'] },
      { title: 'Innovation Pipeline', details: ['Emerging technology evaluation', 'Optimization potential assessment', 'Scalability roadmap planning'] },
      { title: 'Solution Architecture', details: ['Technology stack decisions', 'Integration pattern design', 'Scalability architecture'] },
      { title: 'Process Engineering', details: ['Workflow automation opportunities', 'Efficiency improvement strategies', 'Error reduction protocols'] },
      { title: 'Business Intelligence', details: ['Cost optimization analysis', 'ROI measurement frameworks', 'Market positioning strategies'] }
    ]
    
    await sleep(1000)
    
    // Show synthesis for each active agent up to the first 5 for readability
    const maxSynthesisShow = Math.min(activeAgentCount, 5)
    for (let i = 1; i <= maxSynthesisShow; i++) {
      const synthesis = synthesisPoints[(i - 1) % synthesisPoints.length]
      streamContent('orchestrator', `${i}. ${synthesis.title} (Agent ${i})\n`)
      synthesis.details.forEach(detail => {
        streamContent('orchestrator', `   - ${detail}\n`)
      })
      streamContent('orchestrator', '\n')
      await sleep(800)
    }
    
    // If more than 5 agents, add a summary line
    if (activeAgentCount > 5) {
      streamContent('orchestrator', `... and ${activeAgentCount - 5} additional specialized insights from remaining agents.\n\n`)
      await sleep(500)
    }
    await sleep(800)
    streamContent('orchestrator', '✅ Coordination complete! Multi-agent consensus achieved.\n')
    
    // Final visual log summary
    streamContent('visual-log', 'SESSION COMPLETE\n')
    streamContent('visual-log', `Final Statistics: ${activeAgentCount} agents, Winner: Agent ${winnerAgent}\n`)

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