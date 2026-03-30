import json
from action_executor import ActionExecutor
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Main entry point for the voice assistant."""
    executor = ActionExecutor()
    
    # Example JSON responses from AI
    test_cases = [
        '{"action": "open_app", "parameters": {"app_name": "calculator"}}',
        '{"action": "create_file", "parameters": {"file_name": "test.txt", "content": "Hello, World!"}}',
        '{"action": "read_file", "parameters": {"file_name": "test.txt"}}',
        '{"action": "search_web", "parameters": {"query": "next ipl match"}}',
        '{"action": "write_code", "parameters": {"description": "fibonacci sequence generator"}}',
    ]
    
    logger.info("Voice-Controlled AI Assistant started")
    
    for test_case in test_cases:
        print(f"\n{'='*60}")
        print(f"Processing: {test_case}")
        print(f"{'='*60}")
        
        result = executor.execute(test_case)
        print(f"Result: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
