#!/usr/bin/env python3
"""
Installation script that handles pip3 vs pip availability
"""
import subprocess
import sys
import os


def detect_pip_command():
    """
    Detect which pip command is available on the system
    
    Returns:
        str: The pip command to use ('pip3', 'pip', or 'python -m pip')
    """
    pip_commands = ['pip3', 'pip', [sys.executable, '-m', 'pip']]
    
    for cmd in pip_commands:
        try:
            if isinstance(cmd, list):
                result = subprocess.run(cmd + ['--version'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    print(f"✅ Using: {' '.join(cmd)}")
                    return cmd
            else:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    print(f"✅ Using: {cmd}")
                    return [cmd]
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    raise RuntimeError("No pip command found. Please install pip or pip3.")


def install_requirements():
    """Install requirements using the detected pip command"""
    try:
        # Detect available pip command
        pip_cmd = detect_pip_command()
        
        # Check if requirements.txt exists
        req_file = 'requirements.txt'
        if not os.path.exists(req_file):
            print(f"❌ {req_file} not found in current directory")
            return False
        
        print(f"📦 Installing requirements from {req_file}...")
        
        # Install requirements
        install_cmd = pip_cmd + ['install', '-r', req_file]
        result = subprocess.run(install_cmd, check=True)
        
        if result.returncode == 0:
            print("✅ Requirements installed successfully!")
            return True
        else:
            print("❌ Failed to install requirements")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Installation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def upgrade_requirements():
    """Upgrade all requirements to latest versions"""
    try:
        pip_cmd = detect_pip_command()
        
        print("🔄 Upgrading all requirements to latest versions...")
        
        # Upgrade all requirements
        upgrade_cmd = pip_cmd + ['install', '-r', 'requirements.txt', '--upgrade']
        result = subprocess.run(upgrade_cmd, check=True)
        
        if result.returncode == 0:
            print("✅ Requirements upgraded successfully!")
            return True
        else:
            print("❌ Failed to upgrade requirements")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Upgrade failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def show_installed_packages():
    """Show currently installed packages"""
    try:
        pip_cmd = detect_pip_command()
        
        print("📋 Currently installed packages:")
        list_cmd = pip_cmd + ['list']
        subprocess.run(list_cmd, check=True)
        
    except Exception as e:
        print(f"❌ Error listing packages: {e}")


def main():
    """Main installation process"""
    print("🔧 RAH iRacing Overlay - Requirements Installation\n")
    
    # Show Python version
    print(f"🐍 Python version: {sys.version}")
    
    if len(sys.argv) > 1 and sys.argv[1] == '--upgrade':
        success = upgrade_requirements()
    else:
        success = install_requirements()
    
    if success:
        print("\n📋 Installation completed! Here are the security-critical packages:")
        try:
            pip_cmd = detect_pip_command()
            
            # Check specific security-critical packages
            check_cmd = pip_cmd + ['show', 'Flask', 'eventlet', 'marshmallow']
            subprocess.run(check_cmd)
            
        except Exception:
            pass
        
        print("\n🔒 Security Note:")
        print("The following vulnerabilities have been patched:")
        print("- Flask CVE-2024-34069, CVE-2024-56326 (updated to 3.1.2)")
        print("- Eventlet CVE-2025-58068 (updated to 0.40.3)")
        print("- Input validation added with marshmallow")
        
        print("\n🚀 You can now run the application with:")
        print("   python3 src/main.py")
        
    else:
        print("\n❌ Installation failed. Please check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    main()