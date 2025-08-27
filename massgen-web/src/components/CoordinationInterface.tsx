import React, { useState, useEffect, useRef } from 'react';
import { WebSocketManager } from '../services/websocket.ts';
import { MultimediaInput } from './MultimediaInput.tsx';
import { HybridTerminal } from './HybridTerminal.tsx';
import { AgentCoordinationPanel } from './AgentCoordinationPanel.tsx';
import { CoordinationState, WebSocketMessage, AgentInfo, MediaFile, AgentConfig } from '../types.ts';

export const CoordinationInterface: React.FC = () => {
  const [state, setState] = useState<CoordinationState>({
    sessionId: '',
    agents: [],
    currentTask: '',
    coordinationPhase: 'idle',
    mediaFiles: [],
    orchestratorEvents: []
  });

  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected');
  const wsManager = useRef<WebSocketManager>();

  useEffect(() => {
    // Initialize WebSocket connection
    wsManager.current = new WebSocketManager();
    
    wsManager.current.onCoordinationUpdate = handleCoordinationUpdate;
    wsManager.current.onConnectionStatus = setConnectionStatus;

    // Connect to WebSocket
    wsManager.current.connect().catch(console.error);

    // Set session ID
    setState(prev => ({
      ...prev,
      sessionId: wsManager.current!.getSessionId()
    }));

    // Cleanup on unmount
    return () => {
      wsManager.current?.disconnect();
    };
  }, []);

  const handleCoordinationUpdate = (message: WebSocketMessage) => {
    console.log('Received message:', message);

    switch (message.type) {
      case 'coordination_started':
        setState(prev => ({
          ...prev,
          currentTask: message.task,
          coordinationPhase: 'coordinating',
          agents: message.agents.map((agentId: string) => ({
            id: agentId,
            status: 'waiting' as const,
            content: []
          })),
          mediaFiles: message.media_files || []
        }));
        break;

      case 'agent_content_update':
        setState(prev => ({
          ...prev,
          agents: prev.agents.map(agent => 
            agent.id === message.agent_id 
              ? {
                  ...agent,
                  content: [...agent.content, {
                    content: message.content,
                    type: message.content_type,
                    timestamp: message.timestamp
                  }]
                }
              : agent
          )
        }));
        break;

      case 'agent_status_update':
        setState(prev => ({
          ...prev,
          agents: prev.agents.map(agent =>
            agent.id === message.agent_id
              ? { ...agent, status: message.status }
              : agent
          )
        }));
        break;

      case 'orchestrator_event':
        setState(prev => ({
          ...prev,
          orchestratorEvents: [...prev.orchestratorEvents, {
            event: message.event,
            timestamp: message.timestamp
          }]
        }));
        break;

      case 'final_answer':
        setState(prev => ({
          ...prev,
          coordinationPhase: 'presenting'
        }));
        break;

      case 'coordination_completed':
        setState(prev => ({
          ...prev,
          coordinationPhase: 'idle'
        }));
        break;

      case 'media_uploaded':
        setState(prev => ({
          ...prev,
          mediaFiles: [...prev.mediaFiles, message.media_file]
        }));
        break;

      case 'pong':
        // Handle ping response
        break;

      default:
        console.log('Unknown message type:', message.type);
    }
  };

  const handleMediaUpload = async (files: File[]) => {
    if (!wsManager.current) return;

    for (const file of files) {
      try {
        await wsManager.current.uploadMedia(file);
      } catch (error) {
        console.error('Upload error:', error);
      }
    }
  };

  const handleTaskSubmit = async (task: string) => {
    if (!wsManager.current || !task.trim()) return;

    const defaultAgentConfigs: AgentConfig[] = [
      {
        id: 'analyst',
        backend: { type: 'openai', model: 'gpt-4o-mini' },
        persona: 'You are an analytical assistant focused on breaking down complex problems.'
      },
      {
        id: 'researcher', 
        backend: { type: 'openai', model: 'gpt-4o-mini' },
        persona: 'You are a research assistant focused on gathering comprehensive information.'
      }
    ];

    try {
      await wsManager.current.startCoordination(task, defaultAgentConfigs);
    } catch (error) {
      console.error('Start coordination error:', error);
    }
  };

  const getConnectionStatusColor = () => {
    switch (connectionStatus) {
      case 'connected': return 'text-green-400';
      case 'connecting': return 'text-yellow-400';
      case 'error': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getConnectionStatusText = () => {
    switch (connectionStatus) {
      case 'connected': return '🟢 Connected';
      case 'connecting': return '🟡 Connecting...';
      case 'error': return '🔴 Error';
      default: return '⚪ Disconnected';
    }
  };

  return (
    <div className="coordination-interface h-screen bg-gray-900 text-white flex flex-col">
      {/* Header */}
      <div className="bg-gray-800 border-b border-gray-700 p-3 flex justify-between items-center">
        <div>
          <h1 className="text-xl font-bold">🚀 MassGen Studio</h1>
          <p className="text-sm text-gray-400">Session: {state.sessionId}</p>
        </div>
        <div className={`text-sm ${getConnectionStatusColor()}`}>
          {getConnectionStatusText()}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 grid grid-cols-12 overflow-hidden">
        {/* Input Panel */}
        <div className="col-span-3 border-r border-gray-700 flex flex-col">
          <MultimediaInput 
            onTaskSubmit={handleTaskSubmit}
            onMediaUpload={handleMediaUpload}
            mediaFiles={state.mediaFiles}
            disabled={connectionStatus !== 'connected'}
          />
        </div>

        {/* Main Coordination Display */}
        <div className="col-span-6 flex flex-col">
          <HybridTerminal 
            agents={state.agents}
            coordinationPhase={state.coordinationPhase}
            mediaFiles={state.mediaFiles}
            currentTask={state.currentTask}
          />
        </div>

        {/* Agent Status Panel */}
        <div className="col-span-3 border-l border-gray-700 flex flex-col">
          <AgentCoordinationPanel 
            agents={state.agents}
            orchestratorEvents={state.orchestratorEvents}
            coordinationPhase={state.coordinationPhase}
          />
        </div>
      </div>
    </div>
  );
};

export default CoordinationInterface;