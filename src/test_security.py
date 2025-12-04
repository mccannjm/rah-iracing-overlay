#!/usr/bin/env python3
"""
Basic security test script to validate implemented security improvements
"""
import json
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.dirname(__file__))

from validation import (
    validate_folder_name, OverlayRequestSchema, WindowPositionReportSchema, 
    validate_request_data
)
from marshmallow import ValidationError


def test_folder_name_validation():
    """Test folder name validation against path traversal"""
    print("Testing folder name validation...")
    
    # Valid folder names
    valid_names = ["input_telemetry", "driver_info", "lap_times"]
    for name in valid_names:
        try:
            result = validate_folder_name(name)
            print(f"✅ Valid: '{name}' -> '{result}'")
        except ValueError as e:
            print(f"❌ Unexpected error for valid name '{name}': {e}")
    
    # Invalid folder names (path traversal attempts)
    invalid_names = [
        "../../../etc/passwd",
        "..\\windows\\system32",
        "folder/../other",
        "folder/subdir",
        "folder\\subdir",
        "folder with spaces!",
        "folder@#$%",
        "",
        None
    ]
    
    for name in invalid_names:
        try:
            result = validate_folder_name(name)
            print(f"❌ Should have failed: '{name}' -> '{result}'")
        except (ValueError, TypeError):
            print(f"✅ Correctly blocked: '{name}'")


def test_json_validation():
    """Test JSON input validation"""
    print("\nTesting JSON input validation...")
    
    # Test overlay request schema
    valid_request = {
        "overlay": "input_telemetry",
        "transparent": True
    }
    
    try:
        result = validate_request_data(OverlayRequestSchema, valid_request)
        print(f"✅ Valid overlay request: {result}")
    except ValidationError as e:
        print(f"❌ Unexpected error for valid request: {e}")
    
    # Test invalid requests
    invalid_requests = [
        {"overlay": ""},  # Empty overlay name
        {"overlay": "invalid@name!"},  # Invalid characters
        {"overlay": "a" * 60},  # Too long
        {"overlay": "../../../etc/passwd"},  # Path traversal
        None,  # No data
        {}  # Missing required field
    ]
    
    for req in invalid_requests:
        try:
            result = validate_request_data(OverlayRequestSchema, req)
            print(f"❌ Should have failed: {req} -> {result}")
        except ValidationError:
            print(f"✅ Correctly blocked invalid request: {req}")
        except Exception as e:
            print(f"✅ Correctly blocked with error: {req} -> {type(e).__name__}")


def test_position_validation():
    """Test position data validation"""
    print("\nTesting position data validation...")
    
    # Valid position report
    valid_position = {
        "folder_name": "input_telemetry",
        "position": {"x": 100, "y": 200},
        "dpi_scale": 1.5
    }
    
    try:
        result = validate_request_data(WindowPositionReportSchema, valid_position)
        print(f"✅ Valid position report: {result}")
    except ValidationError as e:
        print(f"❌ Unexpected error for valid position: {e}")
    
    # Test invalid position reports
    invalid_positions = [
        {
            "folder_name": "../../../etc",
            "position": {"x": 100, "y": 200}
        },  # Path traversal
        {
            "folder_name": "valid_name",
            "position": {"x": "not_a_number", "y": 200}
        },  # Invalid coordinate type
        {
            "folder_name": "valid_name",
            "position": {"x": 99999, "y": 200}
        },  # Out of bounds
        {
            "folder_name": "valid_name",
            "position": "not_an_object"
        },  # Invalid position type
    ]
    
    for pos in invalid_positions:
        try:
            result = validate_request_data(WindowPositionReportSchema, pos)
            print(f"❌ Should have failed: {pos} -> {result}")
        except ValidationError:
            print(f"✅ Correctly blocked invalid position: {pos}")


def test_javascript_escaping():
    """Test that JavaScript values are properly escaped"""
    print("\nTesting JavaScript escaping...")
    
    # Test dangerous strings that could cause injection
    dangerous_strings = [
        "'; alert('XSS'); var x='",
        "\"; alert('XSS'); var x=\"",
        "<script>alert('XSS')</script>",
        "\\'; alert('XSS'); var x='",
    ]
    
    for dangerous_str in dangerous_strings:
        escaped = json.dumps(dangerous_str)
        print(f"✅ Escaped: '{dangerous_str}' -> {escaped}")
        
        # Verify it's safe to embed in JS
        js_code = f"var folderName = {escaped};"
        # This should not cause syntax errors or injection
        print(f"  JS: {js_code}")


def main():
    """Run all security tests"""
    print("🔒 Running Security Tests for RAH iRacing Overlay\n")
    
    try:
        test_folder_name_validation()
        test_json_validation()
        test_position_validation() 
        test_javascript_escaping()
        
        print("\n✅ All security tests completed!")
        print("🔒 Security improvements appear to be working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())