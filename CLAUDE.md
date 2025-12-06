# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAH iRacing Overlay is a Python-based real-time telemetry overlay system for iRacing. It provides a Flask/SocketIO backend that streams telemetry data from the iRacing SDK to multiple browser-based overlays that can be displayed in OBS or as standalone windows.

**Key Technologies:** Python 3.10+, Flask 3.1.2, Flask-SocketIO, pyirsdk, eventlet (with fallback to threading), pywebview

## Build and Development Commands

### Environment Setup
```bash
# Automated setup (recommended)
python3 setup_environment.py

# Simple installation
python3 install_requirements.py

# Manual installation
pip3 install -r requirements.txt
```

### Running the Application
```bash
# Development mode
cd src
python3 app.py

# The app will start a Flask server on port 8085
# A GUI interface window will open to manage overlays
```

### Building for Distribution
```bash
# From repository root
python3 scripts/build_exe.py

# Or from src directory
python3.10 build_exe.py

# Output: dist/RAH_Telemetry_Overlay/RAH_Telemetry_Overlay.exe
# Uses PyInstaller with spec file: src/config/RAH_Telemetry_Overlay.spec
```

## Architecture

### Three-Tier System Architecture

1. **Data Layer** (`src/core/data_provider.py`)
   - Connects to iRacing SDK via `pyirsdk`
   - Polls telemetry at ~30 FPS
   - Extracts and normalizes telemetry data
   - Provides data to both web interface and overlays

2. **Web Server Layer** (`src/core/web_interface.py`)
   - Flask application with SocketIO for real-time communication
   - Uses eventlet async mode (falls back to threading on Windows/PyInstaller)
   - Runs background telemetry thread that emits data to SocketIO namespaces
   - Serves static files for overlays

3. **Overlay Layer** (Browser-based)
   - Each overlay is a separate namespace (`/overlay_name`)
   - Receives real-time updates via SocketIO
   - Can run in pywebview windows or browser for OBS
   - Auto-discovered from `src/overlays/` directory

### Critical Architecture Details

#### SocketIO Namespace System
Each overlay gets its own namespace registered in `web_interface.py._setup_namespaces()`:
- Namespaces are auto-registered by scanning `src/overlays/` for directories
- Each overlay must have a corresponding `Namespace` class (e.g., `TelemetryNamespace`, `StandingsNamespace`)
- Data is emitted to namespaces in `_process_telemetry_data()` method

#### Telemetry Flow
```
iRacing SDK → DataProvider → WebInterface._process_telemetry_data() → SocketIO.emit() → Overlay JS
```

Key method: `web_interface.py:271-350` processes telemetry and emits to all active overlay namespaces.

#### Async Mode Handling
The system has sophisticated async mode detection:
- **Production (PyInstaller on Windows)**: Forces threading mode due to eventlet/PyInstaller incompatibilities
- **Development**: Prefers eventlet for better performance
- Controlled by `FORCE_THREADING_MODE` environment variable
- See `web_interface.py:9-40` for fallback logic

### Tire Temperature Prediction System

A 4-layer ML prediction system provides tire temperature forecasts when actual temps are unavailable:

**Layer 1: Physics Model** (`tire_physics_model.py`)
- Real-time thermodynamic calculations
- Heat generation from throttle, brake, lateral G, speed
- Cooling from airflow
- Load transfer adjustments
- Always active, provides baseline predictions

**Layer 2-3: Pattern Learning** (`tire_pattern_learner.py`)
- Learns car class patterns (stint progression, optimal ranges)
- Learns track-specific patterns (corner heating, stint curves)
- Stores patterns in `data/calibrations/`

**Layer 4: ML Models** (`tire_model_trainer.py`)
- GradientBoostingRegressor with 12 models per car (4 tires × 3 zones)
- Trains on pit entry data (ground truth)
- Models stored in `data/models/`

**Coordinator** (`tire_predictor.py`)
- Blends all 4 layers with confidence-based weighting
- Provides trends, advice, and confidence indicators
- Integrated into DataProvider lifecycle

**Data Collection** (`tire_data_collector.py`)
- Records telemetry at 1Hz during sessions
- Captures ground truth temps at pit entries
- Compresses and stores to `data/sessions/`

**Storage Management** (`storage_manager.py`)
- 100MB total budget
- Synthesizes old sessions before deletion (preserves knowledge)
- Automatic cleanup with retention policies

**Session Management:**
- Auto-starts when `SessionNum` changes in iRacing
- Auto-stops and triggers learning when session ends
- Background model training after sessions
- See `data_provider.py:711-737` for session change detection

## Creating New Overlays

