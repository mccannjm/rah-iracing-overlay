from flask import Blueprint, render_template, send_from_directory, Response
import os
import sys

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_path, relative_path)

overlays_bp = Blueprint(
    'overlays', __name__,
    template_folder='.',
    static_folder=None 
)

@overlays_bp.route('/<overlay_name>')
def serve_overlay(overlay_name):
    # Validate overlay name to prevent path traversal
    if not overlay_name or '..' in overlay_name or '/' in overlay_name or '\\' in overlay_name:
        return "Invalid overlay name", 400
    
    # Allow only alphanumeric, underscore, and hyphen
    import re
    if not re.match(r'^[a-zA-Z0-9_\-]+$', overlay_name):
        return "Invalid overlay name", 400
    
    html_file_path = os.path.join(resource_path('overlays'), overlay_name, f'{overlay_name}.html')
    
    # Ensure the resolved path is within the overlays directory
    overlays_dir = os.path.abspath(resource_path('overlays'))
    resolved_path = os.path.abspath(html_file_path)
    
    if not resolved_path.startswith(overlays_dir):
        return "Access denied", 403
    
    if os.path.exists(html_file_path):
        # Render the template with transparency support
        rendered_html = render_template(f'{overlay_name}/{overlay_name}.html')
        
        # Return with appropriate headers
        response = Response(rendered_html)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response
    else:
        return "Overlay not found", 404

@overlays_bp.route('/<overlay_name>/static/<path:filename>')
def serve_static(overlay_name, filename):
    # Validate overlay name and filename to prevent path traversal
    import re
    
    if not overlay_name or '..' in overlay_name or '/' in overlay_name or '\\' in overlay_name:
        return "Invalid overlay name", 400
    
    if not re.match(r'^[a-zA-Z0-9_\-]+$', overlay_name):
        return "Invalid overlay name", 400
    
    if not filename or '..' in filename:
        return "Invalid filename", 400
    
    static_folder = os.path.join(resource_path('overlays'), overlay_name, 'static')
    
    # Ensure the resolved path is within the static directory
    static_dir = os.path.abspath(static_folder)
    requested_file = os.path.abspath(os.path.join(static_folder, filename))
    
    if not requested_file.startswith(static_dir):
        return "Access denied", 403
    
    return send_from_directory(static_folder, filename)