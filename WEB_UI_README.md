# MassGen Web UI

An interactive web interface for MassGen that provides real-time visualization of multi-agent coordination workflows.

## Features

### Core Functionality
- **Interactive Configuration**: Upload YAML/JSON config files or use sample configurations
- **Real-time Agent Monitoring**: Live status updates and output streaming from agents
- **Coordination Visualization**: Timeline of coordination events and agent interactions
- **Solution Comparison**: Side-by-side comparison of agent solutions with voting interface
- **Responsive Design**: Works on desktop and mobile devices

### Technical Features
- **Real-time Communication**: WebSocket-based live updates
- **RESTful API**: Clean API endpoints for all operations
- **Modern UI**: React + Tailwind CSS frontend served via Flask
- **Session Management**: Support for multiple concurrent coordination sessions
- **Error Handling**: Comprehensive error handling and user feedback

## Quick Start

### 1. Install Dependencies

```bash
# Install additional web UI dependencies
pip install Flask>=3.0.0 Flask-CORS>=4.0.0 Flask-SocketIO>=5.3.0 python-socketio>=5.8.0
```

### 2. Start the Web UI Server

```bash
# Start on default port 5000
python -m massgen.web_ui.cli_server

# Custom port and debug mode
python -m massgen.web_ui.cli_server --port 8080 --debug
```

### 3. Access the Interface

Open your browser and navigate to `http://localhost:5000`

## Usage Guide

### Configuration Setup
1. **Upload Config**: Click "Choose File" to upload your YAML/JSON configuration
2. **Use Sample**: Click "Use Sample" for pre-configured single/multi-agent setups
3. **Enter Question**: Type your question or task in the text area
4. **Start Session**: Click "Start Coordination" to begin

### Monitoring Coordination
- **Agent Grid**: Shows real-time status and output from each agent
- **Events Timeline**: Displays coordination events as they happen
- **Progress Indicators**: Visual feedback on agent activity
- **WebSocket Status**: Connection indicator in the header

### Solution Comparison
- **Side-by-side View**: Compare solutions from different agents
- **Voting Interface**: Select the best solution (future enhancement)
- **Detailed Output**: View full agent responses and reasoning

## API Reference

### Core Endpoints

#### Health Check
```http
GET /api/health
```

#### Upload Configuration
```http
POST /api/upload-config
Content-Type: multipart/form-data
```

#### Create Session
```http
POST /api/create-session
Content-Type: application/json

{
  "config": {...},
  "question": "Your question here"
}
```

#### Start Coordination
```http
POST /api/start-coordination
Content-Type: application/json

{
  "session_id": "uuid-here"
}
```

#### Get Session Status
```http
GET /api/session-status/{session_id}
```

#### Stop Session
```http
POST /api/stop-session/{session_id}
```

#### Sample Configurations
```http
GET /api/sample-configs
```

### WebSocket Events

#### Client → Server
- `join_session`: Join a coordination session room
- `leave_session`: Leave a session room

#### Server → Client
- `connected`: Connection confirmation
- `coordination_event`: Coordination process events
- `agent_output`: Real-time agent output
- `voting_event`: Solution comparison data
- `agent_status`: Agent status updates

## Architecture

### Backend (Flask)
- **Flask App**: Main web server with SocketIO integration
- **API Layer**: RESTful endpoints for session management
- **WebSocket Handler**: Real-time communication with clients
- **Integration Layer**: Bridges with existing MassGen CLI/orchestrator

### Frontend (React)
- **Single Page Application**: React components with Tailwind CSS
- **Real-time Updates**: Socket.IO client for live data
- **Responsive Design**: Mobile-friendly interface
- **Component Architecture**: Modular, reusable components

### Data Flow
1. User uploads config and submits question via web interface
2. Backend creates session and initializes agents from config
3. Coordination starts with real-time WebSocket updates
4. Frontend displays live agent status, events, and outputs
5. Final results shown with solution comparison interface

## Sample Configurations

### Single Agent
```yaml
agent:
  id: "agent1"
  backend:
    type: "openai"
    model: "gpt-4o-mini"
  system_message: "You are a helpful AI assistant."
ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

### Multi-Agent
```yaml
agents:
  - id: "analyst"
    backend:
      type: "openai"
      model: "gpt-4o"
    system_message: "You are a data analyst focused on thorough analysis."
  - id: "creative"
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-20241022"
    system_message: "You are a creative thinker focused on innovative solutions."
orchestrator:
  snapshot_storage: ".massgen/snapshots"
  agent_temporary_workspace: ".massgen/temp_workspaces"
  session_storage: ".massgen/sessions"
ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

## Development

### Project Structure
```
massgen/web_ui/
├── __init__.py              # Package initialization
├── app.py                   # Flask application factory
├── api.py                   # REST API endpoints
├── websocket_handler.py     # WebSocket event handling
├── cli_server.py           # CLI server command
├── templates/
│   └── index.html          # React SPA template
└── static/
    └── favicon.ico         # Static assets
```

### Adding New Features
1. **API Endpoints**: Add new routes in `api.py`
2. **WebSocket Events**: Extend `websocket_handler.py`
3. **Frontend Components**: Update the React components in `index.html`
4. **Styling**: Use Tailwind CSS classes for consistent design

## Testing

Run the test suite to verify functionality:

```bash
python test_web_ui.py
```

Tests cover:
- Module imports
- Flask app creation
- API route registration
- WebSocket integration (future)

## Integration with MassGen CLI

The Web UI is designed to work alongside the existing MassGen CLI:
- **Shared Configuration**: Same YAML/JSON config format
- **Agent Compatibility**: Uses same agent backends and orchestrator
- **File System Integration**: Supports context paths and workspace management
- **Logging Integration**: Inherits MassGen's logging configuration

## Future Enhancements

### Planned Features
- **Real-time Voting**: Interactive solution voting interface
- **Advanced Visualization**: Agent interaction graphs and decision trees  
- **Configuration Editor**: Built-in YAML/JSON editor with validation
- **Session History**: Persistent session storage and replay
- **Export Functionality**: Download results in various formats
- **Authentication**: User login and session management
- **Performance Metrics**: Agent execution time and resource usage
- **Custom Themes**: Dark mode and customizable UI themes

### Technical Improvements
- **Database Integration**: PostgreSQL/SQLite for session persistence
- **Caching Layer**: Redis for improved performance
- **Load Balancing**: Support for multiple coordination workers
- **API Versioning**: Structured API versioning for backward compatibility
- **Unit Tests**: Comprehensive test coverage for all components
- **Documentation**: API documentation with Swagger/OpenAPI

## Contributing

This Web UI is part of the MassGen project. Please follow the main project's contributing guidelines when submitting changes.

### Development Setup
1. Clone the MassGen repository
2. Install dependencies: `pip install -r requirements.txt`
3. Install web UI dependencies: `pip install -r requirements_web_ui.txt`
4. Start development server: `python -m massgen.web_ui.cli_server --debug`
5. Access at `http://localhost:5000`

### Code Style
- Follow PEP 8 for Python code
- Use consistent naming conventions
- Add docstrings for all functions and classes
- Use type hints where appropriate