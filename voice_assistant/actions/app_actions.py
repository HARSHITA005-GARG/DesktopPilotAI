import os
import platform
import subprocess
import time
from ast import Add, BinOp, Constant, Div, Expression, Mult, Pow, Sub, UAdd, USub, UnaryOp, parse
from utils.logger import get_logger

logger = get_logger(__name__)

APPS_WINDOWS = {
    "chrome": "chrome",
    "brave": "brave",
    "edge": "msedge",
    "firefox": "firefox",
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "powershell": "powershell",
}

APPS_LINUX = {
    "chrome": "google-chrome",
    "firefox": "firefox",
    "notepad": "gedit",
    "calculator": "gnome-calculator",
}

APPS_MAC = {
    "chrome": "Google Chrome",
    "firefox": "Firefox",
    "notepad": "TextEdit",
    "calculator": "Calculator",
}


WINDOW_TITLES = {
    "notepad": "Notepad",
    "word": "Word",
    "calculator": "Calculator",
    "calc": "Calculator",
    "chrome": "Chrome",
    "firefox": "Firefox",
    "brave": "Brave",
    "edge": "Edge",
}


def _launch_windows_app(app_name):
    candidates = []
    alias = APPS_WINDOWS.get(app_name)
    if alias:
        candidates.append(alias)
    candidates.append(app_name)

    attempted = []
    for candidate in candidates:
        if candidate in attempted:
            continue
        attempted.append(candidate)

        try:
            os.startfile(candidate)
            return
        except OSError:
            try:
                subprocess.Popen([candidate])
                return
            except OSError:
                continue

    raise FileNotFoundError(f"Could not open application '{app_name}'.")


def _launch_app(system, app_name):
    if system == "Windows":
        _launch_windows_app(app_name)
        return

    if system == "Darwin":
        app = APPS_MAC.get(app_name, app_name)
        subprocess.Popen(["open", "-a", app])
        return

    if system == "Linux":
        app = APPS_LINUX.get(app_name, app_name)
        subprocess.Popen([app])
        return

    raise ValueError(f"Unsupported platform '{system}'")


def _dedupe_preserve_order(values):
    result = []
    seen = set()
    for value in values:
        normalized = (value or "").strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _window_title_candidates(app_name, window_title=None):
    raw_candidates = [
        window_title,
        WINDOW_TITLES.get(app_name),
        app_name,
        app_name.title(),
    ]
    return _dedupe_preserve_order(raw_candidates)


def _focus_and_paste(title_candidates, text, pre_keys=None):
    env = os.environ.copy()
    env["AURA_WINDOW_TITLES"] = "||".join(title_candidates)
    env["AURA_TEXT"] = text
    env["AURA_PRE_KEYS"] = pre_keys or ""

    script = r"""
$wshell = New-Object -ComObject WScript.Shell
$activated = $false
$titles = $env:AURA_WINDOW_TITLES -split '\|\|'
for ($i = 0; $i -lt 30 -and -not $activated; $i++) {
    foreach ($title in $titles) {
        if ($title -and $wshell.AppActivate($title)) {
            $activated = $true
            break
        }
    }
    if (-not $activated) {
        Start-Sleep -Milliseconds 400
    }
}
if (-not $activated) {
    throw "Could not focus any target window: $env:AURA_WINDOW_TITLES"
}
if ($env:AURA_PRE_KEYS) {
    $wshell.SendKeys($env:AURA_PRE_KEYS)
    Start-Sleep -Milliseconds 400
}
Set-Clipboard -Value $env:AURA_TEXT
Start-Sleep -Milliseconds 200
$wshell.SendKeys('^v')
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )


def _write_in_word(content):
    env = os.environ.copy()
    env["AURA_TEXT"] = content
    script = r"""
$word = New-Object -ComObject Word.Application
$word.Visible = $true
$document = $word.Documents.Add()
$selection = $word.Selection
$selection.TypeText($env:AURA_TEXT)
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )


def _safe_eval(expression):
    allowed_nodes = (Expression, BinOp, UnaryOp, Constant, Add, Sub, Mult, Div, Pow, UAdd, USub)
    tree = parse(expression, mode="eval")

    for node in ast_walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError("Only basic arithmetic is allowed.")
        if isinstance(node, Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric values are allowed.")

    return eval(compile(tree, "<expression>", "eval"), {"__builtins__": {}}, {})


def ast_walk(node):
    yield node
    for child in getattr(node, "_fields", []):
        value = getattr(node, child)
        if isinstance(value, list):
            for item in value:
                if hasattr(item, "_fields"):
                    yield from ast_walk(item)
        elif hasattr(value, "_fields"):
            yield from ast_walk(value)


def open_app(app_name):
    """Open an application by name."""
    try:
        raw_app_name = app_name.strip()
        app_name = raw_app_name.lower()
        system = platform.system()
        
        logger.info(f"Opening application: {raw_app_name}")
        
        _launch_app(system, app_name)
        
        logger.info(f"Successfully opened {raw_app_name}")
        return {"status": "success", "message": f"Opened {raw_app_name}"}
    
    except Exception as e:
        logger.error(f"Failed to open app: {e}")
        raise


def open_target(target):
    """Open an app, URL, file, or folder."""
    normalized = target.strip()
    lowered = normalized.lower()

    if lowered in APPS_WINDOWS or lowered in APPS_LINUX or lowered in APPS_MAC:
        return open_app(lowered)

    if normalized.startswith(("http://", "https://")):
        os.startfile(normalized)
        return {"status": "success", "message": f"Opened {normalized}"}

    os.startfile(normalized)
    return {"status": "success", "message": f"Opened {normalized}"}


def write_in_app(app, content, window_title=None):
    """Open a desktop app and paste the requested content into it."""
    raw_app_name = app.strip()
    app_name = raw_app_name.lower()
    if app_name == "word" and platform.system() == "Windows":
        try:
            _write_in_word(content)
            return {
                "status": "success",
                "message": "I opened Word and wrote the requested content.",
            }
        except Exception:
            logger.warning("Word COM automation failed; falling back to window automation.", exc_info=True)

    open_app(raw_app_name)
    time.sleep(2.5)

    title_candidates = _window_title_candidates(app_name, window_title=window_title)
    pre_keys = "^n" if app_name == "word" else ""
    try:
        _focus_and_paste(title_candidates, content, pre_keys=pre_keys)
    except Exception:
        logger.warning("Window focus/paste failed for app '%s'.", raw_app_name, exc_info=True)
        raise

    return {
        "status": "success",
        "message": f"Opened {raw_app_name} and wrote the requested content.",
    }


def calculate(expression):
    """Evaluate arithmetic and also open Calculator with the expression pasted in."""
    result = _safe_eval(expression)
    open_app("calculator")
    try:
        time.sleep(1.2)
        _focus_and_paste(_window_title_candidates("calculator"), expression)
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$wshell = New-Object -ComObject WScript.Shell; "
                "$null = $wshell.AppActivate('Calculator'); "
                "Start-Sleep -Milliseconds 200; "
                "$wshell.SendKeys('=')",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        logger.warning("Could not type expression into Calculator window.", exc_info=True)

    return {
        "status": "success",
        "message": f"I calculated {expression}. The result is {result}.",
        "expression": expression,
        "result": result,
    }
