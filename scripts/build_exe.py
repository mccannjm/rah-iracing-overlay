import os
import subprocess
import sys
import shutil
import platform
import time

def check_requirements():
    """Check if required packages are installed with specific versions"""
    try:
        import PyInstaller
        print("PyInstaller found!")
    except ImportError:
        print("Installing PyInstaller...")
        try:
            # Try pip3 first (common on macOS/Linux)
            subprocess.check_call(["pip3", "install", "pyinstaller"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fall back to pip
            try:
                subprocess.check_call(["pip", "install", "pyinstaller"])
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Final fallback to python -m pip
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Dictionary of required packages with their specific versions
    required_packages = {
        "pyirsdk": "1.3.5",
        "flask": "3.1.2",
        "flask_socketio": "5.4.1",
        "eventlet": "0.40.3",
        "pywebview": "4.4.1",
        "dnspython": "2.4.2",
        "marshmallow": "3.22.0"
    }
    
    for package, version in required_packages.items():
        try:
            module = __import__(package)
            print(f"{package} found!")
        except ImportError:
            print(f"Installing {package} version {version}...")
            try:
                # Try pip3 first (common on macOS/Linux)
                subprocess.check_call(["pip3", "install", f"{package}=={version}"])
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fall back to pip
                try:
                    subprocess.check_call(["pip", "install", f"{package}=={version}"])
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # Final fallback to python -m pip
                    subprocess.check_call([sys.executable, "-m", "pip", "install", f"{package}=={version}"])

def build_exe():
    """Build the executable using PyInstaller"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(script_dir, "src")
    
    for dir_name in ["build", "dist"]:
        path = os.path.join(script_dir, dir_name)
        if os.path.exists(path):
            print(f"Removing old {dir_name} directory...")
            try:
                shutil.rmtree(path)
            except PermissionError as e:
                print(f"\nERROR: Cannot remove {dir_name} directory. Files may be in use by another process.")
                print("Please close any applications that might be using files in this directory.")
                print("Specifically, make sure you've closed any instances of RAH_Telemetry_Overlay.")
                print(f"Error details: {e}")
                print("\nTry one of the following solutions:")
                print("1. Close any running instances of the application")
                print("2. Restart your computer")
                print("3. Manually delete the directory before running this script again")
                sys.exit(1)
    
    spec_file = os.path.join(src_dir, "RAH_Telemetry_Overlay.spec")
    print("Building executable...")
    os.chdir(script_dir)
    
    dist_path = os.path.join(script_dir, "dist")
    work_path = os.path.join(script_dir, "build")
    
    subprocess.check_call([
        sys.executable, 
        "-m", 
        "PyInstaller", 
        spec_file,
        "--distpath", 
        dist_path,
        "--workpath", 
        work_path
    ])
    
    print("\n============ BUILD COMPLETED ============")

if __name__ == "__main__":
    print("========== Building RAH Telemetry Overlay ==========")
    print(f"Python version: {platform.python_version()}")
    print(f"Operating system: {platform.system()} {platform.release()}")
    
    check_requirements()
    build_exe() 