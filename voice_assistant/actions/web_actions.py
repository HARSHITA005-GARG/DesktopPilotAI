import webbrowser
import subprocess
from urllib.parse import quote
from config import SEARCH_ENGINE_URL
from utils.logger import get_logger

logger = get_logger(__name__)


BROWSER_COMMANDS = {
    "chrome": "chrome",
    "firefox": "firefox",
    "brave": "brave",
    "edge": "msedge",
}


PLATFORM_ALIASES = {
    "youtube": "youtube",
    "youtube.com": "youtube",
    "yt": "youtube",
    "youtube video": "youtube",
    "youtube videos": "youtube",
    "youtube music": "youtube_music",
    "yt music": "youtube_music",
    "music.youtube.com": "youtube_music",
    "spotify": "spotify",
    "spotify music": "spotify",
    "open.spotify.com": "spotify",
    "netflix": "netflix",
    "netflix.com": "netflix",
    "hotstar": "hotstar",
    "disney+ hotstar": "hotstar",
    "hotstar.com": "hotstar",
}


def _open_in_browser(target_url, preferred_browser=None):
    if preferred_browser:
        command = BROWSER_COMMANDS.get(preferred_browser)
        if not command:
            raise ValueError(f"Unsupported browser '{preferred_browser}'.")
        try:
            subprocess.Popen([command, target_url])
        except OSError:
            webbrowser.open(target_url)
    else:
        webbrowser.open(target_url)


def _normalize_url(value):
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith(("http://", "https://")):
        return cleaned
    if " " in cleaned:
        return None
    return f"https://{cleaned}"


def _build_url(query=None, site=None, url=None):
    target_url = _normalize_url(url) or _normalize_url(site)

    if target_url and query:
        return SEARCH_ENGINE_URL + quote(f"site:{target_url} {query}")
    if target_url:
        return target_url
    if query:
        return SEARCH_ENGINE_URL + quote(query)

    raise ValueError("Provide a url, a query, or a site.")


def _normalize_platform(platform):
    cleaned = (platform or "").strip().lower()
    return PLATFORM_ALIASES.get(cleaned, cleaned)


def _media_target(platform, title):
    media_title = quote(title)
    normalized_platform = _normalize_platform(platform)

    if normalized_platform == "youtube":
        return normalized_platform, f"https://www.youtube.com/results?search_query={media_title}"
    if normalized_platform == "youtube_music":
        return normalized_platform, f"https://music.youtube.com/search?q={media_title}"
    if normalized_platform == "spotify":
        return normalized_platform, f"https://open.spotify.com/search/{media_title}"
    if normalized_platform == "netflix":
        return normalized_platform, f"https://www.netflix.com/search?q={media_title}"
    if normalized_platform == "hotstar":
        return normalized_platform, f"https://www.hotstar.com/in/search?q={media_title}"
    if normalized_platform:
        return normalized_platform, SEARCH_ENGINE_URL + quote(f"site:{normalized_platform} {title}")
    return None, SEARCH_ENGINE_URL + quote(title)


def browse(query=None, browser=None, site=None, url=None):
    """Open a URL or search query in a chosen browser when possible."""
    target_url = _build_url(query=query, site=site, url=url)
    preferred_browser = (browser or "").strip().lower()

    logger.info("Opening browser target: %s", target_url)
    _open_in_browser(target_url, preferred_browser=preferred_browser or None)

    if query:
        message = (
            f"I searched for '{query}'"
            + (f" in {preferred_browser}" if preferred_browser else "")
            + f" and opened the results at {target_url}."
        )
    else:
        message = (
            f"I opened {target_url}"
            + (f" in {preferred_browser}." if preferred_browser else ".")
        )

    return {
        "status": "success",
        "message": message,
        "url": target_url,
        "query": query,
        "browser": preferred_browser or None,
    }


def play_media(title, platform=None, browser=None):
    """Open a platform-specific playback/search URL for media."""
    media_title = (title or "").strip()
    if not media_title:
        raise ValueError("Missing media title.")

    requested_platform = (platform or "").strip()
    preferred_browser = (browser or "").strip().lower() or None
    target_platform, target_url = _media_target(requested_platform, media_title)

    logger.info("Opening media target: %s", target_url)
    _open_in_browser(target_url, preferred_browser=preferred_browser)

    return {
        "status": "success",
        "message": (
            f"I opened {target_platform or 'the browser'} for '{media_title}'."
        ),
        "url": target_url,
        "title": media_title,
        "platform": target_platform or None,
        "browser": preferred_browser,
    }


def search_web(query):
    """Open web search in default browser."""
    try:
        return browse(query=query)
    
    except Exception as e:
        logger.error(f"Failed to search web: {e}")
        raise
