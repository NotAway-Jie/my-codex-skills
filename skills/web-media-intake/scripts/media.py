import html
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sources import IntakeError, write_json


CUE_TIME = r"(?:\d{1,3}:)?\d{2}:\d{2}[.,]\d{3}"
CUE_LINE = re.compile(rf"^({CUE_TIME})\s+-->\s+({CUE_TIME})(?:\s|$)")
TEXT_CODECS = {"ass", "ssa", "subrip", "mov_text", "webvtt", "text", "srt"}
CAPTION_SUFFIXES = (".srt", ".vtt")


def seconds(time):
    value = 0.0
    for part in time.replace(",", ".").split(":"):
        value = value * 60 + float(part)
    return value


def timestamp(seconds_value):
    mins, millis = divmod(round(seconds_value * 1000), 60000)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{millis // 1000:02d}.{millis % 1000:03d}"


def subtitle_cues(path):
    if path.stat().st_size > 10_000_000:
        raise IntakeError("Subtitle file exceeds 10 MB.")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    cues = []
    for block in re.split(r"\n[ \t]*\n", text):
        lines = block.splitlines()
        if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION", "WEBVTT")):
            continue
        for index, line in enumerate(lines[:2]):
            match = CUE_LINE.match(line.strip())
            if match:
                start, end = map(seconds, match.groups())
                caption = html.unescape(re.sub(r"<[^>]*>", "", " ".join(lines[index + 1:])))
                caption = " ".join(caption.split())
                if caption and end >= start:
                    cue = {"start": start, "end": end, "text": caption}
                    if not cues or cue != cues[-1]:
                        cues.append(cue)
                break
    return cues


def save_transcript(folder, cues):
    transcript = folder / "transcript.txt"
    transcript.write_text("".join(
        f"[{timestamp(cue['start'])} → {timestamp(cue['end'])}] {cue['text']}\n"
        for cue in cues
    ), encoding="utf-8")
    timed = folder / "transcript.json"
    write_json(timed, cues)
    return {"transcript": str(transcript), "timed_segments": str(timed)}


def run(command, label, timeout=180, required=True, binary=False):
    try:
        text_options = {} if binary else {"encoding": "utf-8", "errors": "replace"}
        result = subprocess.run(command, capture_output=True, timeout=timeout,
                                check=False, **text_options)
    except subprocess.TimeoutExpired:
        raise IntakeError(f"{label} timed out.") from None
    except OSError:
        raise IntakeError(f"Could not start {label}. Check installed dependencies.") from None
    if required and result.returncode:
        raise IntakeError(f"{label} failed (exit {result.returncode}).")
    return result


def caption_rank(name, language):
    code = name.lower().replace("_", "-")
    code = {"chi": "zh", "zho": "zh", "eng": "en", "jpn": "ja"}.get(code, code)
    if language:
        exact = language.lower().replace("_", "-")
        preferred = (exact, exact.split("-")[0])
    else:
        preferred = ("zh", "en")
    return next((i for i, key in enumerate(preferred)
                 if code == key or code.startswith(key + "-")), len(preferred))


def file_captions(media, language):
    prefix = media.stem + "."
    choices = [item for item in media.parent.iterdir() if item.is_file()
               and item.name.startswith(prefix) and item.suffix.lower() in CAPTION_SUFFIXES]
    choices.sort(key=lambda item: (
        caption_rank(item.stem[len(prefix):], language), item.name != media.stem + item.suffix,
        item.name,
    ))
    for path in choices:
        cues = subtitle_cues(path)
        if cues:
            return cues
    return []


def probe(media):
    result = run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                  "-show_format", "-show_streams", "-of", "json", str(media)], "ffprobe")
    try:
        info = json.loads(result.stdout)
    except ValueError:
        raise IntakeError("ffprobe returned invalid media metadata.") from None
    return info.get("streams", []), info.get("format", {})


def ffmpeg_input(media):
    return ["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(media)]


def embedded_captions(media, streams, language, scratch):
    choices = [stream for stream in streams if stream.get("codec_type") == "subtitle"
               and stream.get("codec_name") in TEXT_CODECS]
    choices.sort(key=lambda stream: caption_rank(stream.get("tags", {}).get("language", ""), language))
    for stream in choices:
        output = scratch / f"embedded-{stream['index']}.srt"
        command = ffmpeg_input(media) + ["-map", f"0:{stream['index']}", "-c:s", "srt", str(output)]
        result = run(command, "FFmpeg subtitle extraction", required=False)
        if result.returncode == 0 and output.is_file():
            cues = subtitle_cues(output)
            if cues:
                return cues
    return []


def transcribe(media, args):
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError:
        raise IntakeError("No usable subtitle. Install faster-whisper to transcribe the audio.") from None
    model_name = args.model or os.getenv("WEB_MEDIA_WHISPER_MODEL") or "small"
    # Prefer the existing local file when a model directory is specified.
    model_directory = Path(model_name).expanduser()
    if model_directory.is_dir():
        model_name = str(model_directory.resolve())
    audio = run(
        ffmpeg_input(media) + ["-map", "0:a:0", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
        "FFmpeg audio decoding", timeout=900, binary=True,
    ).stdout
    samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
    if not samples.size:
        return [], args.language
    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8",
                             local_files_only=not args.fetch_model)
        segments, info = model.transcribe(samples, language=args.language, vad_filter=True)
        cues = [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
                for s in segments if s.text.strip()]
    except Exception as exc:
        raise IntakeError(
            f"Whisper transcription failed ({type(exc).__name__}). Check the cached model or local model path."
        ) from None
    return cues, info.language


def yt_command():
    if importlib.util.find_spec("yt_dlp"):
        return [sys.executable, "-X", "utf8", "-m", "yt_dlp"]
    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]
    raise IntakeError("Video URL needs yt-dlp. See the skill setup notes.")


