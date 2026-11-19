"""Build a Douyin review queue from user-provided links or rendered browser captures."""

import re
import tempfile
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from sources import IntakeError, write_json


MAX_CAPTURE_BYTES = 20_000_000
DOUYIN_ROOT = "https://www.douyin.com"
POST_PATH = re.compile(r"^/(note|video)/([0-9]{15,25})/?$")
POST_ID = re.compile(r"^[0-9]{15,25}$")
PROFILE_PATH = re.compile(r"^/user/([A-Za-z0-9_-]+)/?$")
SHARE_PATH = re.compile(r"^/[A-Za-z0-9_-]+/?$")
TEXT_LINK = re.compile(
    r'(?<![\w./@-])(?:https?://|(?=(?:www\.|v\.)?douyin\.com/))'
    r'[a-z0-9.-]+/[^\s<>"\x27，。；、！）】》]+', re.I,
)


class PostAnchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for name, value in attrs if name == "href" and value)


def browser_links(source):
    if source.lower().startswith(("https://", "http://")):
        return [source]
    path = Path(source).expanduser()
    if not path.is_file():
        raise IntakeError("Provide a Douyin URL or a local UTF-8 capture file.")
    if path.stat().st_size > MAX_CAPTURE_BYTES:
        raise IntakeError("Browser capture exceeds 20 MB. Split it into smaller batches.")
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeError:
        raise IntakeError("Convert the browser capture to UTF-8.") from None
    if path.suffix.lower() in (".html", ".htm"):
        parser = PostAnchors()
        parser.feed(content)
        return parser.links
    if path.suffix.lower() in (".txt", ".md"):
        return [match.group().rstrip(".,;)") for match in TEXT_LINK.finditer(content)]
    raise IntakeError("Use a UTF-8 .txt, .md or .html browser capture.")


def normalize(link):
    link = unescape(link).strip()
    if link.startswith("//"):
        link = "https:" + link
    elif link.startswith("/"):
        link = DOUYIN_ROOT + link
    elif not link.lower().startswith(("https://", "http://")):
        link = "https://" + link
    try:
        url = urlsplit(link)
        if url.username is not None or url.password is not None or url.port is not None:
            return None
    except ValueError:
        return None
    if url.hostname == "v.douyin.com" and SHARE_PATH.fullmatch(url.path):
        clean = f"https://v.douyin.com{url.path.rstrip('/')}/"
        return clean, {"kind": "short_link", "url": clean, "status": "needs_resolution"}
    if url.hostname not in ("douyin.com", "www.douyin.com"):
        return None
    match = POST_PATH.fullmatch(url.path)
    if match:
        kind, post_id = match.groups()
        return post_id, {"post_id": post_id, "kind": kind,
                         "url": f"{DOUYIN_ROOT}/{kind}/{post_id}", "status": "pending_review"}
    profile = PROFILE_PATH.fullmatch(url.path)
    if profile is None:
        return None
    values = parse_qs(url.query).get("vid", [])
    if len(values) == 1 and POST_ID.fullmatch(values[0]):
        post_id = values[0]
        return post_id, {
            "post_id": post_id, "kind": "unknown", "status": "needs_resolution",
            "url": f"{DOUYIN_ROOT}/user/{profile[1]}?vid={post_id}",
        }
    return None


def create_index(sources, out):
    records = {}
    for source in sources:
        for link in browser_links(source):
            item = normalize(link)
            if item is None:
                continue
            key, post = item
            previous = records.get(key)
            if previous is None or (previous["kind"] == "unknown" and post["kind"] != "unknown"):
                records[key] = post
    if not records:
        raise IntakeError("No Douyin posts in the capture. Supply links or copy the visible post list.")
    out.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="douyin-index-", dir=out.resolve()))
    path = folder / "post-index.json"
    posts = list(records.values())
    post_count = sum(post["status"] == "pending_review" for post in posts)
    write_json(path, {
        "platform": "douyin", "coverage": "unverified", "post_count": post_count,
        "unresolved_count": len(posts) - post_count, "posts": posts,
    })
    return {"status": "index_created", "index": str(path), "post_count": post_count,
            "unresolved_count": len(posts) - post_count, "coverage": "unverified"}
