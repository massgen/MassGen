import { WebSocketMessage } from '../types';

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;

  public onCoordinationUpdate?: (message: WebSocketMessage) => void;
  public onConnectionStatus?: (status: 'connecting' | 'connected' | 'disconnected' | 'error') => void;

  constructor(sessionId: string = '') {
    this.sessionId = sessionId || this.generateSessionId();
  }

  private generateSessionId(): string {
    return 'session_' + Math.random().toString(36).substr(2, 9);
  }

  public getSessionId(): string {
    return this.sessionId;
  }

  public connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      this.onConnectionStatus?.('connecting');
      
      const wsUrl = `ws://127.0.0.1:8000/ws/${this.sessionId}`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log(`WebSocket connected: ${this.sessionId}`);
        this.reconnectAttempts = 0;
        this.onConnectionStatus?.('connected');
        resolve();
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.onCoordinationUpdate?.(message);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      this.ws.onclose = () => {
        console.log('WebSocket disconnected');
        this.onConnectionStatus?.('disconnected');
        this.attemptReconnect();
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.onConnectionStatus?.('error');
        reject(error);
      };
    });
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
      
      setTimeout(() => {
        this.connect().catch(console.error);
      }, this.reconnectDelay * this.reconnectAttempts);
    }
  }

  public disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  public async uploadMedia(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`/api/sessions/${this.sessionId}/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }

    return response.json();
  }

  public async startCoordination(task: string, agentConfigs: any[]): Promise<any> {
    const response = await fetch(`/api/sessions/${this.sessionId}/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        task,
        agents: agentConfigs,
      }),
    });

    if (!response.ok) {
      throw new Error(`Start coordination failed: ${response.statusText}`);
    }

    return response.json();
  }

  public async getSessionStatus(): Promise<any> {
    const response = await fetch(`/api/sessions/${this.sessionId}/status`);
    
    if (!response.ok) {
      throw new Error(`Get status failed: ${response.statusText}`);
    }

    return response.json();
  }

  public sendPing(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'ping' }));
    }
  }
}