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

def remove_readonly(func, path, excinfo):
    """Error handler for Windows readonly files"""
    os.chmod(path, 0o777)
    func(path)

def remove_directory_safely(path, dir_name):
    """Safely remove a directory with retries and proper error handling"""
    max_retries = 3
    retry_delay = 1  # seconds

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"Retry attempt {attempt + 1}/{max_retries}...")
                time.sleep(retry_delay)

            shutil.rmtree(path, onerror=remove_readonly)
            print(f"Successfully removed old {dir_name} directory")
            return True

        except (PermissionError, OSError) as e:
            if attempt == max_retries - 1:
                print(f"\nERROR: Cannot remove {dir_name} directory after {max_retries} attempts.")
                print("Files may be in use by another process or marked as read-only.")
                print("Please close any applications that might be using files in this directory.")
                print("Specifically, make sure you've closed any instances of RAH_Telemetry_Overlay.")
                print(f"Error details: {e}")
                print(f"\nProblematic path: {path}")
                print("\nTry one of the following solutions:")
                print("1. Close any running instances of the application")
                print("2. Close any file explorer windows showing these directories")
                print("3. Restart your computer")
                print("4. Manually delete the directory before running this script again")
                return False

    return True

def build_exe():
    """Build the executable using PyInstaller"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Get the repository root (parent of scripts/ directory)
    repo_root = os.path.dirname(script_dir)
    src_dir = os.path.join(repo_root, "src")

    # Validate paths exist
    print(f"Repository root: {repo_root}")
    print(f"Source directory: {src_dir}")

    if not os.path.exists(src_dir):
        print(f"\nERROR: Source directory not found at {src_dir}")
        print("Make sure you're running this script from the correct location.")
        sys.exit(1)

    # Spec file is now in src/config/
    spec_file = os.path.join(src_dir, "config", "RAH_Telemetry_Overlay.spec")

    if not os.path.exists(spec_file):
        print(f"\nERROR: Spec file not found at {spec_file}")
        print("Expected location: src/config/RAH_Telemetry_Overlay.spec")
        sys.exit(1)

    print(f"Using spec file: {spec_file}")

    # Remove old build artifacts
    for dir_name in ["build", "dist"]:
        path = os.path.join(repo_root, dir_name)
        if os.path.exists(path):
            print(f"Removing old {dir_name} directory...")
            if not remove_directory_safely(path, dir_name):
                sys.exit(1)

    print("\nBuilding executable with PyInstaller...")
    os.chdir(repo_root)

    dist_path = os.path.join(repo_root, "dist")
    work_path = os.path.join(repo_root, "build")

    try:
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
    except subprocess.CalledProcessError as e:
        print(f"\n\nERROR: PyInstaller build failed with exit code {e.returncode}")
        print("Check the output above for specific error messages.")
        print("\nCommon issues:")
        print("- Missing dependencies (run: pip install -r requirements.txt)")
        print("- Syntax errors in the source code")
        print("- Issues with the spec file configuration")
        sys.exit(1)
    except FileNotFoundError:
        print("\nERROR: PyInstaller not found. This should not happen after check_requirements().")
        print("Try manually installing: pip install pyinstaller")
        sys.exit(1)

    # Verify the build output exists
    expected_exe_dir = os.path.join(dist_path, "RAH_Telemetry_Overlay")
    if os.path.exists(expected_exe_dir):
        print("\n============ BUILD COMPLETED SUCCESSFULLY ============")
        print(f"Output location: {expected_exe_dir}")
    else:
        print("\n============ BUILD COMPLETED ============")
        print("Warning: Expected output directory not found. Check dist/ for build results.")
        print(f"Expected: {expected_exe_dir}")

if __name__ == "__main__":
    print("========== Building RAH Telemetry Overlay ==========")
    print(f"Python version: {platform.python_version()}")
    print(f"Operating system: {platform.system()} {platform.release()}")
    
    check_requirements()
    build_exe() 