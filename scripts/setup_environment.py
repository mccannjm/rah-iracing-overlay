#!/usr/bin/env python3
"""
Environment setup script that handles virtual environments and pip3/pip issues
"""
import subprocess
import sys
import os
import platform
import venv
import shutil


def detect_pip_command():
    """
    Detect which pip command is available on the system
    
    Returns:
        list: The pip command to use (['pip3'] or ['pip'] or [sys.executable, '-m', 'pip'])
    """
    pip_commands = ['pip3', 'pip', [sys.executable, '-m', 'pip']]
    
    for cmd in pip_commands:
        try:
            if isinstance(cmd, list):
                result = subprocess.run(cmd + ['--version'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return cmd
            else:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return [cmd]
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    raise RuntimeError("No pip command found. Please install pip or pip3.")


def check_virtual_environment():
    """Check if we're in a virtual environment or need to create one"""
    # Check if already in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ Already in virtual environment")
        return True, None
    
    # Check if venv directory exists
    venv_path = os.path.join(os.getcwd(), 'venv')
    if os.path.exists(venv_path):
        print("✅ Virtual environment found at: venv/")
        return False, venv_path
    
    return False, None


def create_virtual_environment():
    """Create a virtual environment"""
    venv_path = os.path.join(os.getcwd(), 'venv')
    
    print(f"🔧 Creating virtual environment at: {venv_path}")
    try:
        venv.create(venv_path, with_pip=True)
        print("✅ Virtual environment created successfully")
        return venv_path
    except Exception as e:
        print(f"❌ Failed to create virtual environment: {e}")
        return None


def get_venv_python_and_pip(venv_path):
    """Get the python and pip commands for the virtual environment"""
    if platform.system() == "Windows":
        python_cmd = os.path.join(venv_path, 'Scripts', 'python.exe')
        pip_cmd = os.path.join(venv_path, 'Scripts', 'pip.exe')
    else:
        python_cmd = os.path.join(venv_path, 'bin', 'python')
        pip_cmd = os.path.join(venv_path, 'bin', 'pip')
    
    return python_cmd, [pip_cmd]


def install_requirements_in_venv(venv_path):
    """Install requirements in virtual environment"""
    python_cmd, pip_cmd = get_venv_python_and_pip(venv_path)
    
    if not os.path.exists('requirements.txt'):
        print("❌ requirements.txt not found")
        return False
    
    print("📦 Installing requirements in virtual environment...")
    try:
        install_cmd = pip_cmd + ['install', '-r', 'requirements.txt']
        result = subprocess.run(install_cmd, check=True)
        
        if result.returncode == 0:
            print("✅ Requirements installed successfully in virtual environment!")
            return True
        else:
            print("❌ Failed to install requirements")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation failed: {e}")
        return False


def install_requirements_global():
    """Install requirements globally (if no externally-managed-environment)"""
    try:
        pip_cmd = detect_pip_command()
        
        if not os.path.exists('requirements.txt'):
            print("❌ requirements.txt not found")
            return False
        
        print("📦 Installing requirements globally...")
        
        install_cmd = pip_cmd + ['install', '-r', 'requirements.txt']
        result = subprocess.run(install_cmd, check=True)
        
        if result.returncode == 0:
            print("✅ Requirements installed successfully!")
            return True
        else:
            print("❌ Failed to install requirements")
            return False
            
    except subprocess.CalledProcessError as e:
        error_output = str(e)
        if 'externally-managed-environment' in error_output:
            print("⚠️  System requires virtual environment due to externally-managed-environment")
            return False
        else:
            print(f"❌ Installation failed: {e}")
            return False


def show_activation_instructions(venv_path):
    """Show instructions for activating the virtual environment"""
    print(f"\n🚀 Virtual environment setup complete!")
    print(f"📁 Location: {venv_path}")
    
    print(f"\n📋 To use the environment:")
    if platform.system() == "Windows":
        print(f"   {venv_path}\\Scripts\\activate")
        print(f"   python src\\main.py")
    else:
        print(f"   source {venv_path}/bin/activate")
        print(f"   python3 src/main.py")
    
    print(f"\n📋 Or run directly without activation:")
    if platform.system() == "Windows":
        print(f"   {venv_path}\\Scripts\\python.exe src\\main.py")
    else:
        print(f"   {venv_path}/bin/python src/main.py")


def create_run_script(venv_path):
    """Create a convenience script to run the application"""
    if platform.system() == "Windows":
        script_name = "run_overlay.bat"
        python_path = os.path.join(venv_path, 'Scripts', 'python.exe')
        content = f"""@echo off
echo Starting RAH iRacing Overlay...
"{python_path}" src\\main.py
pause
"""
    else:
        script_name = "run_overlay.sh"
        python_path = os.path.join(venv_path, 'bin', 'python')
        content = f"""#!/bin/bash
echo "Starting RAH iRacing Overlay..."
"{python_path}" src/main.py
"""
    
    try:
        with open(script_name, 'w') as f:
            f.write(content)
        
        if platform.system() != "Windows":
            os.chmod(script_name, 0o755)
        
        print(f"✅ Created convenience script: {script_name}")
        return script_name
    except Exception as e:
        print(f"⚠️  Failed to create run script: {e}")
        return None


def main():
    """Main setup process"""
    print("🔧 RAH iRacing Overlay - Environment Setup\n")
    
    # Show system info
    print(f"🐍 Python version: {sys.version}")
    print(f"💻 Platform: {platform.system()} {platform.release()}")
    print(f"📁 Working directory: {os.getcwd()}\n")
    
    # Check current environment
    in_venv, venv_path = check_virtual_environment()
    
    if in_venv:
        # Already in virtual environment, install directly
        success = install_requirements_global()
    else:
        # Try global installation first
        print("🔄 Attempting global installation...")
        success = install_requirements_global()
        
        if not success:
            print("\n🔄 Global installation failed, setting up virtual environment...")
            
            if venv_path is None:
                venv_path = create_virtual_environment()
                if venv_path is None:
                    print("❌ Cannot proceed without virtual environment")
                    sys.exit(1)
            
            success = install_requirements_in_venv(venv_path)
            
            if success:
                show_activation_instructions(venv_path)
                run_script = create_run_script(venv_path)
    
    if success:
        print("\n🔒 Security improvements included:")
        print("- Flask updated to 3.1.2 (patches CVE-2024-34069, CVE-2024-56326)")
        print("- Eventlet updated to 0.40.3 (patches CVE-2025-58068)")
        print("- Marshmallow added for input validation")
        print("- CORS restrictions implemented")
        print("- Path traversal protection added")
        print("- Security headers configured")
        
        if not in_venv and venv_path:
            print(f"\n⚠️  Remember to activate the virtual environment before running:")
            if platform.system() == "Windows":
                print(f"   {venv_path}\\Scripts\\activate")
            else:
                print(f"   source {venv_path}/bin/activate")
        
        print("\n✅ Setup complete! You can now run the application.")
        
    else:
        print("\n❌ Setup failed. Please check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    main()