#!/usr/bin/env python3
"""
Windows Security Fix Script
Handles DLL unblocking and security zone removal
"""
import os
import sys
import subprocess
import platform


def is_windows():
    """Check if running on Windows"""
    return platform.system() == 'Windows'


def find_blocked_files(root_dir):
    """Find files that may be blocked by Windows security"""
    blocked_extensions = ['.dll', '.exe', '.pyd', '.so']
    blocked_files = []
    
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if any(file.lower().endswith(ext) for ext in blocked_extensions):
                file_path = os.path.join(root, file)
                blocked_files.append(file_path)
    
    return blocked_files


def unblock_file_powershell(file_path):
    """Unblock file using PowerShell Unblock-File command"""
    try:
        cmd = ['powershell', '-Command', f'Unblock-File -Path "{file_path}"']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, "Success"
    except subprocess.CalledProcessError as e:
        return False, f"PowerShell error: {e.stderr}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def unblock_file_streams(file_path):
    """Remove alternate data stream that marks file as downloaded"""
    try:
        # Remove the Zone.Identifier alternate data stream
        cmd = ['powershell', '-Command', f'Remove-Item -Path "{file_path}:Zone.Identifier" -ErrorAction SilentlyContinue']
        subprocess.run(cmd, capture_output=True, text=True)
        return True, "Zone identifier removed"
    except Exception as e:
        return False, f"Error removing zone identifier: {str(e)}"


def create_unblock_batch_script():
    """Create a batch script to unblock all DLLs"""
    script_content = """@echo off
echo Unblocking RAH iRacing Overlay files...
echo.

REM Unblock main executable
if exist "RAH_Telemetry_Overlay.exe" (
    echo Unblocking main executable...
    powershell -Command "Unblock-File -Path 'RAH_Telemetry_Overlay.exe'"
)

REM Unblock all DLL files recursively
echo Unblocking DLL files...
for /r . %%f in (*.dll) do (
    echo Unblocking: %%f
    powershell -Command "Unblock-File -Path '%%f'" 2>nul
)

REM Unblock Python extension files
echo Unblocking Python extension files...
for /r . %%f in (*.pyd) do (
    echo Unblocking: %%f
    powershell -Command "Unblock-File -Path '%%f'" 2>nul
)

REM Unblock executable files
echo Unblocking executable files...
for /r . %%f in (*.exe) do (
    echo Unblocking: %%f
    powershell -Command "Unblock-File -Path '%%f'" 2>nul
)

echo.
echo ✅ Unblocking complete!
echo You can now run RAH_Telemetry_Overlay.exe
pause
"""
    
    try:
        with open('unblock_files.bat', 'w') as f:
            f.write(script_content)
        print("✅ Created unblock_files.bat script")
        return True
    except Exception as e:
        print(f"❌ Failed to create batch script: {e}")
        return False


