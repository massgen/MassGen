#!/usr/bin/env python3
"""
Web UI server command for MassGen.

Starts a Flask development server with the MassGen Web UI.
"""

import argparse
import os
from .app import create_app
from .websocket_handler import socketio


def main():
    """Main entry point for the web UI server."""
    parser = argparse.ArgumentParser(
        description="MassGen Web UI Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start web UI on default port 5000
  python -m massgen.web_ui.cli_server
  
  # Start on custom port
  python -m massgen.web_ui.cli_server --port 8080
  
  # Enable debug mode
  python -m massgen.web_ui.cli_server --debug
        """
    )
    
    parser.add_argument(
        '--host',
        type=str,
        default='127.0.0.1',
        help='Host to bind the server to (default: 127.0.0.1)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port to run the server on (default: 5000)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    
    args = parser.parse_args()
    
    # Create Flask app
    app = create_app()
    app.config['DEBUG'] = args.debug
    
    print(f"🚀 Starting MassGen Web UI...")
    print(f"📍 URL: http://{args.host}:{args.port}")
    print(f"🔧 Debug mode: {'enabled' if args.debug else 'disabled'}")
    print(f"⭐ Press Ctrl+C to stop")
    
    try:
        # Run with SocketIO support
        socketio.run(
            app,
            host=args.host,
            port=args.port,
            debug=args.debug,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print("\n👋 Shutting down MassGen Web UI")


if __name__ == '__main__':
    main()