import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "intake.py"
sys.path.insert(0, str(SCRIPT.parent))
from web import PageError, fetch_page


class IntakeTests(unittest.TestCase):
    def run_intake(self, *args, expected=0):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", str(SCRIPT), *map(str, args)],
            capture_output=True, encoding="utf-8", errors="replace", check=False,
        )
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_routing_uses_hostname_and_extension(self):
        for source, kind in [
            ("https://www.bilibili.com/video/BV1test", "media"),
            ("https://assets.example.org/talk.mp4?token=123", "media"),
            ("https://youtube.com.example.org/article", "web"),
            ("https://example.org/post?next=movie.mp4", "web"),
            ("https://www.douyin.com/user/author?vid=123", "web"),
            ("https://www.douyin.com/note/123", "web"),
            ("https://www.douyin.com/video/123", "media"),
            ("https://example.org/card.png", "image"),
        ]:
            with self.subTest(source=source):
                self.assertEqual(self.run_intake(source, "--dry-run")["kind"], kind)

    def test_local_subtitle_preserves_timestamps_and_original_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subtitle = root / "讲座.vtt"
            original = (
                "WEBVTT\n\n00:00.500 --> 00:02.000 align:start\n"
                "<c>从细胞膜开始</c>\n\n00:02.000 --> 00:05.000\nA &amp; B\n"
            )
            subtitle.write_text(original, encoding="utf-8")
            report = self.run_intake(subtitle, "--out", root / "results")
            transcript = Path(report["artifacts"]["transcript"]).read_text(encoding="utf-8")
            self.assertIn("[00:00:00.500 → 00:00:02.000] 从细胞膜开始", transcript)
            self.assertIn("A & B", transcript)
            self.assertEqual(subtitle.read_text(encoding="utf-8"), original)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires FFmpeg")
    def test_local_video_reuses_subtitles_and_extracts_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "talk.mp4"
            subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                 "color=c=blue:s=320x180:r=12:d=3", "-c:v", "mpeg4", str(video)],
                capture_output=True, check=True,
            )
            video.with_suffix(".srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nExample caption\n",
                encoding="utf-8",
            )
            report = self.run_intake(video, "--frames", 2, "--out", root / "results")
            self.assertEqual(report["transcript_source"], "sidecar")
            self.assertEqual([frame["seconds"] for frame in report["frames"]], [0.75, 2.25])
            for frame in report["frames"]:
                self.assertTrue(Path(frame["path"]).read_bytes().startswith(b"\xff\xd8"))
            self.assertNotIn("media", report["artifacts"])
            frames_only = self.run_intake(
                video, "--frames", 1, "--frames-only", "--out", root / "results"
            )
            self.assertNotIn("transcript", frames_only["artifacts"])
            self.assertNotIn("media", frames_only["artifacts"])
            self.assertEqual(len(frames_only["frames"]), 1)

    def test_web_selection_is_local_unless_cloud_requested(self):
        source = "https://example.org/"
        self.assertEqual(self.run_intake(source, "--dry-run")["web_backends"], ["scrapling"])
        self.assertEqual(
            self.run_intake(source, "--dry-run", "--web-backend", "auto", "--allow-cloud")[
                "web_backends"
            ],
            ["scrapling", "firecrawl"],
        )

    def test_douyin_browser_capture_deduplicates_and_requires_media_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "visible-links.html"
            page.write_text(
                '<a href="/note/1000000000000000001">配色一</a>'
                '<a href="https://www.douyin.com/note/1000000000000000001?tracking=x">重复</a>'
                '<a href="/video/1000000000000000002">配色视频</a>'
                '<a href="https://douyin.com.example.org/note/1000000000000000003">外站</a>'
                '<script>"/note/1000000000000000004"</script>',
                encoding="utf-8",
            )
            copied = root / "shared.txt"
            copied.write_text(
                "Value: douyin.com/note/1000000000000000003\n"
                "https://www.douyin.com/user/test?from_tab_name=main&vid=1000000000000000001",
                encoding="utf-8",
            )
            result = self.run_intake(page, copied, "--douyin-index", "--out", root / "results")
            index = json.loads(Path(result["index"]).read_text(encoding="utf-8"))
            self.assertEqual(index["post_count"], 3)
            self.assertEqual(index["coverage"], "unverified")
            self.assertEqual([p["kind"] for p in index["posts"]], ["note", "video", "note"])
            self.assertTrue(all(p["status"] == "pending_review" for p in index["posts"]))
            self.assertEqual(index["posts"][0]["url"],
                             "https://www.douyin.com/note/1000000000000000001")

    def test_web_fallback_only_after_a_permitted_failure(self):
        args = SimpleNamespace(web_backend="auto", allow_cloud=True, crawl=1)
        url = "https://example.org/article"
        rendered = {"url": url, "title": "Article", "markdown": "Rendered text", "links": []}
        with patch("web.scrapling_page", return_value={**rendered, "markdown": ""}), \
                patch("web.firecrawl_page", return_value=rendered):
            page, backend = fetch_page(url, args)
            self.assertEqual((page["markdown"], backend), ("Rendered text", "firecrawl"))
        with patch("web.scrapling_page", side_effect=PageError("Origin returned HTTP 429.", stop=True)), \
                patch("web.firecrawl_page", side_effect=AssertionError("must stop on rate limiting")):
            with self.assertRaisesRegex(PageError, "429"):
                fetch_page(url, args)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires FFmpeg")
    def test_embedded_text_subtitles_are_extracted_without_whisper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "talk.mkv"
            caption = root / "caption.srt"
            caption.write_text("1\n00:00:00,100 --> 00:00:01,000\nEmbedded evidence\n", encoding="utf-8")
            subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                 "color=c=blue:s=320x180:r=12:d=2", "-i", str(caption),
                 "-c:v", "mpeg4", "-c:s", "srt", str(video)],
                capture_output=True, check=True,
            )
            report = self.run_intake(video, "--out", root / "results")
            self.assertEqual(report["transcript_source"], "embedded_subtitle")
            data = json.loads(Path(report["artifacts"]["timed_segments"]).read_text(encoding="utf-8"))
            self.assertEqual(data, [{"start": 0.1, "end": 1.0, "text": "Embedded evidence"}])


if __name__ == "__main__":
    unittest.main()