Overlays are auto-discovered from `src/overlays/` directory. See `src/overlays/README.md` for detailed instructions.

**Required structure:**
```
src/overlays/my_overlay/
├── my_overlay.html              # Main HTML template
├── properties.json              # Overlay config (resolution, position, DPI)
└── static/
    ├── my_overlay.css
    ├── my_overlay.js            # SocketIO client code
    └── images/ (optional)
```

**Integration steps:**
1. Create overlay directory with required files
2. Add namespace class to `web_interface.py` (e.g., `class MyOverlayNamespace(Namespace)`)
3. Register namespace in `_setup_namespaces()` method
4. Add data emission in `_process_telemetry_data()` method
5. Optionally add data extraction methods to `data_provider.py`

**Key patterns:**
- Use `url_for('overlays.serve_static', overlay_name='...', filename='...')` for static files
- Use `url_for('serve_common_js', filename='socket.io.min.js')` for common JS
- Add `.pywebview-drag-region` class to draggable elements
- Always validate received data in JavaScript

## File Locations

**Core system:**
- `src/app.py` - Main entry point, manages processes
- `src/core/web_interface.py` - Flask/SocketIO server
- `src/core/data_provider.py` - iRacing SDK interface
- `src/core/overlay_window.py` - pywebview window management
- `src/core/validation.py` - Marshmallow schemas for security

**Tire prediction system:**
- `src/core/tire_predictor.py` - Main coordinator
- `src/core/tire_data_collector.py` - Session data recording
- `src/core/tire_physics_model.py` - Physics-based predictions
- `src/core/tire_pattern_learner.py` - Pattern recognition
- `src/core/tire_model_trainer.py` - ML model training
- `src/core/storage_manager.py` - Data lifecycle management

**Interface:**
- `src/interface/` - Flask blueprint for main GUI interface
- `src/interface/templates/` - Interface HTML templates
- `src/interface/static/` - Interface CSS/JS/images

**Overlays:**
- `src/overlays/input_telemetry/` - Steering/throttle/brake display
- `src/overlays/driver_in_front/` - Gap and pace tracking
- `src/overlays/standings/` - Race position and timing
- `src/overlays/tire_temps/` - Tire temperatures with predictions

**Common resources:**
- `src/common/js/socket.io.min.js` - Shared Socket.IO client

**Build config:**
- `src/config/RAH_Telemetry_Overlay.spec` - PyInstaller spec
- `scripts/build_exe.py` - Build script

## Important Implementation Notes

### Windows-Specific Behavior
- `pywin32` is required for Windows builds
- DLL files may need to be unblocked after download (see README.md)
- eventlet is disabled by default on Windows/PyInstaller builds

### Security Features
- Input validation with Marshmallow schemas (`validation.py`)
- CORS restricted to localhost:8085
- Path traversal protection on file serving
- Security headers (CSP, X-Frame-Options, etc.)
- File size limits (16KB for config uploads)

### Resource Paths
Use `resource_path()` helper for PyInstaller compatibility:
```python
def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS  # PyInstaller temp folder
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)
```

### Data Emission Pattern
All overlay data should be emitted in `_process_telemetry_data()`:
```python
# Get data from provider
data = self.data_provider.get_telemetry_data()

# Create overlay-specific data dict
overlay_data = {
    'field1': data.get('field1', 0),
    'field2': data.get('field2', 0)
}

# Emit to namespace
try:
    self.socketio.emit('overlay_update', overlay_data, namespace='/overlay_name')
except Exception as e:
    logging.error(f"Error in overlay processing: {e}")
```

### Tire Prediction Integration
When adding tire temperature features to overlays:
- Use `data_provider.get_tire_predictions()` for predictions
- Use `data_provider.get_tire_data()` for actual temps (in pit only)
- Predictions include: `temps`, `confidence`, `trends`, `advice`
- Always check `in_pit` flag to determine data source

## Debugging

### Common Issues
- **"Cannot import eventlet"**: Expected on Windows/PyInstaller, system falls back to threading
- **SocketIO connection failures**: Check if port 8085 is available, verify CORS settings
- **Overlay not appearing**: Check `_setup_namespaces()` registration and console logs
- **PyInstaller missing files**: Add to `datas` list in `.spec` file

### Logging
All components use Python `logging` module. Check console output for connection/data flow issues.

## Testing Approach

Since this interfaces with iRacing SDK:
- **Unit tests**: Test data parsing and validation logic
- **Integration tests**: Test with mock iRacing SDK data
- **Live tests**: Test with actual iRacing session running

The tire prediction system stores training data, so test with multiple sessions to verify learning behavior.
