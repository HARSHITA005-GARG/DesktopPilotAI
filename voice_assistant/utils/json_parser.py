import json
from utils.logger import get_logger

logger = get_logger(__name__)


def parse_json_response(json_string):
    """
    Parse and validate JSON response from AI model.
    Returns: dict with 'action' and 'parameters' keys
    """
    try:
        data = json.loads(json_string)
        
        if "action" not in data:
            raise ValueError("Missing 'action' key in JSON response")
        
        if not isinstance(data.get("parameters"), dict):
            data["parameters"] = {}
        
        logger.debug(f"Parsed JSON: {data}")
        return data
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format: {e}")
        raise ValueError(f"Invalid JSON: {e}")
    except Exception as e:
        logger.error(f"Error parsing JSON: {e}")
        raise


def validate_action(action, supported_actions):
    """Validate if action is supported."""
    if action not in supported_actions:
        logger.error(f"Unsupported action: {action}")
        raise ValueError(f"Action '{action}' is not supported")
    return True
