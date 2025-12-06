"""
Input validation schemas for security
"""
from marshmallow import Schema, fields, ValidationError, validates_schema
from marshmallow.validate import Length, Range
import re


class OverlayRequestSchema(Schema):
    """Schema for overlay launch requests"""
    overlay = fields.Str(required=True, validate=Length(min=1, max=50))
    transparent = fields.Bool(missing=True)
    folder_name = fields.Str(validate=Length(min=1, max=50))

    @validates_schema
    def validate_overlay_name(self, data, **kwargs):
        """Validate overlay name contains only safe characters"""
        overlay = data.get('overlay', '')
        folder_name = data.get('folder_name', '')
        
        # Allow only alphanumeric, underscore, hyphen, and space
        safe_pattern = re.compile(r'^[a-zA-Z0-9_\- ]+$')
        
        if overlay and not safe_pattern.match(overlay):
            raise ValidationError('Overlay name contains invalid characters')
        
        if folder_name and not safe_pattern.match(folder_name):
            raise ValidationError('Folder name contains invalid characters')


class PositionRequestSchema(Schema):
    """Schema for position update requests"""
    overlay = fields.Str(required=True, validate=Length(min=1, max=50))
    position = fields.Dict(required=True)
    folder_name = fields.Str(validate=Length(min=1, max=50))

    @validates_schema
    def validate_position(self, data, **kwargs):
        """Validate position data"""
        position = data.get('position', {})
        
        if not isinstance(position, dict):
            raise ValidationError('Position must be an object')
        
        # Validate x and y coordinates
        x = position.get('x')
        y = position.get('y')
        
        if x is not None and (not isinstance(x, (int, float)) or x < -5000 or x > 10000):
            raise ValidationError('Invalid x coordinate')
        
        if y is not None and (not isinstance(y, (int, float)) or y < -5000 or y > 10000):
            raise ValidationError('Invalid y coordinate')


class WindowPositionReportSchema(Schema):
    """Schema for window position reports"""
    folder_name = fields.Str(required=True, validate=Length(min=1, max=50))
    position = fields.Dict(required=True)
    dpi_scale = fields.Float(validate=Range(min=0.1, max=5.0), missing=1.0)

    @validates_schema
    def validate_data(self, data, **kwargs):
        """Validate folder name and position data"""
        folder_name = data.get('folder_name', '')
        position = data.get('position', {})
        
        # Validate folder name - no path traversal
        if '..' in folder_name or '/' in folder_name or '\\' in folder_name:
            raise ValidationError('Invalid folder name - path traversal detected')
        
        # Allow only safe characters in folder name
        safe_pattern = re.compile(r'^[a-zA-Z0-9_\-]+$')
        if not safe_pattern.match(folder_name):
            raise ValidationError('Folder name contains invalid characters')
        
        # Validate position
        if not isinstance(position, dict):
            raise ValidationError('Position must be an object')
        
        x = position.get('x')
        y = position.get('y')
        
        if not isinstance(x, (int, float)) or x < -5000 or x > 10000:
            raise ValidationError('Invalid x coordinate')
        
        if not isinstance(y, (int, float)) or y < -5000 or y > 10000:
            raise ValidationError('Invalid y coordinate')


class CloseOverlaySchema(Schema):
    """Schema for close overlay requests"""
    overlay = fields.Str(validate=Length(min=1, max=50))
    folder_name = fields.Str(validate=Length(min=1, max=50))

    @validates_schema
    def validate_identifiers(self, data, **kwargs):
        """Ensure at least one identifier is provided"""
        if not data.get('overlay') and not data.get('folder_name'):
            raise ValidationError('Either overlay or folder_name must be provided')


def validate_folder_name(folder_name):
    """
    Validate folder name for path traversal and malicious content
    
    Args:
        folder_name (str): The folder name to validate
        
    Returns:
        str: The validated folder name
        
    Raises:
        ValueError: If folder name is invalid
    """
    if not folder_name or not isinstance(folder_name, str):
        raise ValueError("Folder name must be a non-empty string")
    
    # Check for path traversal attempts
    if '..' in folder_name or '/' in folder_name or '\\' in folder_name:
        raise ValueError("Invalid folder name - path traversal detected")
    
    # Allow only alphanumeric, underscore, and hyphen
    safe_pattern = re.compile(r'^[a-zA-Z0-9_\-]+$')
    if not safe_pattern.match(folder_name):
        raise ValueError("Folder name contains invalid characters")
    
    # Length check
    if len(folder_name) > 50:
        raise ValueError("Folder name too long")
    
    return folder_name


def validate_request_data(schema_class, data):
    """
    Helper function to validate request data against a schema
    
    Args:
        schema_class: Marshmallow schema class
        data: Data to validate
        
    Returns:
        dict: Validated data
        
    Raises:
        ValidationError: If validation fails
    """
    if data is None:
        raise ValidationError("No data provided")
    
    schema = schema_class()
    try:
        return schema.load(data)
    except ValidationError as e:
        # Log validation errors for security monitoring
        import logging
        logging.warning(f"Input validation failed: {e.messages}")
        raise e