def fetch_remote(source, folder, scratch, args):
    keep = args.download or args.download_only
    need_frames = bool(args.frames)
    base = yt_command() + [
        "--ignore-config", "--no-plugin-dirs", "--no-playlist", "--playlist-items", "1",
        "--no-progress", "--no-overwrites", "--no-warnings",
        "--restrict-filenames", "--windows-filenames", "--socket-timeout", "20",
        "--encoding", "UTF-8", "--match-filter", "!is_live",
    ]
    if shutil.which("node"):
        base += ["--js-runtimes", "node"]
    captions = ["--write-subs", "--write-auto-subs", "--sub-format", "vtt/srt",
                "--sub-langs", re.escape(args.language) + ".*,-live_chat" if args.language
                else "zh.*,en.*,-live_chat"]
    cues = []
    if not (keep or need_frames):
        lookup = run(base + captions + ["--skip-download", "-o", str(scratch / "source.%(ext)s"),
                                        "--", source], "yt-dlp subtitle lookup", required=False)
        cues = file_captions(scratch / "source.mp4", args.language)
        if cues:
            return None, cues
        if re.search(r"HTTP Error (401|403|429)\b|sign in|DRM.protected", lookup.stderr, re.I):
            raise IntakeError("The platform blocked this video or its subtitles. Supply an authorized local file.")
    target = folder if keep else scratch
    get_captions = not (args.download_only or args.frames_only) and (keep or need_frames)
    flags = captions.copy() if get_captions else []
    if not (keep or need_frames):
        flags += ["-f", "bestaudio/best"]
    result = run(
        base + flags + ["--print", "after_move:filepath", "-o", str(target / "source.%(ext)s"),
                       "--", source], "yt-dlp download", timeout=900,
    )
    for line in reversed(result.stdout.splitlines()):
        media = Path(line.strip()).resolve()
        if media.parent == target.resolve() and media.is_file():
            return media, file_captions(media, args.language) if get_captions else []
    raise IntakeError("yt-dlp did not report a verified local media file.")


def extract_frames(media, duration, count, video_index, folder):
    images = folder / "frames"
    images.mkdir()
    frames = []
    for index in range(count):
        offset = round((index + 0.5) * duration / count, 3)
        output = images / f"frame-{index + 1:02d}.jpg"
        command = ["ffmpeg", "-nostdin", "-v", "error", "-ss", str(offset),
                   "-protocol_whitelist", "file,pipe", "-i", str(media),
                   "-map", f"0:{video_index}", "-frames:v", "1",
                   "-vf", "scale=min(1280\\,iw):-2", "-q:v", "3", str(output)]
        run(command, "FFmpeg frame extraction", required=False)
        if output.is_file() and output.stat().st_size:
            frames.append({"seconds": offset, "path": str(output)})
    return frames


def duration_of(metadata):
    try:
        number = float(metadata.get("duration", 0))
        return number if math.isfinite(number) and number > 0 else 0
    except (ValueError, TypeError):
        return 0


def analyze(media, folder, scratch, args, cues, result):
    artifacts = result["artifacts"]
    issues = []
    streams, fmt = probe(media)
    duration = duration_of(fmt)
    result["duration_seconds"] = duration
    result["streams"] = [
        {key: stream[key] for key in ("index", "codec_name", "codec_type", "width", "height")
         if key in stream} for stream in streams
    ]
    if not (args.download_only or args.frames_only):
        if not cues:
            cues = embedded_captions(media, streams, args.language, scratch)
            if cues:
                result["transcript_source"] = "embedded_subtitle"
        if not cues and any(stream.get("codec_type") == "audio" for stream in streams):
            try:
                cues, language = transcribe(media, args)
                result.update(transcript_source="faster_whisper", transcript_language=language)
            except IntakeError as exc:
                issues.append(str(exc))
        if cues:
            artifacts.update(save_transcript(folder, cues))
        elif not issues:
            issues.append("No usable subtitle or recognized speech.")

    if args.frames:
        video = next((stream for stream in streams if stream.get("codec_type") == "video"
                      and not stream.get("disposition", {}).get("attached_pic")), None)
        frames = extract_frames(media, duration, args.frames, video["index"], folder) if video and duration else []
        result["frames"] = frames
        if len(frames) != args.frames:
            issues.append(f"Extracted {len(frames)} of {args.frames} requested frames.")
    if issues:
        result.update(status="partial" if artifacts or result.get("frames") else "error", issues=issues)


def media_job(source, local, folder, args):
    result = {"artifacts": {}}
    if args.download_only and local is not None:
        raise IntakeError("Local media already exists. Remove --download-only to analyze it.")
    with TemporaryDirectory(prefix=".work-", dir=folder) as scratch_dir:
        scratch = Path(scratch_dir)
        if local is None:
            media, cues = fetch_remote(source, folder, scratch, args)
            if cues:
                result["transcript_source"] = "platform_subtitle"
            if media is None:
                result["artifacts"].update(save_transcript(folder, cues))
                return result
            if args.download or args.download_only:
                result["artifacts"]["media"] = str(media)
        else:
            media = local
            cues = file_captions(media, args.language)
            if cues:
                result["transcript_source"] = "sidecar"
        try:
            analyze(media, folder, scratch, args, cues, result)
        except IntakeError as exc:
            if cues:
                result["artifacts"].update(save_transcript(folder, cues))
            result.update(status="partial" if result["artifacts"] else "error", issues=[str(exc)])
        return result
