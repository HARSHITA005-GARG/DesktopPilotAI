from utils.logger import get_logger
from utils.json_parser import parse_json_response, validate_action
from config import SUPPORTED_ACTIONS
from actions.app_actions import calculate, open_target, write_in_app
from actions.code_actions import write_code
from actions.datetime_actions import get_datetime
from actions.email_actions import send_email
from actions.file_actions import create_file
from actions.web_actions import browse, play_media

logger = get_logger(__name__)
GENERIC_MEDIA_TITLES = {
    "song",
    "music",
    "video",
    "movie",
    "show",
    "podcast",
    "track",
}


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
            "get_datetime": get_datetime,
            "browse": browse,
            "play_media": play_media,
            "create_file": create_file,
            "write_code": write_code,
            "send_email": send_email,
            "shutdown": shutdown_assistant,
        }

    def _validate_parameters(self, action, parameters):
        if action == "play_media":
            title = str(parameters.get("title", "")).strip()
            if not title:
                raise ValueError("Please specify what to play.")
            if title.lower() in GENERIC_MEDIA_TITLES:
                raise ValueError("Please specify the song, video, or title to play.")

        if action == "send_email":
            receiver = str(parameters.get("receiver", "")).strip()
            if not receiver:
                raise ValueError("Missing email recipient.")
            if "@" not in receiver or "." not in receiver.split("@")[-1]:
                raise ValueError("Please provide a valid email address.")
    
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
            self._validate_parameters(action, parameters)
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
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Execution error: {e}")
            return {"status": "error", "message": str(e)}
