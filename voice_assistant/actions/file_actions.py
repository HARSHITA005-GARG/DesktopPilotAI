import os
from pathlib import Path
from config import DATA_DIR
from utils.logger import get_logger

logger = get_logger(__name__)


def _data_dir_only_error():
    return ValueError(
        f"File access is currently limited to the app data folder: {Path(DATA_DIR).resolve()}. "
        "Broader D: or E: access is not enabled yet."
    )


def _resolve_root(root=None):
    data_root = Path(DATA_DIR).resolve()
    data_root.mkdir(parents=True, exist_ok=True)

    if root:
        requested_root = Path(root).expanduser().resolve()
        if requested_root != data_root:
            raise _data_dir_only_error()

    return data_root


def _resolve_child_path(base_root, file_name):
    file_path = (base_root / file_name).resolve()
    if not str(file_path).startswith(str(base_root)):
        raise ValueError("Invalid file path")
    return file_path


def create_file(target, content="", root=None):
    """Create a file with given content."""
    try:
        base_root = _resolve_root(root)
        file_path = _resolve_child_path(base_root, target)

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Created file: {file_path}")
        return {
            "status": "success",
            "message": f"Created file at {file_path}",
            "file_path": str(file_path),
        }
    
    except Exception as e:
        logger.error(f"Failed to create file: {e}")
        raise


def read_file(file_name, root=None):
    """Read and return file content."""
    try:
        base_root = _resolve_root(root)
        file_path = _resolve_child_path(base_root, file_name)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info(f"Read file: {file_path}")
        return {"status": "success", "content": content, "file_path": str(file_path)}
    
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise
