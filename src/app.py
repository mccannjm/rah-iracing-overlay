import os
import sys
import platform
import logging
import traceback
from datetime import datetime

# Setup logging to file before anything else
log_dir = os.path.join(os.path.expanduser('~'), 'RAH_Telemetry_Overlay_Logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'app_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')

# Configure logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logging.info("="*60)
logging.info("RAH iRacing Telemetry Overlay Starting")
logging.info(f"Log file: {log_file}")
logging.info(f"Python version: {sys.version}")
logging.info(f"Platform: {platform.system()} {platform.release()}")
logging.info(f"Frozen: {getattr(sys, 'frozen', False)}")
if hasattr(sys, '_MEIPASS'):
    logging.info(f"PyInstaller temp dir: {sys._MEIPASS}")
logging.info("="*60)

# Windows-specific configuration for eventlet
if platform.system() == 'Windows':
    # Patch environment before importing eventlet
    os.environ['EVENTLET_NO_GREENDNS'] = 'yes'
    # Force using threading mode for reliability
    os.environ['FORCE_THREADING_MODE'] = 'true'
    logging.info("Windows detected - configured eventlet settings")

try:
    from core.web_interface import WebInterface, using_fallback_mode
    logging.info("Successfully imported web_interface from core")
except Exception as e:
    logging.error(f"Failed to import web_interface: {e}")
    logging.error(traceback.format_exc())
    raise

try:
    from core.overlay_window import OverlayWindow
    logging.info("Successfully imported overlay_window from core")
except Exception as e:
    logging.error(f"Failed to import overlay_window: {e}")
    logging.error(traceback.format_exc())
    raise

import multiprocessing
import atexit
import signal
import time
import importlib
import subprocess
import threading

overlay_processes = []
web_interface_process = None
exit_flag = multiprocessing.Value('i', 0)  # Shared flag to signal program exit

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

def detect_overlays():
    """
    Detect available overlays in the overlays directory.
    """
    try:
        overlays_dir = resource_path('overlays')
        logging.info(f"Looking for overlays in: {overlays_dir}")

        if not os.path.exists(overlays_dir):
            logging.error(f"Overlays directory not found: {overlays_dir}")
            return []

        overlays = [name for name in os.listdir(overlays_dir) if os.path.isdir(os.path.join(overlays_dir, name))]
        logging.info(f"Found {len(overlays)} overlays: {overlays}")
        return overlays
    except Exception as e:
        logging.error(f"Error detecting overlays: {e}")
        logging.error(traceback.format_exc())
        return []

def cleanup():
    """
    Cleanup function to terminate all processes on exit
    """
    print("Cleaning up resources...")
    
    try:
        from interface import opened_overlays
        print(f"Found {len(opened_overlays)} active overlay windows to close")
        
        for overlay_name, process in opened_overlays.items():
            try:
                if process and process.is_alive():
                    print(f"Terminating overlay: {overlay_name}")
                    process.terminate()
                    process.join(timeout=1)
            except Exception as e:
                print(f"Error closing overlay {overlay_name}: {e}")
    except Exception as e:
        print(f"Error accessing opened overlays: {e}")
    
    for process in overlay_processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
    
    if web_interface_process and web_interface_process.is_alive():
        web_interface_process.terminate()
        web_interface_process.join(timeout=1)
    
    print("All processes terminated successfully")

def signal_handler(sig, frame):
    """
    Handle termination signals
    """
    print(f"Received signal {sig}, shutting down...")
    cleanup()
    sys.exit(0)

def create_main_window_thread(exit_flag):
    """Create the main window in a thread instead of a process on Windows"""
    try:
        interface = OverlayWindow('http://127.0.0.1:8085/', width=1000, height=700, frameless=False)
        
        def on_window_closed():
            exit_flag.value = 1
            
        interface.set_on_closed(on_window_closed)
        interface.create_overlay_window()
    except Exception as e:
        print(f"Error in main window thread: {e}")
        exit_flag.value = 1

def create_main_window(exit_flag):
    """
    Create the main window in a separate process
    """
    try:
        interface = OverlayWindow('http://127.0.0.1:8085/', width=1000, height=700, frameless=False)
        
        def on_window_closed():
            exit_flag.value = 1
            
        interface.set_on_closed(on_window_closed)
        interface.create_overlay_window()
    except Exception as e:
        print(f"Error in main window process: {e}")
        exit_flag.value = 1

def run_web_interface(selected_overlays):
    """
    Run the web interface in a separate process
    """
    try:
        web_interface = WebInterface(selected_overlays)
        web_interface.run()
    except Exception as e:
        print(f"Error in web interface: {e}")

def run_unified_app(selected_overlays):
    """
    Run both web interface and create window in the main thread
    This is used when we're in fallback mode to ensure pywebview runs in the main thread
    """
    try:
        web_interface = WebInterface(selected_overlays)
        
        web_thread = threading.Thread(target=lambda: web_interface.run())
        web_thread.daemon = True
        web_thread.start()
        
        time.sleep(1)
        
        print("Creating main window in main thread...")
        interface = OverlayWindow('http://127.0.0.1:8085/', width=1000, height=700, frameless=False)
        
        interface.create_overlay_window()
        print("Main window closed, shutting down...")
        
    except Exception as e:
        print(f"Error in unified app: {e}")

def main():
    """
    Main entry point for the iRacing Telemetry Overlay application.
    Initializes and runs the web interface with detected overlays.
    """
    global overlay_processes, web_interface_process

    logging.info("Entering main() function")
    atexit.register(cleanup)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logging.info("Signal handlers registered")

    try:
        selected_overlays = detect_overlays()
        frozen_on_windows = platform.system() == 'Windows' and getattr(sys, 'frozen', False)

        logging.info(f"Frozen on Windows: {frozen_on_windows}")
        logging.info(f"Using fallback mode: {using_fallback_mode}")

        if using_fallback_mode or frozen_on_windows:
            logging.info("Running in unified mode - web interface and window in same process")
            print("Running in unified mode - web interface and window in same process")
            run_unified_app(selected_overlays)
            cleanup()
            return
            
        web_interface_process = multiprocessing.Process(
            target=run_web_interface,
            args=(selected_overlays,)
        )
        web_interface_process.start()
        
        time.sleep(0.5)
        
        if frozen_on_windows:
            import threading
            main_window_thread = threading.Thread(
                target=create_main_window_thread,
                args=(exit_flag,)
            )
            main_window_thread.daemon = True
            main_window_thread.start()
            
            while True:
                if exit_flag.value == 1:
                    print("Main window closed, initiating shutdown...")
                    cleanup()
                    break
                time.sleep(0.1)
        else:
            overlay_process = multiprocessing.Process(
                target=create_main_window,
                args=(exit_flag,)
            )
            overlay_process.start()
            overlay_processes.append(overlay_process)
            
            while True:
                if exit_flag.value == 1:
                    print("Main window closed, initiating shutdown...")
                    cleanup()
                    break
                time.sleep(0.1)
            
        sys.exit(0)

    except KeyboardInterrupt:
        print("Shutting down gracefully...")
        cleanup()
        sys.exit(0)

if __name__ == '__main__':
    try:
        multiprocessing.freeze_support()
        logging.info("Starting main application...")
        main()
        logging.info("Application exited normally")
    except Exception as e:
        logging.error("="*60)
        logging.error("FATAL ERROR - Application crashed!")
        logging.error(f"Error: {e}")
        logging.error("="*60)
        logging.error("Full traceback:")
        logging.error(traceback.format_exc())
        logging.error("="*60)
        logging.error(f"Log file saved to: {log_file}")

        print("\n" + "="*60)
        print("APPLICATION ERROR!")
        print(f"Error: {e}")
        print("="*60)
        print(f"\nFull error log saved to:\n{log_file}")
        print("\nPress Enter to close this window...")
        print("="*60)

        try:
            input()
        except:
            time.sleep(30)  # Keep window open for 30 seconds if input() fails

        sys.exit(1)