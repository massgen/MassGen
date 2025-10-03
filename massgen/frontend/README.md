# MassGen Web UI

The MassGen Web UI provides an interactive web interface for running and monitoring multi-agent workflows, making MassGen accessible to non-technical users and enabling real-time visualization of agent coordination.

## Features

### 🌐 Web Interface
- **Interactive Web UI**: Clean, modern interface built with React and Tailwind CSS
- **Real-time Updates**: WebSocket-based live updates of agent status and coordination
- **Responsive Design**: Works on desktop, tablet, and mobile devices

### 🤖 Agent Coordination Visualization
- **Agent Status Cards**: Live status indicators for each agent (thinking, working, completed, error)
- **Progress Tracking**: Real-time progress bars for individual agents and overall coordination
- **Model Information**: Display of backend type and model for each agent
- **Task Assignment**: Visual indication of current task for each agent

### ⚙️ Configuration Management
- **File Upload**: Support for YAML and JSON configuration files
- **Drag & Drop**: Easy configuration file upload with validation
- **Default Config**: Automatic fallback to OpenAI GPT-4 mini if no config provided
- **Config Validation**: Real-time validation of uploaded configuration files

### 📊 Coordinator Panel
- **Task Submission**: Simple text input for submitting tasks to agents
- **Status Display**: Current task status with coordinator messages
- **Result Display**: Final answers with winning agent identification
- **Error Handling**: Clear error messages and status indicators

### 🔌 Real-time Communication
- **WebSocket Support**: Bi-directional real-time communication
- **Connection Status**: Visual indicator of WebSocket connection status
- **Auto-reconnection**: Automatic reconnection on connection loss
- **Message Types**: Support for various message types (task updates, completions, errors)

## Quick Start

### 1. Start the Web Server

Using the CLI with web mode:

```bash
# Start with default settings (localhost:8000)
python -m massgen.cli --web

# Customize host and port
python -m massgen.cli --web --host 0.0.0.0 --port 3000

# Start with specific backend
python -m massgen.cli --web --backend openai --model gpt-4o
```

### 2. Open the Web Interface

Navigate to `http://localhost:8000` (or your specified host:port) in your web browser.

### 3. Submit a Task

1. **Optional**: Upload a configuration file (YAML or JSON) to customize agent settings
2. **Required**: Enter your task in the text input field
3. **Submit**: Click the "Submit" button to start agent coordination
4. **Monitor**: Watch real-time updates as agents process your task

## Configuration Files

The Web UI supports standard MassGen configuration files in YAML or JSON format.

### Example Configuration (YAML)

```yaml
agents:
  - id: "gpt4_agent"
    backend:
      type: "openai"
      model: "gpt-4o"
      api_key: "${OPENAI_API_KEY}"
    system_message: "You are an expert analyst."
  
  - id: "claude_agent"
    backend:
      type: "claude"
      model: "claude-3-sonnet-20241022"
      api_key: "${ANTHROPIC_API_KEY}"
    system_message: "You are a creative problem solver."

ui:
  display_type: "web"
  logging_enabled: true
```

### Example Configuration (JSON)

```json
{
  "agent": {
    "id": "single_agent",
    "backend": {
      "type": "openai",
      "model": "gpt-4o-mini"
    },
    "system_message": "You are a helpful assistant."
  },
  "ui": {
    "display_type": "web"
  }
}
```

## API Endpoints

The web server exposes several REST API endpoints:

### Health Check
- **GET** `/api/health`: Server health status and active connections

### Task Management
- **POST** `/api/tasks`: Submit a new task for processing
- **GET** `/api/tasks/{task_id}/status`: Get status of a specific task

### Configuration
- **POST** `/api/upload-config`: Upload and validate configuration files

### WebSocket
- **WS** `/ws`: Real-time bidirectional communication

## Architecture

### Backend Components

1. **MassGenWebServer**: FastAPI-based web server
2. **WebSocketManager**: Manages real-time WebSocket connections
3. **WebDisplay**: Integration between orchestrator and web UI
4. **Task Processing**: Asynchronous task processing with real agent responses

### Frontend Components

1. **MassGenApp**: Main React application component
2. **CoordinatorPanel**: Task submission and status display
3. **AgentCard**: Individual agent status visualization
4. **WebSocket Client**: Real-time communication handler

### Message Flow

1. User submits task via web UI
2. Task sent to backend via REST API
3. Backend creates agents and orchestrator
4. Orchestrator processes task with real-time WebSocket updates
5. Web UI receives and displays live status updates
6. Final result displayed with winning agent identification

## Development

### File Structure

```
massgen/frontend/
├── README.md                 # This documentation
├── web_server.py            # FastAPI web server
├── static/
│   └── index.html          # Single-page React application
└── displays/
    ├── base_display.py     # Base display interface
    ├── web_display.py      # Web UI integration
    └── ...                 # Other display types
```

### Adding Features

1. **Backend**: Extend `MassGenWebServer` class in `web_server.py`
2. **Frontend**: Modify React components in `static/index.html`
3. **Real-time**: Add new message types to WebSocket handling
4. **API**: Add new REST endpoints following FastAPI patterns

### Testing

```bash
# Start development server
python -m massgen.cli --web --debug

# Access at http://localhost:8000
# Check browser console for debug messages
# Monitor server logs for backend debugging
```

## Environment Variables

The Web UI respects all standard MassGen environment variables:

- `OPENAI_API_KEY`: For OpenAI backend agents
- `ANTHROPIC_API_KEY`: For Claude backend agents
- `GOOGLE_API_KEY`: For Gemini backend agents
- `XAI_API_KEY`: For Grok backend agents
- And other provider-specific API keys

## Browser Support

- **Modern Browsers**: Chrome 88+, Firefox 85+, Safari 14+, Edge 88+
- **Features Used**: WebSocket, Fetch API, ES6 modules, CSS Grid/Flexbox
- **Mobile**: Responsive design works on iOS Safari and Chrome Mobile

## Troubleshooting

### Common Issues

1. **Connection Failed**: Ensure the web server is running on the correct host/port
2. **Config Upload Error**: Check that your configuration file is valid YAML/JSON
3. **Agent Errors**: Verify API keys are set in environment variables
4. **WebSocket Issues**: Check browser console for connection errors

### Debug Mode

Enable debug mode for detailed logging:

```bash
python -m massgen.cli --web --debug
```

### Browser Developer Tools

- **Console**: Check for JavaScript errors and WebSocket messages
- **Network**: Monitor REST API calls and WebSocket connections
- **Storage**: Inspect any local storage or session data

## Contributing

When contributing to the Web UI:

1. Test on multiple browsers and screen sizes
2. Ensure WebSocket connections are properly managed
3. Add appropriate error handling and user feedback
4. Follow the existing React patterns and Tailwind CSS classes
5. Update this documentation for any new features

## Security Considerations

- **API Keys**: Never expose API keys in the frontend code
- **File Upload**: Configuration files are validated server-side
- **WebSocket**: Connections are authenticated and rate-limited
- **CORS**: CORS is configured for development (customize for production)
- **Input Validation**: All user inputs are validated and sanitized

## Production Deployment

For production deployment:

1. Update CORS settings in `web_server.py`
2. Use HTTPS for secure WebSocket connections (WSS)
3. Configure proper reverse proxy (nginx/Apache)
4. Set appropriate security headers
5. Use environment variables for sensitive configuration
6. Consider rate limiting and authentication