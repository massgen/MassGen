'use client'

import { useEffect, useRef, useState } from 'react'
import { Application, Graphics, Text, Container } from 'pixi.js'
import { usePanelStore } from '@/store/usePanelStore'

interface VisualLogProps {
  panelId: string
}

interface AgentNode {
  id: number
  x: number
  y: number
  graphics: Graphics
  text: Text
  status: 'idle' | 'working' | 'voting' | 'completed'
}

interface Connection {
  from: number
  to: number
  graphics: Graphics
  timestamp: number
}

export default function PixiVisualLog({ panelId }: VisualLogProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const appRef = useRef<Application | null>(null)
  const agentNodesRef = useRef<Map<number, AgentNode>>(new Map())
  const connectionsRef = useRef<Connection[]>([])
  const containerRef = useRef<Container | null>(null)
  const timelineRef = useRef<number>(0)
  
  const { panels, activeAgentCount } = usePanelStore()
  const panel = panels.find(p => p.id === panelId)
  
  const [isInitialized, setIsInitialized] = useState(false)

  // Colors for different states
  const colors = {
    idle: 0x6B7280,      // gray-500
    working: 0xEAB308,   // yellow-500
    voting: 0xF97316,    // orange-500
    completed: 0x10B981, // green-500
    connection: 0x3B82F6 // blue-500
  }

  useEffect(() => {
    const initPixi = async () => {
      if (!canvasRef.current || appRef.current) return

      try {
        // Create PixiJS application
        const app = new Application()
        // Get the actual container dimensions
        const parentContainer = canvasRef.current.parentElement
        const containerWidth = parentContainer?.clientWidth || 400
        const containerHeight = parentContainer?.clientHeight || 180
        
        await app.init({
          canvas: canvasRef.current,
          width: Math.min(containerWidth, 600), // Cap at reasonable max width
          height: Math.min(containerHeight, 200), // Cap at reasonable max height
          backgroundColor: 0x1F2937, // gray-800
          antialias: true
        })

        appRef.current = app

        // Create main container
        const pixiContainer = new Container()
        app.stage.addChild(pixiContainer)
        containerRef.current = pixiContainer

        // Initialize agent nodes
        updateAgentNodes()
        
        setIsInitialized(true)
      } catch (error) {
        console.error('Failed to initialize PixiJS:', error)
      }
    }

    initPixi()

    return () => {
      if (appRef.current) {
        appRef.current.destroy(true)
        appRef.current = null
      }
    }
  }, [])

  const updateAgentNodes = () => {
    if (!containerRef.current || !appRef.current) return

    const container = containerRef.current
    const app = appRef.current

    // Clear existing nodes
    agentNodesRef.current.forEach(node => {
      container.removeChild(node.graphics)
      container.removeChild(node.text)
    })
    agentNodesRef.current.clear()

    // Create nodes for active agents
    const nodeRadius = 12 // Slightly smaller for better fit
    const margin = 40
    const maxWidth = app.canvas.width - margin
    const spacing = activeAgentCount > 1 ? Math.min(maxWidth / (activeAgentCount - 1), 50) : 0
    const startX = activeAgentCount === 1 ? app.canvas.width / 2 : margin / 2

    for (let i = 1; i <= activeAgentCount; i++) {
      const x = startX + (i - 1) * spacing
      const y = app.canvas.height / 2 // Center vertically

      // Create agent circle
      const graphics = new Graphics()
      graphics.circle(0, 0, nodeRadius)
      graphics.fill(colors.idle)
      graphics.stroke({ color: 0xFFFFFF, width: 2 })
      graphics.position.set(x, y)
      
      // Create agent label
      const text = new Text({
        text: `A${i}`,
        style: {
          fontSize: 9,
          fill: 0xFFFFFF,
          fontFamily: 'Arial',
          fontWeight: 'bold'
        }
      })
      text.anchor.set(0.5)
      text.position.set(x, y)

      const agentNode: AgentNode = {
        id: i,
        x,
        y,
        graphics,
        text,
        status: 'idle'
      }

      container.addChild(graphics)
      container.addChild(text)
      agentNodesRef.current.set(i, agentNode)
    }
  }

  const updateAgentStatus = (agentId: number, status: AgentNode['status']) => {
    const node = agentNodesRef.current.get(agentId)
    if (!node) return

    node.status = status
    
    // Update visual appearance
    node.graphics.clear()
    node.graphics.circle(0, 0, 12)
    node.graphics.fill(colors[status])
    node.graphics.stroke({ color: 0xFFFFFF, width: 2 })

    // Add pulsing effect for working/voting
    if (status === 'working' || status === 'voting') {
      const animate = () => {
        if (node.status === status) {
          node.graphics.scale.set(1 + 0.1 * Math.sin(Date.now() * 0.01))
          requestAnimationFrame(animate)
        } else {
          node.graphics.scale.set(1)
        }
      }
      animate()
    }
  }

  const addConnection = (fromId: number, toId: number, type: 'communication' | 'vote' = 'communication') => {
    if (!containerRef.current) return

    const fromNode = agentNodesRef.current.get(fromId)
    const toNode = agentNodesRef.current.get(toId)
    
    if (!fromNode || !toNode) return

    const graphics = new Graphics()
    
    // Draw connection line
    graphics.moveTo(fromNode.x, fromNode.y)
    graphics.lineTo(toNode.x, toNode.y)
    graphics.stroke({ 
      color: type === 'vote' ? 0xF97316 : colors.connection, 
      width: 2 
    })

    // Add arrowhead
    const angle = Math.atan2(toNode.y - fromNode.y, toNode.x - fromNode.x)
    const arrowLength = 6
    const arrowX = toNode.x - 12 * Math.cos(angle)
    const arrowY = toNode.y - 12 * Math.sin(angle)
    
    graphics.moveTo(arrowX, arrowY)
    graphics.lineTo(
      arrowX - arrowLength * Math.cos(angle - Math.PI / 6),
      arrowY - arrowLength * Math.sin(angle - Math.PI / 6)
    )
    graphics.moveTo(arrowX, arrowY)
    graphics.lineTo(
      arrowX - arrowLength * Math.cos(angle + Math.PI / 6),
      arrowY - arrowLength * Math.sin(angle + Math.PI / 6)
    )
    graphics.stroke({ 
      color: type === 'vote' ? 0xF97316 : colors.connection, 
      width: 2 
    })

    containerRef.current.addChild(graphics)

    const connection: Connection = {
      from: fromId,
      to: toId,
      graphics,
      timestamp: Date.now()
    }

    connectionsRef.current.push(connection)

    // Auto-remove connection after 3 seconds
    setTimeout(() => {
      if (containerRef.current && graphics.parent) {
        containerRef.current.removeChild(graphics)
        connectionsRef.current = connectionsRef.current.filter(c => c !== connection)
      }
    }, 3000)
  }

  const addPhaseIndicator = (phase: string) => {
    if (!containerRef.current || !appRef.current) return

    // Clear existing phase indicators
    const existingIndicators = containerRef.current.children.filter(child => 
      child instanceof Text && (child as any).isPhaseIndicator
    )
    existingIndicators.forEach(indicator => containerRef.current?.removeChild(indicator))

    // Add new phase indicator
    const phaseText = new Text({
      text: `Phase: ${phase.toUpperCase()}`,
      style: {
        fontSize: 12,
        fill: 0xFFFFFF,
        fontFamily: 'Arial',
        fontWeight: 'bold'
      }
    })
    phaseText.position.set(10, 10)
    ;(phaseText as any).isPhaseIndicator = true

    containerRef.current.addChild(phaseText)
  }

  // Listen for panel content changes to trigger visual updates
  useEffect(() => {
    if (!panel || !isInitialized) return

    const content = panel.content
    const lines = content.split('\n')
    
    // Parse different types of interactions from content
    lines.forEach(line => {
      // Agent status updates
      if (line.includes('Agent') && line.includes('working')) {
        const match = line.match(/Agent (\d+)/)
        if (match) {
          updateAgentStatus(parseInt(match[1]), 'working')
        }
      }
      
      if (line.includes('Agent') && line.includes('voting')) {
        const match = line.match(/Agent (\d+)/)
        if (match) {
          updateAgentStatus(parseInt(match[1]), 'voting')
        }
      }
      
      if (line.includes('Agent') && line.includes('completed')) {
        const match = line.match(/Agent (\d+)/)
        if (match) {
          updateAgentStatus(parseInt(match[1]), 'completed')
        }
      }

      // Communication connections
      if (line.includes('communicates with')) {
        const match = line.match(/Agent (\d+) communicates with Agent (\d+)/)
        if (match) {
          addConnection(parseInt(match[1]), parseInt(match[2]))
        }
      }

      // Voting connections
      if (line.includes('votes for')) {
        const match = line.match(/Agent (\d+) votes for Agent (\d+)/)
        if (match) {
          addConnection(parseInt(match[1]), parseInt(match[2]), 'vote')
        }
      }

      // Phase changes
      if (line.includes('COORDINATION PHASE')) {
        addPhaseIndicator('Coordination')
      }
      if (line.includes('VOTING PHASE')) {
        addPhaseIndicator('Voting')
      }
      if (line.includes('COMPLETION')) {
        addPhaseIndicator('Completed')
      }
    })
  }, [panel?.content, isInitialized])

  // Update nodes when activeAgentCount changes
  useEffect(() => {
    if (isInitialized) {
      updateAgentNodes()
    }
  }, [activeAgentCount, isInitialized])

  if (!panel) {
    return (
      <div className="h-full bg-gray-800 border border-gray-700 rounded-lg p-4 flex items-center justify-center">
        <div className="text-red-400">Visual Log panel not found</div>
      </div>
    )
  }

  return (
    <div className="h-full bg-gray-800 border border-gray-700 rounded-lg flex flex-col">
      {/* Panel Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-700 bg-gray-900 rounded-t-lg">
        <div className="flex items-center gap-2">
          <h3 className="text-white font-medium">{panel.title}</h3>
        </div>
        <div className="text-gray-400 text-xs">
          Interactive Visualization
        </div>
      </div>

      {/* PixiJS Canvas */}
      <div className="flex-1 p-2 overflow-hidden">
        <canvas 
          ref={canvasRef}
          className="w-full h-full max-w-full max-h-full"
          style={{ 
            maxHeight: '100%', 
            maxWidth: '100%',
            objectFit: 'contain',
            display: 'block'
          }}
        />
      </div>
    </div>
  )
}