import React from 'react';
import { AgentInfo } from '../types.ts';

interface AgentCoordinationPanelProps {
  agents: AgentInfo[];
  orchestratorEvents: Array<{
    event: string;
    timestamp: string;
  }>;
  coordinationPhase: 'idle' | 'coordinating' | 'presenting';
}

export const AgentCoordinationPanel: React.FC<AgentCoordinationPanelProps> = ({
  agents,
  orchestratorEvents,
  coordinationPhase
}) => {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'waiting': return '⏳';
      case 'working': return '⚡';
      case 'completed': return '✅';
      case 'error': return '❌';
      default: return '❓';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'waiting': return 'text-gray-400';
      case 'working': return 'text-yellow-400';
      case 'completed': return 'text-green-400';
      case 'error': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <div className="agent-coordination-panel h-full flex flex-col bg-gray-900">
      {/* Header */}
      <div className="border-b border-gray-700 p-4">
        <h3 className="text-lg font-semibold mb-2">🤝 Coordination Panel</h3>
        <div className={`text-sm ${
          coordinationPhase === 'coordinating' ? 'text-yellow-400' :
          coordinationPhase === 'presenting' ? 'text-green-400' :
          'text-gray-400'
        }`}>
          {coordinationPhase === 'coordinating' && '🔄 Active coordination'}
          {coordinationPhase === 'presenting' && '🎯 Presenting results'}
          {coordinationPhase === 'idle' && '💤 Awaiting task'}
        </div>
      </div>

      {/* Agent Status Section */}
      <div className="flex-1 overflow-y-auto p-4">
        <h4 className="text-md font-medium mb-3">👥 Agents ({agents.length})</h4>
        
        {agents.length === 0 ? (
          <div className="text-gray-500 text-sm italic">
            No agents initialized
          </div>
        ) : (
          <div className="space-y-3">
            {agents.map((agent) => (
              <div key={agent.id} className="bg-gray-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <span className={getStatusColor(agent.status)}>
                      {getStatusIcon(agent.status)}
                    </span>
                    <span className="font-medium text-sm">{agent.id.toUpperCase()}</span>
                  </div>
                </div>

                <div className={`text-xs mb-2 ${getStatusColor(agent.status)}`}>
                  Status: {agent.status}
                </div>

                {agent.content.length > 0 && (
                  <div className="text-xs text-gray-400">
                    <div className="font-medium mb-1">Latest:</div>
                    <div className="bg-gray-900 rounded p-2 text-gray-300 text-xs">
                      {agent.content[agent.content.length - 1].content.substring(0, 80)}
                      {agent.content[agent.content.length - 1].content.length > 80 && '...'}
                    </div>
                  </div>
                )}

                <div className="text-xs text-gray-500 mt-2 flex space-x-3">
                  <span>💭 {agent.content.filter(c => c.type === 'thinking').length}</span>
                  <span>🔧 {agent.content.filter(c => c.type === 'tool').length}</span>
                  <span>📊 {agent.content.filter(c => c.type === 'status').length}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Orchestrator Events */}
        <div className="mt-6">
          <h4 className="text-md font-medium mb-3">🎭 Events ({orchestratorEvents.length})</h4>
          
          {orchestratorEvents.length === 0 ? (
            <div className="text-gray-500 text-sm italic">
              No coordination events yet
            </div>
          ) : (
            <div className="space-y-2 max-h-32 overflow-y-auto">
              {orchestratorEvents.slice(-5).reverse().map((event, index) => (
                <div key={index} className="bg-gray-800 rounded p-2">
                  <div className="text-xs text-gray-400 mb-1">
                    {formatTimestamp(event.timestamp)}
                  </div>
                  <div className="text-sm text-gray-300">
                    {event.event}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Footer Stats */}
      <div className="border-t border-gray-700 p-4 bg-gray-800">
        <div className="grid grid-cols-2 gap-4 text-center">
          <div>
            <div className="text-lg font-bold text-blue-400">{agents.length}</div>
            <div className="text-xs text-gray-500">Active Agents</div>
          </div>
          <div>
            <div className="text-lg font-bold text-green-400">{orchestratorEvents.length}</div>
            <div className="text-xs text-gray-500">Events</div>
          </div>
        </div>
        
        {coordinationPhase === 'coordinating' && (
          <div className="mt-3 text-center">
            <div className="text-xs text-yellow-400">
              🔄 Coordination in progress...
            </div>
          </div>
        )}
      </div>
    </div>
  );
};