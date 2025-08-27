export interface MediaFile {
  id: string;
  filename: string;
  content_type: string;
  file_path: string;
  thumbnail_path?: string;
  upload_timestamp: string;
  metadata: Record<string, any>;
}

export interface AgentInfo {
  id: string;
  status: 'waiting' | 'working' | 'completed' | 'error';
  backend?: string;
  content: Array<{
    content: string;
    type: string;
    timestamp: string;
  }>;
}

export interface CoordinationState {
  sessionId: string;
  agents: AgentInfo[];
  currentTask: string;
  coordinationPhase: 'idle' | 'coordinating' | 'presenting';
  mediaFiles: MediaFile[];
  orchestratorEvents: Array<{
    event: string;
    timestamp: string;
  }>;
}

export interface WebSocketMessage {
  type: string;
  [key: string]: any;
}

export interface AgentConfig {
  id: string;
  backend: {
    type: string;
    model: string;
  };
  persona?: string;
}