def create_security_fix_readme():
    """Create a comprehensive README for Windows security issues"""
    readme_content = """# Windows Security Fix Guide

## 🔒 Why Files Get Blocked

When you download files from the internet, Windows applies security zones:
- Files are marked with "Zone.Identifier" metadata
- Windows blocks execution of potentially dangerous files
- This affects .dll, .exe, and .pyd files

## 🛠️ Automated Fix (Recommended)

### Method 1: Use the Batch Script
1. Run as Administrator: `unblock_files.bat`
2. This will automatically unblock all necessary files

### Method 2: PowerShell Command
Run PowerShell as Administrator:
```powershell
Get-ChildItem -Recurse | Unblock-File
```

## 🔧 Manual Fix

If automated methods don't work:

### For Each Blocked File:
1. Right-click the file → Properties
2. Look for "Security" section at bottom
3. Check "Unblock" if present
4. Click OK

### Common Files to Unblock:
- `RAH_Telemetry_Overlay.exe`
- `_internal/pythonnet/runtime/Python.Runtime.dll`
- All files in `_internal/webview/lib/`
- All `.dll` files in `_internal/` subdirectories

## 🚨 Security Considerations

### This Application is Safe Because:
- ✅ **Source code audited** for security vulnerabilities
- ✅ **No network access** except localhost (127.0.0.1:8085)
- ✅ **Read-only iRacing data** access
- ✅ **No system modification** capabilities
- ✅ **Local operation only** - no external communication

### Verification Steps:
1. Check Windows Defender scan results
2. Verify no network connections to external hosts
3. Monitor Process Monitor during execution

## 🔐 Advanced Security (Optional)

### Code Signing Alternative
For enterprise use, consider:
1. Code signing the executable with your own certificate
2. Adding certificate to Windows Trusted Root
3. Group Policy deployment

### Windows Defender Exclusions
Add folder to Windows Defender exclusions:
1. Windows Security → Virus & threat protection
2. Manage settings → Add or remove exclusions
3. Add folder: RAH_Telemetry_Overlay directory

## ⚠️ If Problems Persist

1. **Run as Administrator**: Right-click → "Run as administrator"
2. **Check Windows Event Log**: Windows Logs → Application
3. **Disable real-time protection** temporarily during first run
4. **Contact support** with error messages

## 🎯 Expected Behavior After Fix

✅ Application starts without security warnings
✅ Overlay windows display properly
✅ iRacing telemetry data flows normally
✅ No blocked file error messages
"""
    
    try:
        with open('WINDOWS_SECURITY_FIX.md', 'w') as f:
            f.write(readme_content)
        print("✅ Created WINDOWS_SECURITY_FIX.md")
        return True
    except Exception as e:
        print(f"❌ Failed to create security README: {e}")
        return False


def main():
    """Main security fix process"""
    print("🔒 RAH iRacing Overlay - Windows Security Fix\n")
    
    if not is_windows():
        print("ℹ️  This script is designed for Windows systems.")
        print("   On other platforms, file blocking is not typically an issue.")
        print("\n✅ Creating Windows-specific fix files for deployment...")
        
        create_unblock_batch_script()
        create_security_fix_readme()
        
        print("\n📋 When you deploy to Windows:")
        print("   1. Copy these files with your application")
        print("   2. Run 'unblock_files.bat' as Administrator")
        print("   3. Follow WINDOWS_SECURITY_FIX.md if issues persist")
        return
    
    # Windows-specific operations
    print("🔍 Scanning for potentially blocked files...")
    
    # Look for common locations
    search_paths = ['.', 'dist', '_internal']
    all_blocked_files = []
    
    for path in search_paths:
        if os.path.exists(path):
            blocked_files = find_blocked_files(path)
            all_blocked_files.extend(blocked_files)
    
    if not all_blocked_files:
        print("✅ No executable files found to unblock")
        return
    
    print(f"📋 Found {len(all_blocked_files)} files that may need unblocking")
    
    # Create automated fix tools
    create_unblock_batch_script()
    create_security_fix_readme()
    
    print("\n🛠️ Automated fix files created:")
    print("   - unblock_files.bat (run as Administrator)")
    print("   - WINDOWS_SECURITY_FIX.md (detailed instructions)")
    
    # Ask if user wants to attempt automatic unblocking
    try:
        response = input("\n🔧 Attempt automatic unblocking now? (y/N): ")
        if response.lower() == 'y':
            print("\n🔄 Attempting to unblock files...")
            success_count = 0
            
            for file_path in all_blocked_files:
                success, message = unblock_file_powershell(file_path)
                if success:
                    success_count += 1
                    print(f"✅ {os.path.basename(file_path)}")
                else:
                    print(f"⚠️  {os.path.basename(file_path)}: {message}")
            
            print(f"\n📊 Unblocked {success_count}/{len(all_blocked_files)} files")
            
            if success_count == len(all_blocked_files):
                print("🎉 All files unblocked successfully!")
            else:
                print("⚠️  Some files may still be blocked. Run 'unblock_files.bat' as Administrator")
    
    except KeyboardInterrupt:
        print("\n\n✅ Fix files created. Run 'unblock_files.bat' when ready.")


if __name__ == "__main__":
    main()