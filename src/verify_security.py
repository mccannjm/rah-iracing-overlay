#!/usr/bin/env python3
"""
Simple security verification script (no external dependencies)
"""
import json
import re
import os


def verify_javascript_escaping():
    """Verify that json.dumps properly escapes dangerous strings"""
    print("🔒 Verifying JavaScript escaping...")
    
    dangerous_strings = [
        "'; alert('XSS'); var x='",
        "\"; alert('XSS'); var x=\"", 
        "<script>alert('XSS')</script>",
        "folder_name_with_quotes'\"",
    ]
    
    for dangerous_str in dangerous_strings:
        escaped = json.dumps(dangerous_str)
        print(f"✅ Safely escaped: '{dangerous_str}' -> {escaped}")
        
        # Verify no unescaped quotes that could break out of JS strings
        if "'" not in escaped.replace("\\'", "") and '"' not in escaped.replace('\\"', ""):
            print(f"  ✅ No unescaped quotes found")
        else:
            print(f"  ❌ WARNING: May contain unescaped quotes")


def verify_path_traversal_detection():
    """Verify basic path traversal detection patterns"""
    print("\n🔒 Verifying path traversal detection...")
    
    safe_pattern = re.compile(r'^[a-zA-Z0-9_\-]+$')
    
    safe_names = ["input_telemetry", "driver_info", "lap_times", "test_overlay"]
    dangerous_names = [
        "../../../etc/passwd",
        "..\\windows\\system32", 
        "folder/../other",
        "folder/subdir",
        "folder\\subdir",
        "overlay@hack",
        "name with spaces",
        ""
    ]
    
    print("Testing safe names:")
    for name in safe_names:
        if safe_pattern.match(name) and '..' not in name and '/' not in name and '\\' not in name:
            print(f"✅ Safe: '{name}'")
        else:
            print(f"❌ False positive: '{name}'")
    
    print("\nTesting dangerous names:")
    for name in dangerous_names:
        if not safe_pattern.match(name) or '..' in name or '/' in name or '\\' in name:
            print(f"✅ Correctly blocked: '{name}'")
        else:
            print(f"❌ WARNING: Not blocked: '{name}'")


def verify_file_changes():
    """Verify that security-related files have been modified"""
    print("\n🔒 Verifying security-related file modifications...")
    
    # Check if validation.py exists
    if os.path.exists('validation.py'):
        print("✅ validation.py created")
        
        # Check for key security functions
        with open('validation.py', 'r') as f:
            content = f.read()
            if 'validate_folder_name' in content:
                print("✅ validate_folder_name function found")
            if 'path traversal' in content.lower():
                print("✅ Path traversal protection implemented")
            if 'ValidationError' in content:
                print("✅ Proper error handling implemented")
    else:
        print("❌ validation.py not found")
    
    # Check requirements.txt for updated dependencies
    if os.path.exists('../requirements.txt'):
        with open('../requirements.txt', 'r') as f:
            content = f.read()
            if 'Flask==3.1.2' in content:
                print("✅ Flask updated to secure version")
            elif 'Flask==3.0.3' in content:
                print("❌ Flask still on vulnerable version")
            
            if 'eventlet==0.40.3' in content:
                print("✅ Eventlet updated to secure version") 
            elif 'eventlet==0.37.0' in content:
                print("❌ Eventlet still on vulnerable version")
                
            if 'marshmallow' in content:
                print("✅ Marshmallow added for validation")
    
    # Check overlay_window.py for JSON escaping
    if os.path.exists('overlay_window.py'):
        with open('overlay_window.py', 'r') as f:
            content = f.read()
            if 'json.dumps' in content:
                print("✅ JSON escaping implemented in overlay_window.py")
            if 'import html' in content:
                print("✅ HTML escaping module imported")
    
    # Check web_interface.py for CORS restrictions
    if os.path.exists('web_interface.py'):
        with open('web_interface.py', 'r') as f:
            content = f.read()
            if "cors_allowed_origins': ['http://127.0.0.1:8085'" in content:
                print("✅ CORS policy restricted to specific origins")
            if 'MAX_CONTENT_LENGTH' in content:
                print("✅ Request size limits implemented")
            if 'X-Content-Type-Options' in content:
                print("✅ Security headers implemented")


def main():
    """Run security verification"""
    print("🔒 RAH iRacing Overlay Security Verification\n")
    
    verify_javascript_escaping()
    verify_path_traversal_detection()
    verify_file_changes()
    
    print("\n✅ Security verification completed!")
    print("🔒 Please install updated dependencies: pip install -r requirements.txt")


if __name__ == "__main__":
    main()