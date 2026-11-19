import json
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit


MEDIA_SUFFIXES = set(
    ".mp4 .m4v .mov .mkv .webm .avi .mpeg .mpg .ts .wmv .flv .m3u8 .mpd "
    ".m4a .mp3 .aac .wav .flac .ogg .oga .opus .wma".split()
)
VIDEO_HOSTS = (
    "youtube.com", "youtu.be", "bilibili.com", "b23.tv", "vimeo.com",
    "tiktok.com", "douyin.com", "ixigua.com", "dailymotion.com", "dai.ly",
    "soundcloud.com", "twitch.tv",
)
LOCAL_KINDS = {
    ".txt": "text", ".md": "text", ".markdown": "text", ".csv": "text",
    ".tsv": "text", ".json": "text", ".html": "html", ".htm": "html",
    ".srt": "subtitle", ".vtt": "subtitle",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".heic"}


class IntakeError(Exception):
    pass


def is_url(source):
    return source.lower().startswith(("http://", "https://"))


def public_source(source):
    """Omit URL queries and user information from generated manifests."""
    if not is_url(source):
        return source
    try:
        parts = urlsplit(source)
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))
    except ValueError:
        return "(invalid URL)"


def detect(source, forced="auto"):
    if is_url(source):
        try:
            url = urlsplit(source)
            host = url.hostname
            _ = url.port
        except ValueError:
            raise IntakeError("Invalid HTTP(S) URL.") from None
        if not host or url.username is not None or url.password is not None:
            raise IntakeError("Use an HTTP(S) URL without embedded credentials.")
        if forced != "auto":
            return forced
        suffix = Path(unquote(url.path)).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            return "image"
        if (host == "douyin.com" or host.endswith(".douyin.com")) and url.path.startswith(("/user/", "/note/")):
            return "web"
        if suffix in MEDIA_SUFFIXES or any(
            host == candidate or host.endswith("." + candidate) for candidate in VIDEO_HOSTS
        ):
            return "media"
        return "web"
    if "://" in source:
        raise IntakeError("Supported inputs are HTTP(S) URLs and local file paths.")
    suffix = Path(source).suffix.lower()
    if forced == "web":
        if suffix not in (".html", ".htm"):
            raise IntakeError("Local web input must be an HTML file.")
        return "html"
    if forced == "media" or suffix in MEDIA_SUFFIXES:
        if suffix in (".m3u8", ".mpd"):
            raise IntakeError("Use a downloaded local media file in place of a local stream playlist.")
        return "media"
    if suffix in LOCAL_KINDS:
        return LOCAL_KINDS[suffix]
    if suffix in IMAGE_SUFFIXES:
        return "image"
    raise IntakeError("Unsupported file type. Supply an image, audio/video, subtitle, HTML, text, CSV or JSON.")


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
