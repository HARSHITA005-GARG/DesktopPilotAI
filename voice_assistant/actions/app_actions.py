import os
import platform
import subprocess
import time
import csv
import io
import json
import re
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
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "code": "code",
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
    "excel": "Excel",
    "powerpoint": "PowerPoint",
    "calculator": "Calculator",
    "calc": "Calculator",
    "chrome": "Chrome",
    "firefox": "Firefox",
    "brave": "Brave",
    "edge": "Edge",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "code": "Visual Studio Code",
}


NEW_DOCUMENT_KEYS = {
    "word": "^n",
    "excel": "^n",
    "powerpoint": "^n",
    "vs code": "^n",
    "vscode": "^n",
    "visual studio code": "^n",
    "code": "^n",
}


PROCESS_ALIASES = {
    "word": "WINWORD",
    "excel": "EXCEL",
    "powerpoint": "POWERPNT",
    "notepad": "notepad",
    "chrome": "chrome",
    "brave": "brave",
    "edge": "msedge",
    "firefox": "firefox",
    "vs code": "Code",
    "vscode": "Code",
    "visual studio code": "Code",
    "code": "Code",
}


def _launch_windows_app(app_name):
    candidates = []
    raw_name = (app_name or "").strip()
    alias = APPS_WINDOWS.get(raw_name.lower())
    if alias:
        candidates.append(alias)
    candidates.extend(
        [
            raw_name,
            raw_name.lower(),
            f"{raw_name}.exe" if raw_name and not raw_name.lower().endswith(".exe") else raw_name,
            f"{raw_name.lower()}.exe" if raw_name and not raw_name.lower().endswith(".exe") else raw_name.lower(),
        ]
    )

    attempted = set()
    for candidate in candidates:
        normalized = (candidate or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in attempted:
            continue
        attempted.add(key)

        try:
            os.startfile(normalized)
            return
        except OSError:
            pass

        try:
            subprocess.Popen([normalized])
            return
        except OSError:
            pass

        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Start-Process",
                    "-FilePath",
                    normalized,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return
        except Exception:
            continue

    raise FileNotFoundError(f"Could not open application '{app_name}'.")


def _launch_app(system, app_name):
    if system == "Windows":
        _launch_windows_app(app_name)
        return

    if system == "Darwin":
        app = APPS_MAC.get(app_name.lower(), app_name)
        subprocess.Popen(["open", "-a", app])
        return

    if system == "Linux":
        app = APPS_LINUX.get(app_name.lower(), app_name)
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
    normalized = (app_name or "").strip()
    lowered = normalized.lower()
    raw_candidates = [
        window_title,
        WINDOW_TITLES.get(lowered),
        normalized,
        normalized.title(),
        normalized.replace(".exe", ""),
        normalized.replace(".exe", "").title(),
    ]
    return _dedupe_preserve_order(raw_candidates)


def _focus_and_paste(title_candidates, text, pre_keys=None, process_name=None):
    env = os.environ.copy()
    env["AURA_WINDOW_TITLES"] = "||".join(title_candidates)
    env["AURA_TEXT"] = text
    env["AURA_PRE_KEYS"] = pre_keys or ""
    env["AURA_PROCESS_NAME"] = process_name or ""

    script = r"""
$wshell = New-Object -ComObject WScript.Shell
$activated = $false
$titles = $env:AURA_WINDOW_TITLES -split '\|\|'
$processName = $env:AURA_PROCESS_NAME
for ($i = 0; $i -lt 40 -and -not $activated; $i++) {
    foreach ($title in $titles) {
        if ($title -and $wshell.AppActivate($title)) {
            $activated = $true
            break
        }
    }
    if (-not $activated) {
        $matchingProcess = Get-Process |
            Where-Object {
                $_.MainWindowTitle -and (
                    ($processName -and $_.ProcessName -eq $processName) -or
                    ($titles | Where-Object { $_ -and $_.Trim() -and $_.MainWindowTitle -like ('*' + $_ + '*') })
                )
            } |
            Select-Object -First 1
        if ($matchingProcess) {
            $activated = $wshell.AppActivate($matchingProcess.Id)
        }
    }
    if (-not $activated) {
        Start-Sleep -Milliseconds 400
    }
}
if (-not $activated) {
    throw "Could not focus any target window: $env:AURA_WINDOW_TITLES"
}
Start-Sleep -Milliseconds 500
if ($env:AURA_PRE_KEYS) {
    $wshell.SendKeys($env:AURA_PRE_KEYS)
    Start-Sleep -Milliseconds 700
}
Set-Clipboard -Value $env:AURA_TEXT
Start-Sleep -Milliseconds 350
$wshell.SendKeys('^v')
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )


def _parse_tabular_text(content):
    text = (content or "").strip()
    if not text:
        return []

    if "\t" in text:
        delimiter = "\t"
    elif "," in text:
        delimiter = ","
    else:
        return [[text]]

    rows = []
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    for row in reader:
        rows.append([cell.strip() for cell in row])
    return rows


def _write_in_excel(content):
    rows = _parse_tabular_text(content)
    if not rows:
        raise ValueError("Missing text to write in Excel.")

    env = os.environ.copy()
    env["AURA_ROWS_JSON"] = json.dumps(rows)
    script = r"""
$rows = $env:AURA_ROWS_JSON | ConvertFrom-Json
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $true
$workbook = $excel.Workbooks.Add()
$sheet = $workbook.Worksheets.Item(1)

for ($r = 0; $r -lt $rows.Count; $r++) {
    $row = $rows[$r]
    if ($row -isnot [System.Collections.IEnumerable] -or $row -is [string]) {
        $sheet.Cells.Item($r + 1, 1).Value2 = [string]$row
        continue
    }
    for ($c = 0; $c -lt $row.Count; $c++) {
        $sheet.Cells.Item($r + 1, $c + 1).Value2 = [string]$row[$c]
    }
}

$sheet.Activate() | Out-Null
$sheet.Cells.Item(1, 1).Select() | Out-Null
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )


