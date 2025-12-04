import os
import sys
import platform
import time
import threading
import logging
from typing import List, Dict, Optional, Any, Union

using_fallback_mode = False

force_threading = os.environ.get('FORCE_THREADING_MODE', 'false').lower() == 'true'

if force_threading:
    using_fallback_mode = True
    logging.info("Using threading mode due to FORCE_THREADING_MODE environment variable")

elif platform.system() == 'Windows':
    os.environ['EVENTLET_NO_GREENDNS'] = 'yes'
    
    if getattr(sys, 'frozen', False):
        os.environ['EVENTLET_THREADPOOL_SIZE'] = '30'

if not using_fallback_mode:
    try:
        import eventlet
        if platform.system() == 'Windows':
            eventlet.monkey_patch(os=False, thread=False, time=False)
        else:
            eventlet.monkey_patch()
    except ImportError as e:
        logging.warning(f"Cannot import eventlet: {e}")
        logging.info("Falling back to pure threading mode")
        using_fallback_mode = True
    except Exception as e:
        logging.warning(f"Error initializing eventlet: {e}")
        if platform.system() == 'Windows' and getattr(sys, 'frozen', False):
            logging.info("This is likely due to PyInstaller packaging issues with eventlet.")
            logging.info("Falling back to pure threading mode")
        using_fallback_mode = True

from flask import Flask, send_from_directory

if not using_fallback_mode:
    try:
        from flask_socketio import SocketIO, Namespace
    except ImportError:
        logging.warning("Cannot import flask_socketio with eventlet support")
        using_fallback_mode = True

if using_fallback_mode:
    try:
        from flask_socketio import SocketIO, Namespace
    except ImportError as e:
        logging.critical(f"Cannot import flask_socketio: {e}")
        logging.critical("Application cannot run without SocketIO support")
        sys.exit(1)

from data_provider import DataProvider
from interface import interface_bp
from overlays import overlays_bp


def resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    
    Args:
        relative_path: The relative path to the resource
        
    Returns:
        The absolute path to the resource
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


class TelemetryNamespace(Namespace):
    """Socket.IO namespace for telemetry data."""
    
    def on_connect(self) -> None:
        """Handle client connection to telemetry namespace."""
        print("Client connected to telemetry namespace")
        logging.info("Client connected to telemetry namespace")

    def on_disconnect(self) -> None:
        """Handle client disconnection from telemetry namespace."""
        print("Client disconnected from telemetry namespace")
        logging.info("Client disconnected from telemetry namespace")


class DriverInFrontNamespace(Namespace):
    """Socket.IO namespace for driver in front data."""
    
    def on_connect(self) -> None:
        """Handle client connection to driver in front namespace."""
        logging.info("Client connected to driver in front namespace")

    def on_disconnect(self) -> None:
        """Handle client disconnection from driver in front namespace."""
        logging.info("Client disconnected from driver in front namespace")


