'use client'

import { usePanelStore } from '@/store/usePanelStore'
import { useEffect, useRef } from 'react'

interface PanelComponentProps {
  panelId: string
}

export default function PanelComponent({ panelId }: PanelComponentProps) {
  const { panels } = usePanelStore()
  const scrollRef = useRef<HTMLDivElement>(null)
  
  const panel = panels.find(p => p.id === panelId)
  
  useEffect(() => {
    // Auto-scroll to bottom when content updates
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [panel?.content])

  if (!panel) {
    return (
      <div className="h-full bg-gray-800 border border-gray-700 rounded-lg p-4">
        <div className="text-red-400">Panel not found: {panelId}</div>
      </div>
    )
  }

  const getStatusColor = () => {
    if (!panel.status) return 'bg-gray-600'
    
    switch (panel.status) {
      case 'idle': return 'bg-gray-600'
      case 'working': return 'bg-yellow-600'
      case 'completed': return 'bg-green-600'
      case 'voting': return 'bg-orange-600'
      default: return 'bg-gray-600'
    }
  }

  const formatContent = (content: string) => {
    // Basic formatting for different content types
    return content
  }

  return (
    <div className="h-full bg-gray-800 border border-gray-700 rounded-lg flex flex-col">
      {/* Panel Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-700 bg-gray-900 rounded-t-lg">
        <div className="flex items-center gap-2">
          <h3 className="text-white font-medium">{panel.title}</h3>
          {panel.status && (
            <span className={`px-2 py-1 rounded-full text-xs text-white ${getStatusColor()}`}>
              {panel.status}
            </span>
          )}
        </div>
        <div className="text-gray-400 text-xs">
          {panel.content.split('\n').length - 1} lines
        </div>
      </div>

      {/* Panel Content */}
      <div 
        ref={scrollRef}
        className="flex-1 p-4 overflow-auto text-sm text-gray-300 font-mono leading-relaxed"
      >
        <pre className="whitespace-pre-wrap break-words">
          {formatContent(panel.content)}
        </pre>
      </div>
    </div>
  )
}