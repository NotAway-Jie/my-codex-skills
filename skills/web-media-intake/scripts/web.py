import json
import os
import time
from collections import deque
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from sources import IntakeError, detect, public_source, write_json


USER_AGENT = "WebMediaIntake/1.0"


class PageError(IntakeError):
    def __init__(self, message, fallback=False, stop=False):
        super().__init__(message)
        self.fallback = fallback
        self.stop = stop


def web_plan(args):
    if args.web_backend != "auto":
        return [args.web_backend]
    return ["scrapling", "firecrawl"] if args.allow_cloud else ["scrapling"]


def selector_page(selector, url):
    roots = selector.css("main") or selector.css("article") or selector.css("body")
    content = roots[0] if roots else selector
    title = selector.css("title::text").get() or selector.css("h1::text").get() or ""
    convert = getattr(content, "markdown", None)
    if callable(convert):
        markdown = convert().strip()
    else:
        markdown = content.get_all_text(strip=True, ignore_tags=(
            "script", "style", "nav", "footer", "noscript", "svg",
        )).strip()
    return {
        "title": title.strip(),
        "markdown": markdown,
        "links": [urljoin(url, link) for link in selector.css("a[href]::attr(href)").getall()],
        "images": list(dict.fromkeys(
            urljoin(url, link)
            for link in list(selector.css('meta[property="og:image"]::attr(content)').getall())
            + list(content.css("img::attr(src), img::attr(data-src)").getall())
            if link and urljoin(url, link).startswith(("http://", "https://"))
        ))[:100],
        "url": url,
    }


def scrapling_page(url, allow_redirects):
    try:
        from scrapling.fetchers import Fetcher
    except ImportError:
        raise PageError("Scrapling fetcher is unavailable. See the skill setup notes.", fallback=True) from None
    try:
        page = Fetcher.get(
            url, stealthy_headers=False, headers={"User-Agent": USER_AGENT},
            follow_redirects="safe" if allow_redirects else False, retries=1, timeout=25,
        )
    except Exception as exc:
        if "curl: (77)" in str(exc) and allow_redirects:
            return system_tls_page(url)
        raise PageError("Scrapling could not connect to the page.", fallback=True) from None
    if page.status in (401, 403, 412, 429):
        raise PageError(f"Origin returned HTTP {page.status}.", stop=True)
    if not 200 <= page.status < 300:
        raise PageError(f"Origin returned HTTP {page.status}.", fallback=page.status >= 500)
    return selector_page(page, str(page.url))


def system_tls_page(url):
    """Retry a local libcurl trust-store loading error with default Python TLS validation."""
    from scrapling import Selector

    try:
        with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as response:
            if response.headers.get_content_type() not in ("text/html", "application/xhtml+xml"):
                raise PageError("The source did not return an HTML page.")
            body = response.read(5_000_001)
            if len(body) > 5_000_000:
                raise PageError("HTML response exceeds 5 MB.")
            return selector_page(Selector(body), response.geturl())
    except HTTPError as exc:
        raise PageError(f"Origin returned HTTP {exc.code}.", stop=exc.code in (401, 403, 412, 429)) from None
    except (URLError, OSError):
        raise PageError("The system TLS client could not read the page.", fallback=True) from None


def firecrawl_page(url):
    key = os.getenv("FIRECRAWL_API_KEY")
    if not key:
        raise PageError("Firecrawl needs FIRECRAWL_API_KEY in the environment.")
    request = Request(
        "https://api.firecrawl.dev/v2/scrape",
        data=json.dumps({"url": url, "formats": ["markdown", "links"],
                         "onlyMainContent": True, "timeout": 30000}).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=45) as response:
            output = json.load(response)
    except HTTPError as exc:
        raise PageError(f"Firecrawl API returned HTTP {exc.code}.",
                        stop=exc.code in (401, 402, 403, 429)) from None
    except (URLError, OSError, ValueError):
        raise PageError("Firecrawl request failed or returned invalid JSON.") from None
    data = output.get("data") if isinstance(output, dict) and output.get("success") else None
    if not isinstance(data, dict):
        raise PageError("Firecrawl returned no page content.")
    meta = data.get("metadata") or {}
    status = meta.get("statusCode")
    if isinstance(status, int) and status >= 400:
        raise PageError(f"Firecrawl reported origin HTTP {status}.", stop=status in (401, 403, 412, 429))
    return {
        "title": meta.get("title") or "",
        "markdown": (data.get("markdown") or "").strip(),
        "links": data.get("links") or [],
        "url": meta.get("sourceURL") or meta.get("url") or url,
    }


