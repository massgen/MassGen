'use client'

import { usePanelStore } from '@/store/usePanelStore'
import PanelComponent from './PanelComponent'
import PixiVisualLog from './PixiVisualLog'
// Mosaic import removed - using flexbox for prompt/config panels
// import { Mosaic, MosaicWindow } from 'react-mosaic-component'
// import 'react-mosaic-component/react-mosaic-component.css'

export default function GridLayout() {
  const { panels, activeAgentCount } = usePanelStore()

  const promptPanel = panels.find(p => p.id === 'prompt')
  const configPanel = panels.find(p => p.id === 'config-file')
  const orchestratorPanel = panels.find(p => p.id === 'orchestrator')
  const visualLogPanel = panels.find(p => p.id === 'visual-log')
  const agentPanels = panels.filter(p => p.type.startsWith('agent-') && p.visible)

  // Calculate grid dimensions
  const getGridCols = (count: number) => {
    if (count <= 1) return 1
    if (count <= 4) return 2
    if (count <= 9) return 3
    return 4
  }

  const gridCols = getGridCols(activeAgentCount)
  const gridColsClass = {
    1: 'grid-cols-1',
    2: 'grid-cols-2', 
    3: 'grid-cols-3',
    4: 'grid-cols-4'
  }[gridCols] || 'grid-cols-4'

  // Using flexbox for equal width prompt and config panels

  return (
    <div className="h-screen bg-gray-900 text-white flex flex-col">
      {/* GROUP 1: System Panel (top bar already handled in parent) */}
      
      {/* GROUP 2: Prompt & Config Panels (50/50 flexbox split) */}
      <div className="h-48 bg-gray-900 flex p-4 gap-4">
        <div className="flex-1 w-1/2 min-h-0">
          <PanelComponent panelId="prompt" />
        </div>
        <div className="flex-1 w-1/2 min-h-0">
          <PanelComponent panelId="config-file" />
        </div>
      </div>

      {/* STRONG SEPARATOR between Group 2 and Group 3 */}
      <div className="h-4 bg-gray-500 border-y-2 border-gray-400"></div>

      {/* GROUP 3: Agent Coordination (agents + orchestrator + future history) */}
      <div className="flex-1 bg-gray-900 flex flex-col">
        {/* Agent Grid - Most of the space */}
        <div className="flex-1 p-4">
          <div className={`grid ${gridColsClass} gap-4 h-full`}>
            {agentPanels.map(panel => (
              <div key={panel.id} className="min-h-0">
                <PanelComponent panelId={panel.id} />
              </div>
            ))}
          </div>
        </div>

        {/* Bottom Panels: Orchestrator & Visual Log - side by side */}
        <div className="h-64 p-4 flex gap-4">
          <div className="flex-1 w-1/2 min-h-0">
            {orchestratorPanel && <PanelComponent panelId={orchestratorPanel.id} />}
          </div>
          <div className="flex-1 w-1/2 min-h-0">
            {visualLogPanel && <PixiVisualLog panelId={visualLogPanel.id} />}
          </div>
        </div>
        {/* Space for future history/visual panel */}
      </div>
    </div>
  )
}