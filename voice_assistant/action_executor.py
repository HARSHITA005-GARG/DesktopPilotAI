from utils.logger import get_logger
from utils.json_parser import parse_json_response, validate_action
from config import SUPPORTED_ACTIONS
from actions.app_actions import calculate, open_target, write_in_app
from actions.code_actions import write_code
from actions.email_actions import send_email
from actions.file_actions import create_file
from actions.web_actions import browse

logger = get_logger(__name__)


def shutdown_assistant():
    """Request the continuous listener to stop."""
    return {
        "status": "shutdown",
        "message": "Shutting down. Call me again whenever you want.",
    }


class ActionExecutor:
    """Execute actions based on parsed JSON response."""
    
    def __init__(self):
        self.actions_map = {
            "open": open_target,
            "write_in_app": write_in_app,
            "calculate": calculate,
            "browse": browse,
            "create_file": create_file,
            "write_code": write_code,
            "send_email": send_email,
            "shutdown": shutdown_assistant,
        }
    
    def execute(self, json_response):
        """
        Parse JSON and execute the corresponding action.
        
        Args:
            json_response (str | dict): JSON string or dict with an action payload
        
        Returns:
            dict: Result of action execution
        """
        try:
            data = parse_json_response(json_response)
            action = data["action"]
            validate_action(action, SUPPORTED_ACTIONS)

            parameters = {key: value for key, value in data.items() if key != "action"}
            logger.info(f"Executing action: {action} with parameters: {parameters}")
            action_func = self.actions_map[action]
            result = action_func(**parameters)

            logger.info(f"Action completed: {action}")
            return result
        
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return {"status": "error", "message": "I couldn't understand that request clearly enough to run it."}
        except TypeError as e:
            logger.error(f"Parameter error: {e}")
            return {"status": "error", "message": "I understood the action, but some details were missing or invalid."}
        except Exception as e:
            logger.error(f"Execution error: {e}")
            return {"status": "error", "message": "I couldn't complete that action on your PC."}
