'use client'

import { usePanelStore } from '@/store/usePanelStore'
import { useState, useEffect } from 'react'

// Config files will be loaded dynamically from the API
type ConfigFiles = Record<string, string>

export default function NewCommandCenter() {
  const { activeAgentCount, coordinationPhase, setActiveAgentCount, setPrompt, reset, setConfigFile } = usePanelStore()
  const [promptInput, setPromptInput] = useState('')
  const [configFiles, setConfigFiles] = useState<ConfigFiles>({})
  const [isLoadingConfigs, setIsLoadingConfigs] = useState(true)

  // Load config files on component mount
  useEffect(() => {
    const loadConfigFiles = async () => {
      try {
        const response = await fetch('/api/configs')
        if (response.ok) {
          const data = await response.json()
          setConfigFiles(data.configs || {})
        } else {
          console.error('Failed to load config files')
        }
      } catch (error) {
        console.error('Error loading config files:', error)
      } finally {
        setIsLoadingConfigs(false)
      }
    }

    loadConfigFiles()
  }, [])

  const handlePromptSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (promptInput.trim()) {
      setPrompt(promptInput.trim())
    }
  }

  const getPhaseColor = () => {
    switch (coordinationPhase) {
      case 'starting': return 'bg-gray-600'
      case 'coordinating': return 'bg-blue-600'
      case 'voting': return 'bg-orange-600'
      case 'presenting': return 'bg-green-600'
      default: return 'bg-gray-600'
    }
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-gray-900 border-b border-gray-700 p-3">
      <div className="flex items-center justify-between gap-4">
        {/* Left: Phase and Status */}
        <div className="flex items-center gap-3">
          <div className="text-white font-bold text-lg">MassGen</div>
          <div className={`px-3 py-1 rounded-full text-sm text-white ${getPhaseColor()}`}>
            {coordinationPhase.toUpperCase()}
          </div>
          <div className="text-gray-400 text-sm">
            {activeAgentCount} agent{activeAgentCount !== 1 ? 's' : ''} active
          </div>
        </div>

        {/* Center: Prompt Input */}
        <form onSubmit={handlePromptSubmit} className="flex-1 max-w-2xl">
          <div className="flex gap-2">
            <input
              type="text"
              value={promptInput}
              onChange={(e) => setPromptInput(e.target.value)}
              placeholder="Enter prompt for coordination..."
              className="flex-1 px-3 py-1 bg-gray-800 border border-gray-600 rounded text-white text-sm placeholder-gray-400 focus:outline-none focus:border-blue-500"
            />
            <button
              type="submit"
              className="px-4 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors"
            >
              Send
            </button>
          </div>
        </form>

        {/* Right: Config, Agent Count and Controls */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-gray-400 text-sm">Config:</label>
            <select
              onChange={(e) => {
                const configName = e.target.value
                if (configName && configFiles[configName]) {
                  setConfigFile(configName, configFiles[configName])
                }
              }}
              className="px-2 py-1 bg-gray-800 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-blue-500"
              disabled={isLoadingConfigs}
            >
              <option value="">
                {isLoadingConfigs ? 'Loading configs...' : 'Select Config'}
              </option>
              {Object.keys(configFiles).sort().map(configName => (
                <option key={configName} value={configName}>{configName}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-gray-400 text-sm">Agents:</label>
            <select
              value={activeAgentCount}
              onChange={(e) => setActiveAgentCount(parseInt(e.target.value))}
              className="px-2 py-1 bg-gray-800 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-blue-500"
            >
              {Array.from({ length: 16 }, (_, i) => i + 1).map(num => (
                <option key={num} value={num}>{num}</option>
              ))}
            </select>
          </div>
          <button
            onClick={reset}
            className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700 transition-colors"
          >
            Reset
          </button>
        </div>
      </div>
    </div>
  )
}