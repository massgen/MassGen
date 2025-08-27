import React, { useEffect, useRef } from 'react';
import { MediaGallery } from './MediaGallery.tsx';
import { AgentInfo, MediaFile } from '../types.ts';

interface HybridTerminalProps {
  agents: AgentInfo[];
  coordinationPhase: 'idle' | 'coordinating' | 'presenting';
  mediaFiles: MediaFile[];
  currentTask: string;
}

export const HybridTerminal: React.FC<HybridTerminalProps> = ({
  agents,
  coordinationPhase,
  mediaFiles,
  currentTask
}) => {
  const terminalOutputRef = useRef<HTMLDivElement>(null);
  const terminalLogs = useRef<string[]>([]);

  // Simple terminal output function
  const writeToTerminal = (message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = `[${timestamp}] ${message}`;
    terminalLogs.current.push(logEntry);
    
    if (terminalOutputRef.current) {
      const div = document.createElement('div');
      div.className = 'terminal-line text-sm font-mono mb-1';
      div.innerHTML = `<span class="text-gray-500">[${timestamp}]</span> ${message}`;
      terminalOutputRef.current.appendChild(div);
      terminalOutputRef.current.scrollTop = terminalOutputRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    // Initialize terminal with welcome message
    writeToTerminal('🚀 <span class="text-green-400">MassGen Studio Terminal</span>');
    writeToTerminal('📡 <span class="text-blue-400">Multimedia coordination interface ready</span>');
    writeToTerminal('');
  }, []);

  // Update terminal when coordination starts
  useEffect(() => {
    if (currentTask && coordinationPhase === 'coordinating') {
      writeToTerminal('<span class="text-yellow-400">=' + '='.repeat(58) + '</span>');
      writeToTerminal('🎯 <span class="text-yellow-400 font-bold">NEW COORDINATION TASK</span>');
      writeToTerminal('<span class="text-yellow-400">=' + '='.repeat(58) + '</span>');
      writeToTerminal(`<span class="text-white">${currentTask}</span>`);
      writeToTerminal('');
      
      if (mediaFiles.length > 0) {
        writeToTerminal(`📎 <span class="text-purple-400">Media files attached: ${mediaFiles.length}</span>`);
        writeToTerminal('');
      }
      
      writeToTerminal('👥 <span class="text-green-400">Initializing agents...</span>');
      writeToTerminal('');
    }
  }, [currentTask, coordinationPhase, mediaFiles]);

  // Update terminal with agent content
  useEffect(() => {
    agents.forEach(agent => {
      if (agent.content.length > 0) {
        const latestContent = agent.content[agent.content.length - 1];
        
        let prefix = '';
        let colorClass = '';
        switch (latestContent.type) {
          case 'thinking': 
            prefix = '💭'; 
            colorClass = 'text-blue-400';
            break;
          case 'tool': 
            prefix = '🔧'; 
            colorClass = 'text-yellow-400';
            break;
          case 'status': 
            prefix = '📊'; 
            colorClass = 'text-green-400';
            break;
          case 'presentation': 
            prefix = '🎤'; 
            colorClass = 'text-purple-400';
            break;
          default:
            prefix = '💬';
            colorClass = 'text-gray-300';
        }
        
        writeToTerminal(
          `${prefix} <span class="text-cyan-400 font-bold">[${agent.id.toUpperCase()}]</span> <span class="${colorClass}">${latestContent.content}</span>`
        );
      }
    });
  }, [agents]);

  const getPhaseMessage = () => {
    switch (coordinationPhase) {
      case 'idle': return '⏸️ Ready for new task';
      case 'coordinating': return '🔄 Coordination in progress...';
      case 'presenting': return '🎯 Presenting final answer';
      default: return '';
    }
  };

  return (
    <div className="hybrid-terminal h-full flex flex-col bg-terminal-bg">
      {/* Media Gallery */}
      {mediaFiles.length > 0 && (
        <div className="media-gallery-container border-b border-gray-700 bg-gray-800">
          <div className="p-2">
            <div className="text-xs text-gray-400 mb-2">📎 Attached Media ({mediaFiles.length})</div>
            <MediaGallery files={mediaFiles} />
          </div>
        </div>
      )}

      {/* Terminal Header */}
      <div className="terminal-header bg-gray-800 border-b border-gray-700 px-4 py-2 flex justify-between items-center">
        <div className="flex items-center space-x-4">
          <span className="text-sm font-mono text-gray-300">🖥️ Terminal</span>
          {agents.length > 0 && (
            <span className="text-xs text-gray-500">
              {agents.length} agent{agents.length > 1 ? 's' : ''} active
            </span>
          )}
        </div>
        <div className="text-xs font-mono text-yellow-400">
          {getPhaseMessage()}
        </div>
      </div>

      {/* Terminal Display */}
      <div className="terminal-container flex-1 relative overflow-hidden">
        <div 
          ref={terminalOutputRef}
          className="absolute inset-0 p-4 bg-black text-green-400 font-mono text-sm overflow-y-auto"
          style={{
            fontFamily: 'JetBrains Mono, Consolas, Monaco, Courier New, monospace',
            lineHeight: '1.4'
          }}
        />
        
        {/* Agent Status Overlay */}
        {coordinationPhase === 'coordinating' && agents.length > 0 && (
          <div className="absolute top-2 right-2 bg-gray-900/80 rounded p-2 text-xs font-mono">
            <div className="text-gray-400 mb-1">Agent Status:</div>
            {agents.map(agent => (
              <div key={agent.id} className="flex items-center space-x-2">
                <span className={`w-2 h-2 rounded-full ${
                  agent.status === 'working' ? 'bg-yellow-400' :
                  agent.status === 'completed' ? 'bg-green-400' :
                  agent.status === 'error' ? 'bg-red-400' :
                  'bg-gray-400'
                }`} />
                <span className="text-gray-300">{agent.id}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};