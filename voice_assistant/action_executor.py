from utils.logger import get_logger
from utils.json_parser import parse_json_response, validate_action
from config import SUPPORTED_ACTIONS
import actions

logger = get_logger(__name__)


class ActionExecutor:
    """Execute actions based on parsed JSON response."""
    
    def __init__(self):
        self.actions_map = {
            "open_app": actions.open_app,
            "create_file": actions.create_file,
            "read_file": actions.read_file,
            "search_web": actions.search_web,
            "write_code": actions.write_code,
            "send_email": actions.send_email,
        }
    
    def execute(self, json_response):
        """
        Parse JSON and execute the corresponding action.
        
        Args:
            json_response (str): JSON string with 'action' and 'parameters'
        
        Returns:
            dict: Result of action execution
        """
        try:
            # Parse JSON
            data = parse_json_response(json_response)
            action = data["action"]
            parameters = data.get("parameters", {})
            
            # Validate action
            validate_action(action, SUPPORTED_ACTIONS)
            
            # Execute action
            logger.info(f"Executing action: {action} with parameters: {parameters}")
            action_func = self.actions_map[action]
            result = action_func(**parameters)
            
            logger.info(f"Action completed: {action}")
            return result
        
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return {"status": "error", "message": str(e)}
        except TypeError as e:
            logger.error(f"Parameter error: {e}")
            return {"status": "error", "message": f"Invalid parameters for action"}
        except Exception as e:
            logger.error(f"Execution error: {e}")
            return {"status": "error", "message": str(e)}
