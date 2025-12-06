"""
Core modules for RAH iRacing Telemetry Overlay.

This package contains the core functionality including:
- web_interface: Flask/SocketIO server
- data_provider: iRacing SDK interface
- overlay_window: pywebview window management
- validation: Input validation schemas
- tire prediction system components
"""

__all__ = [
    'WebInterface',
    'DataProvider',
    'OverlayWindow',
]