def fetch_page(url, args):
    issues = []
    for backend in web_plan(args):
        try:
            page = scrapling_page(url, args.crawl == 1) if backend == "scrapling" else firecrawl_page(url)
            if not page["markdown"]:
                raise PageError("No readable page text. JavaScript rendering may be needed.", fallback=True)
            return page, backend
        except PageError as exc:
            issues.append(f"{backend}: {exc}")
            if not exc.fallback:
                raise PageError(" ".join(issues), stop=exc.stop) from None
    raise PageError(" ".join(issues))


def origin(url):
    parts = urlsplit(url)
    return parts.scheme.lower(), parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)


def crawl_policy(url):
    root = urlsplit(url)
    rule_url = f"{root.scheme}://{root.netloc}/robots.txt"
    rules = RobotFileParser(rule_url)
    try:
        with urlopen(Request(rule_url, headers={"User-Agent": USER_AGENT}), timeout=15) as response:
            rules.parse(response.read(512_000).decode("utf-8", errors="replace").splitlines())
    except HTTPError as exc:
        if exc.code not in (404, 410):
            raise IntakeError(f"Cannot establish crawl rules. robots.txt returned HTTP {exc.code}.") from None
        rules.parse([])
    except (URLError, OSError):
        raise IntakeError("Cannot read robots.txt for this crawl. Try a single page.") from None
    return rules


def save_page(folder, page):
    folder.mkdir(exist_ok=True)
    content = folder / "content.md"
    content.write_text(page["markdown"] + "\n", encoding="utf-8")
    links = folder / "links.json"
    clean_links = [
        public_source(link) for link in page["links"]
        if isinstance(link, str) and link.lower().startswith(("http://", "https://"))
    ]
    write_json(links, list(dict.fromkeys(clean_links)))
    artifacts = {"content": str(content), "links": str(links)}
    if page.get("images"):
        candidates = folder / "image-candidates.json"
        write_json(candidates, page["images"])
        artifacts["image_candidates"] = str(candidates)
    return artifacts


def web_job(source, path, folder, args):
    if path is not None:
        try:
            from scrapling import Selector
        except ImportError:
            raise IntakeError("Local HTML needs Scrapling. See the skill setup notes.") from None
        if path.stat().st_size > 20_000_000:
            raise IntakeError("Local HTML exceeds the 20 MB limit.")
        page = selector_page(Selector(path.read_bytes()), path.as_uri())
        if not page["markdown"]:
            raise IntakeError("No readable text in this HTML file.")
        return {"artifacts": save_page(folder, page), "backend": "scrapling", "title": page["title"]}

    if args.crawl == 1:
        page, backend = fetch_page(source, args)
        return {"artifacts": save_page(folder, page), "backend": backend,
                "title": page["title"], "resolved_source": public_source(page["url"])}

    return crawl(source, folder, args)


def crawl(source, folder, args):
    rules = crawl_policy(source)
    interval = max(1, rules.crawl_delay(USER_AGENT) or 0)
    if interval > 30:
        raise IntakeError("Site-requested crawl delay exceeds 30 seconds. Use single-page jobs.")
    root = origin(source)
    pending = deque([urldefrag(source).url])
    seen = set(pending)
    pages = []
    failures = []
    attempts = 0
    while pending and attempts < args.crawl:
        url = pending.popleft()
        if not rules.can_fetch(USER_AGENT, url):
            failures.append({"source": public_source(url), "error": "Excluded by robots.txt"})
            continue
        if attempts:
            time.sleep(interval)
        attempts += 1
        try:
            page, backend = fetch_page(url, args)
            if origin(page["url"]) != root:
                raise PageError("The page redirected outside the seed origin.")
        except PageError as exc:
            failures.append({"source": public_source(url), "error": str(exc)})
            if exc.stop:
                break
            continue
        artifacts = save_page(folder / f"page-{len(pages) + 1:03d}", page)
        pages.append({"source": public_source(page["url"]), "title": page["title"],
                      "backend": backend, "artifacts": artifacts})
        for raw in page["links"]:
            if len(seen) >= args.crawl * 10:
                break
            if not isinstance(raw, str):
                continue
            try:
                candidate = urldefrag(urljoin(page["url"], raw)).url
                if candidate in seen or origin(candidate) != root or detect(candidate) != "web":
                    continue
            except (ValueError, IntakeError):
                continue
            seen.add(candidate)
            pending.append(candidate)
    status = "ok" if pages and not failures else "partial" if pages else "error"
    return {"status": status, "pages": pages, "failures": failures}