def _parse_presentation_content(content):
    text = (content or "").strip()
    if not text:
        return []

    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    slides = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        title = re.sub(r"^slide\s*\d+\s*:\s*", "", lines[0], flags=re.IGNORECASE).strip()
        body_lines = [re.sub(r"^slide\s*\d+\s*:\s*", "", line, flags=re.IGNORECASE).strip() for line in lines[1:]]
        slides.append({
            "title": title or "Slide",
            "body": "\r\n".join(line for line in body_lines if line),
        })

    if not slides:
        return [{"title": text, "body": ""}]

    if len(slides) == 1 and not slides[0]["body"] and "\n" in text:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            slides[0]["title"] = lines[0]
            slides[0]["body"] = "\r\n".join(lines[1:])

    return slides


def _write_in_powerpoint(content):
    slides = _parse_presentation_content(content)
    if not slides:
        raise ValueError("Missing text to write in PowerPoint.")

    env = os.environ.copy()
    env["AURA_SLIDES_JSON"] = json.dumps(slides)
    script = r"""
$slides = $env:AURA_SLIDES_JSON | ConvertFrom-Json
$powerpoint = New-Object -ComObject PowerPoint.Application
$powerpoint.Visible = -1
$presentation = $powerpoint.Presentations.Add()

for ($i = 0; $i -lt $slides.Count; $i++) {
    $slideData = $slides[$i]
    $layout = 2
    $slide = $presentation.Slides.Add($i + 1, $layout)
    $slide.Shapes.Title.TextFrame.TextRange.Text = [string]$slideData.title

    if ($slide.Shapes.Count -ge 2 -and $slideData.body) {
        $slide.Shapes.Item(2).TextFrame.TextRange.Text = [string]$slideData.body
    }
}

$powerpoint.Activate()
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
        system = platform.system()
        
        logger.info(f"Opening application: {raw_app_name}")
        
        _launch_app(system, raw_app_name)
        
        logger.info(f"Successfully opened {raw_app_name}")
        return {"status": "success", "message": f"Opened {raw_app_name}"}
    
    except Exception as e:
        logger.error(f"Failed to open app: {e}")
        raise


def open_target(target):
    """Open an app, URL, file, or folder."""
    normalized = target.strip()

    if normalized.startswith(("http://", "https://")):
        os.startfile(normalized)
        return {"status": "success", "message": f"Opened {normalized}"}

    if os.path.exists(normalized):
        os.startfile(normalized)
        return {"status": "success", "message": f"Opened {normalized}"}

    try:
        return open_app(normalized)
    except Exception:
        logger.warning("Falling back to shell open for target '%s'.", normalized, exc_info=True)
        os.startfile(normalized)
        return {"status": "success", "message": f"Opened {normalized}"}


def write_in_app(app, content, window_title=None):
    """Open a desktop app and paste the requested content into it."""
    raw_app_name = app.strip()
    app_name = raw_app_name.lower()
    if not (content or "").strip():
        raise ValueError("Missing text to write in the app.")

    if app_name == "excel" and platform.system() == "Windows":
        try:
            _write_in_excel(content)
            return {
                "status": "success",
                "message": "Opened Excel and wrote the requested content.",
            }
        except Exception:
            logger.warning("Excel COM automation failed; falling back to window automation.", exc_info=True)

    if app_name == "powerpoint" and platform.system() == "Windows":
        try:
            _write_in_powerpoint(content)
            return {
                "status": "success",
                "message": "Opened PowerPoint and wrote the requested content.",
            }
        except Exception:
            logger.warning("PowerPoint COM automation failed; falling back to window automation.", exc_info=True)

    open_app(raw_app_name)
    time.sleep(2.5)

    title_candidates = _window_title_candidates(app_name, window_title=window_title)
    pre_keys = NEW_DOCUMENT_KEYS.get(app_name, "")
    process_name = PROCESS_ALIASES.get(app_name, "")
    try:
        _focus_and_paste(
            title_candidates,
            content,
            pre_keys=pre_keys,
            process_name=process_name,
        )
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
