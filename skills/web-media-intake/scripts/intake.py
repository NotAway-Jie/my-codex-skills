"""Route website and media sources and write artifacts for the calling agent."""

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from media import media_job, save_transcript, subtitle_cues
from post_index import create_index
from sources import IntakeError, detect, is_url, public_source, write_json
from web import web_job, web_plan


def options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="*", help="HTTP(S) URLs or local file paths")
    parser.add_argument("--out", type=Path, default=Path("web-media-output"))
    parser.add_argument("--kind", choices=("auto", "web", "media"), default="auto")
    parser.add_argument("--web-backend", choices=("auto", "scrapling", "firecrawl"), default="auto")
    parser.add_argument("--allow-cloud", action="store_true", help="Allow sending web URLs to Firecrawl")
    parser.add_argument("--crawl", type=int, choices=range(1, 51), metavar="1–50", default=1,
                        help="Maximum same-origin pages per web seed, including the seed")
    parser.add_argument("--download", action="store_true", help="Keep the remote media file")
    parser.add_argument("--download-only", action="store_true", help="Save remote media and skip transcription")
    parser.add_argument("--frames", type=int, choices=range(13), metavar="0–12", default=0,
                        help="Extract this many evenly spaced images when there is video")
    parser.add_argument("--frames-only", action="store_true",
                        help="Extract frames without fetching captions or transcribing audio")
    parser.add_argument("--language", help="Preferred subtitle/transcription language (e.g. zh, en)")
    parser.add_argument("--model", help="Cached faster-whisper model name or a local model directory")
    parser.add_argument("--fetch-model", action="store_true", help="Permit downloading Whisper model weights")
    parser.add_argument("--dry-run", action="store_true", help="Show routing without I/O to sources")
    parser.add_argument("--douyin-index", action="store_true",
                        help="Build a local review queue from supplied links or UTF-8 browser captures")
    parser.add_argument("--doctor", action="store_true", help="Check installed commands and modules")
    args = parser.parse_args()
    if args.web_backend == "firecrawl" and not args.allow_cloud:
        parser.error("--web-backend firecrawl requires --allow-cloud")
    if not args.doctor and not args.sources:
        parser.error("provide a URL or local file")
    if args.frames_only and not args.frames:
        parser.error("--frames-only requires a positive --frames count")
    if args.douyin_index and (args.dry_run or args.doctor):
        parser.error("--douyin-index is a separate local operation")
    return args


def local_document(path, folder, kind):
    if kind == "subtitle":
        cues = subtitle_cues(path)
        if not cues:
            raise IntakeError("No readable timed cues in the subtitle file.")
        return {"artifacts": save_transcript(folder, cues), "transcript_source": "subtitle"}
    if path.stat().st_size > 20_000_000:
        raise IntakeError("Local text exceeds the 20 MB limit. Provide an excerpt or split the file.")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError:
        raise IntakeError("Convert this local text file to UTF-8 and retry.") from None
    if path.suffix.lower() == ".json":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2) + "\n"
        except ValueError:
            raise IntakeError("Local .json file contains invalid JSON.") from None
    output = folder / ("content" + path.suffix.lower())
    output.write_text(text, encoding="utf-8")
    return {"artifacts": {"content": str(output)}}


def process(source, args):
    kind = detect(source, args.kind)
    report = {"source": public_source(source), "kind": kind}
    if args.dry_run:
        if kind == "web":
            report["web_backends"] = web_plan(args)
        return report

    path = None if is_url(source) else Path(source).expanduser().resolve()
    if path is not None and not path.is_file():
        raise IntakeError("Local input file does not exist.")
    args.out.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=f"{kind}-", dir=args.out.resolve()))
    report.update(status="ok", folder=str(folder), manifest=str(folder / "manifest.json"))
    try:
        if kind in ("web", "html"):
            result = web_job(source, path, folder, args)
        elif kind == "media":
            result = media_job(source, path, folder, args)
        elif kind == "image":
            result = {"image_reference": str(path) if path else public_source(source),
                      "status": "needs_visual_review"}
        else:
            result = local_document(path, folder, kind)
        report.update(result)
    except IntakeError as exc:
        report.update(status="error", error=str(exc))
    write_json(folder / "manifest.json", report)
    return report


def main():
    args = options()
    if args.douyin_index:
        try:
            report = create_index(args.sources, args.out)
        except (IntakeError, OSError) as exc:
            print(json.dumps({"status": "error", "error": str(exc)}))
            return 1
        print(json.dumps(report, indent=2))
        return 0
    if args.doctor:
        result = {
            "python": sys.version.split()[0],
            "scrapling": importlib.util.find_spec("scrapling") is not None,
            "yt_dlp": bool(shutil.which("yt-dlp") or importlib.util.find_spec("yt_dlp")),
            "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "ffprobe": bool(shutil.which("ffprobe")),
            "firecrawl_key_present": bool(os.environ.get("FIRECRAWL_API_KEY")),
        }
        print(json.dumps(result, indent=2))
        return 0
    reports = []
    for source in args.sources:
        try:
            reports.append(process(source, args))
        except (IntakeError, OSError) as exc:
            reports.append({"source": public_source(source), "status": "error", "error": str(exc)})
    print(json.dumps(reports[0] if len(reports) == 1 else reports, indent=2))
    return 1 if any(item.get("status") in ("error", "partial") for item in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
