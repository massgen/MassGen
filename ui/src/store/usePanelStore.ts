import { create } from 'zustand'

export type PanelType = 
  | 'prompt'
  | 'config-file'
  | 'orchestrator'
  | 'visual-log'
  | 'agent-1'
  | 'agent-2'
  | 'agent-3'
  | 'agent-4'
  | 'agent-5'
  | 'agent-6'
  | 'agent-7'
  | 'agent-8'
  | 'agent-9'
  | 'agent-10'
  | 'agent-11'
  | 'agent-12'
  | 'agent-13'
  | 'agent-14'
  | 'agent-15'
  | 'agent-16'

export type AgentStatus = 'idle' | 'working' | 'completed' | 'voting'

export interface Panel {
  id: string
  type: PanelType
  title: string
  content: string
  status?: AgentStatus
  visible: boolean
}

export interface PanelStore {
  panels: Panel[]
  activeAgentCount: number
  coordinationPhase: 'starting' | 'coordinating' | 'voting' | 'presenting'
  currentPrompt: string
  selectedConfigFile: string
  
  // Actions
  setActiveAgentCount: (count: number) => void
  updatePanelContent: (id: string, content: string) => void
  updateAgentStatus: (id: string, status: AgentStatus) => void
  streamContent: (id: string, newContent: string) => void
  setPhase: (phase: PanelStore['coordinationPhase']) => void
  setPrompt: (prompt: string) => void
  setConfigFile: (configName: string, content: string) => void
  reset: () => void
}

const createAgentPanels = (): Panel[] => {
  const panels: Panel[] = [
    {
      id: 'prompt',
      type: 'prompt',
      title: '📝 Current Prompt',
      content: 'No prompt yet...\n',
      visible: true,
    },
    {
      id: 'config-file',
      type: 'config-file',
      title: '⚙️ Config File',
      content: 'No config file selected...\n',
      visible: true,
    },
    {
      id: 'orchestrator',
      type: 'orchestrator',
      title: '🎭 Orchestrator',
      content: '=== MassGen Orchestrator ===\nWaiting for coordination to begin...\n',
      visible: true,
    },
    {
      id: 'visual-log',
      type: 'visual-log',
      title: '📊 Visual Log',
      content: '=== Agent Interaction Timeline ===\nWaiting for agent interactions...\n',
      visible: true,
    }
  ]
  
  // Create 16 agent panels
  for (let i = 1; i <= 16; i++) {
    panels.push({
      id: `agent-${i}`,
      type: `agent-${i}` as PanelType,
      title: `🤖 Agent ${i}`,
      content: `Agent ${i} is initializing...\n`,
      status: 'idle',
      visible: false,
    })
  }
  
  return panels
}

export const usePanelStore = create<PanelStore>((set) => ({
  panels: createAgentPanels(),
  activeAgentCount: 3,
  coordinationPhase: 'starting',
  currentPrompt: '',
  selectedConfigFile: '',

  setActiveAgentCount: (count: number) => {
    set(state => ({
      activeAgentCount: Math.min(Math.max(count, 1), 16),
      panels: state.panels.map(p => {
        if (p.type.startsWith('agent-')) {
          const agentNum = parseInt(p.id.split('-')[1])
          return { ...p, visible: agentNum <= count }
        }
        return p
      })
    }))
  },

  updatePanelContent: (id: string, content: string) => {
    set(state => ({
      panels: state.panels.map(p =>
        p.id === id ? { ...p, content } : p
      )
    }))
  },

  updateAgentStatus: (id: string, status: AgentStatus) => {
    set(state => ({
      panels: state.panels.map(p =>
        p.id === id ? { ...p, status } : p
      )
    }))
  },

  streamContent: (id: string, newContent: string) => {
    set(state => ({
      panels: state.panels.map(p =>
        p.id === id ? { ...p, content: p.content + newContent } : p
      )
    }))
  },

  setPhase: (phase: PanelStore['coordinationPhase']) => {
    set({ coordinationPhase: phase })
  },

  setPrompt: (prompt: string) => {
    set(state => ({
      currentPrompt: prompt,
      panels: state.panels.map(p =>
        p.id === 'prompt' ? { ...p, content: prompt + '\n' } : p
      )
    }))
  },

  setConfigFile: (configName: string, content: string) => {
    set(state => ({
      selectedConfigFile: configName,
      panels: state.panels.map(p =>
        p.id === 'config-file' ? { 
          ...p, 
          title: `⚙️ Config File: ${configName}`,
          content: content 
        } : p
      )
    }))
  },

  reset: () => {
    set({
      panels: createAgentPanels(),
      activeAgentCount: 3,
      coordinationPhase: 'starting',
      currentPrompt: '',
      selectedConfigFile: ''
    })
  }
}))