class WebInterface:
    """
    Manages the web interface for displaying iRacing telemetry overlays.
    
    This class handles the web server, WebSocket connections, and data 
    transmission between the iRacing sim and the overlay interface.
    """

    def __init__(self, selected_overlays: Optional[List[str]] = None) -> None:
        """
        Initialize the web interface.
        
        Args:
            selected_overlays: List of overlay names to enable
        """
        self.selected_overlays = selected_overlays or []
        self.app = Flask(__name__)
        
        # Configure security settings
        self.app.config['MAX_CONTENT_LENGTH'] = 16 * 1024  # 16KB limit
        
        self.app.register_blueprint(interface_bp, url_prefix='/')
        self.app.register_blueprint(overlays_bp, url_prefix='/overlay')
        
        self._configure_socketio()
        self.data_provider = DataProvider()
        self._setup_routes()
        self._setup_security_headers()
        self.telemetry_thread = None
        self.shutdown_flag = False
        self._start_telemetry_thread()
        self._setup_namespaces()

    def _configure_socketio(self) -> None:
        """Configure the Socket.IO server with appropriate settings."""
        socketio_kwargs = {}
        
        if using_fallback_mode or (platform.system() == 'Windows' and getattr(sys, 'frozen', False)):
            socketio_kwargs = {
                'async_mode': 'threading',
                'ping_timeout': 60,
                'ping_interval': 25,
                'cors_allowed_origins': ['http://127.0.0.1:8085', 'http://localhost:8085'],
                'logger': False, 
                'engineio_logger': False
            }
            logging.info("Using threading mode for SocketIO")
        else:
            socketio_kwargs = {
                'async_mode': 'eventlet',
                'cors_allowed_origins': ['http://127.0.0.1:8085', 'http://localhost:8085'],
            }
            logging.info("Using eventlet mode for SocketIO")
            
        self.socketio = SocketIO(self.app, **socketio_kwargs)

    def _setup_namespaces(self) -> None:
        """
        Register Socket.IO namespaces for each overlay by automatically scanning the overlays directory.
        """
        overlays_dir = resource_path('overlays')
        available_overlays = []
        try:
            for item in os.listdir(overlays_dir):
                overlay_path = os.path.join(overlays_dir, item)
                if os.path.isdir(overlay_path) and os.path.exists(os.path.join(overlay_path, f'{item}.html')):
                    print(item)
                    available_overlays.append(item)
        except Exception as e:
            logging.error(f"Error scanning overlays directory: {e}")

        logging.info(f"Found overlays: {available_overlays}")

        for overlay in available_overlays:
            print(overlay)
            if overlay == 'driver_in_front':
                self.socketio.on_namespace(DriverInFrontNamespace(f'/{overlay}'))
                print(f"Registered driver in front namespace: {overlay}")
            elif overlay == 'input_telemetry':
                self.socketio.on_namespace(TelemetryNamespace(f'/{overlay}'))
                print(f"Registered telemetry namespace: {overlay}")

        logging.info(f"Registered Socket.IO namespaces for overlays: {available_overlays}")

    def _setup_routes(self) -> None:
        """
        Set up additional routes for serving common static files.
        """
        @self.app.route('/common/js/<path:filename>')
        def serve_common_js(filename: str):
            # Validate filename to prevent path traversal
            if not filename or '..' in filename:
                return "Invalid filename", 400
            
            common_js_folder = resource_path(os.path.join('common', 'js'))
            
            # Ensure the resolved path is within the common js directory
            js_dir = os.path.abspath(common_js_folder)
            requested_file = os.path.abspath(os.path.join(common_js_folder, filename))
            
            if not requested_file.startswith(js_dir):
                return "Access denied", 403
            
            return send_from_directory(common_js_folder, filename)

    def _setup_security_headers(self) -> None:
        """
        Set up security headers for all responses.
        """
        @self.app.after_request
        def add_security_headers(response):
            # Prevent content type sniffing
            response.headers['X-Content-Type-Options'] = 'nosniff'
            
            # Prevent clickjacking (but allow for overlay windows)
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            
            # Basic XSS protection
            response.headers['X-XSS-Protection'] = '1; mode=block'
            
            # Don't send referrer to external sites
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            
            # Content Security Policy for additional protection
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # Allow inline scripts for SocketIO
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self' ws: wss:; "  # Allow WebSocket connections
                "font-src 'self'"
            )
            
            return response

    def _start_telemetry_thread(self) -> None:
        """
        Start a background thread to emit telemetry data.
        """
        def telemetry_thread() -> None:
            """
            Thread function that processes and emits telemetry data.
            """
            while not self.shutdown_flag:
                try:
                    # Reconnect to iRacing if needed
                    if not self.data_provider.is_connected:
                        self.data_provider.connect()
                        
                    # Process telemetry if connected
                    if self.data_provider.is_connected:
                        self._process_telemetry_data()
                            
                except Exception as e:
                    logging.error(f"Unexpected error in telemetry thread: {e}")
                    
                time.sleep(0.01)  # ~30 FPS

        self.telemetry_thread = threading.Thread(target=telemetry_thread)
        self.telemetry_thread.daemon = True
        self.telemetry_thread.start()
        
    def _process_telemetry_data(self) -> None:
        """Process and emit telemetry and lap time data."""
        try:
            data = self.data_provider.get_telemetry_data()
            if data:
                normalized_data = self._normalize_data(data)
                
                # Standard emission for all modes - keep it simple
                try:
                    self.socketio.emit('telemetry_update', normalized_data, namespace='/input_telemetry')
                except Exception as e:
                    logging.error(f"Error in telemetry processing: {e}")
                
                # Create driver in front data
                driver_data = {
                    'front_last_lap_time': data.get('front_last_lap_time', 0.0),
                    'front_best_lap_time': data.get('front_best_lap_time', 0.0),
                    'lap_delta': data.get('lap_delta', 0.0),
                    'target_pace': data.get('target_pace', 0.0),
                    'session_type': data.get('session_type', 'race')
                }
                
                try:
                    self.socketio.emit('driver_in_front_update', driver_data, namespace='/driver_in_front')
                except Exception as e:
                    logging.error(f"Error in driver in front processing: {e}")
                
        except Exception as e:
            logging.error(f"Error in telemetry processing: {e}")
    
    def _normalize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize telemetry data to ensure all values are of correct type.
        
        Args:
            data: Raw telemetry data dictionary
            
        Returns:
            Dict[str, Any]: Normalized data dictionary
        """
        normalized = {}
        for key, value in data.items():
            if key == 'gear':
                normalized[key] = int(value) if value is not None else 0
            elif value is None:
                normalized[key] = 0.0
            else:
                try:
                    normalized[key] = float(value)
                except (TypeError, ValueError):
                    normalized[key] = 0.0
        return normalized

    def run(self, host: str = '127.0.0.1', port: int = 8085) -> None:
        """
        Run the Flask application.
        
        Args:
            host: The hostname to listen on
            port: The port of the webserver
        """
        # Always connect to iRacing first
        self.data_provider.connect()
        
        # Run the appropriate server mode
        if using_fallback_mode or (platform.system() == 'Windows' and getattr(sys, 'frozen', False)):
            self._run_with_threading(host, port)
        else:
            self._run_with_eventlet(host, port)
            
    def _run_with_threading(self, host: str, port: int) -> None:
        """
        Run the server using threading mode.
        
        Args:
            host: The hostname to listen on
            port: The port of the webserver
        """
        try:
            logging.info(f"Starting SocketIO server with threading mode on {host}:{port}...")
            self.socketio.run(self.app, host=host, port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
        except TypeError as e:
            # Fall back to simpler config if the newer parameters aren't supported
            logging.error(f"Error with SocketIO run parameters: {e}")
            try:
                self.socketio.run(self.app, host=host, port=port)
            except Exception as e:
                logging.critical(f"Critical error starting SocketIO server: {e}")
                sys.exit(1)
        except Exception as e:
            logging.error(f"Error starting SocketIO server: {e}")
            sys.exit(1)
            
    def _run_with_eventlet(self, host: str, port: int) -> None:
        """
        Run the server using eventlet mode.
        
        Args:
            host: The hostname to listen on
            port: The port of the webserver
        """
        try:
            self.socketio.run(self.app, host=host, port=port)
        except Exception as e:
            logging.warning(f"Error in eventlet mode, falling back to threading: {e}")
            self.socketio = SocketIO(self.app, async_mode='threading')
            self.socketio.run(self.app, host=host, port=port, debug=False, use_reloader=False)
        
    def shutdown(self) -> None:
        """
        Shutdown the web interface properly.
        """
        logging.info("Shutting down web interface...")
        
        self.shutdown_flag = True
        if self.telemetry_thread and self.telemetry_thread.is_alive():
            try:
                self.telemetry_thread.join(timeout=2)
            except Exception:
                pass
            
        if self.data_provider:
            self.data_provider.disconnect()
            
        try:
            self.socketio.stop()
        except Exception as e:
            logging.error(f"Error stopping SocketIO: {e}")
        
        logging.info("Web interface shutdown complete") 