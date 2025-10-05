"""
Flask application factory for MassGen Web UI.
"""

import os
from pathlib import Path
from flask import Flask, render_template, send_from_directory
from flask_cors import CORS
from .api import api_bp
from .websocket_handler import socketio


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Configure app
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    
    # Enable CORS for API endpoints
    CORS(app, origins=["http://localhost:3000", "http://127.0.0.1:3000"])
    
    # Register blueprints
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Initialize SocketIO
    socketio.init_app(app, cors_allowed_origins="*")
    
    @app.route('/')
    def index():
        """Serve the main web interface."""
        return render_template('index.html')
    
    @app.route('/favicon.ico')
    def favicon():
        """Serve favicon."""
        return send_from_directory(app.static_folder, 'favicon.ico')
    
    return app