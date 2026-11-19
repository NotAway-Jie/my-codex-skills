# 运行说明

解压后保留 `web-media-intake` 目录结构。这是标准 Codex Skill，包含说明、脚本与参考文件。使用宿主环境已有的 Python 3.11+ 和其他工具。

在 PowerShell 中切到解压后的 skill 目录，检查环境：

~~~powershell
python -B .\scripts\intake.py --doctor
python -B .\scripts\intake.py "https://example.org/article" --dry-run
~~~

在 Codex 中，把整个解压目录放在技能目录，或在当前任务直接提供 `SKILL.md` 的绝对路径。技能会读取正文、带时间戳的字幕和关键帧，再按请求写摘要或提取字段。命令行也可以独立生成这些分析材料。

依功能选择环境中的依赖。网页和本地 HTML 用 `scrapling[fetchers]`，在线视频用 `yt-dlp[default]`，媒体探测、抽帧和字幕提取用 PATH 上的 FFmpeg/ffprobe。仅无字幕语音转录需要 faster-whisper 和已缓存的模型。已可用的网页浏览及图像阅读工具也可直接检查图文，不必为每个任务安装所有依赖。

Firecrawl 使用 HTTPS API，Python 端无需额外 SDK。在已授权的环境中通过凭据管理器提供 `FIRECRAWL_API_KEY`，避免把密钥写进命令、文件或聊天。`--allow-cloud` 允许提交网页 URL。仅对已授权公开内容使用云端网页抓取。

Whisper 默认使用已缓存的 `small` 多语言模型。用 `--model` 可以指定本地模型目录。平台字幕或本地字幕会优先复用。`--fetch-model` 会联网获取模型，仅在获准时使用。

~~~powershell
# 抓取两篇网页，分别保存正文与链接
python -X utf8 -B .\scripts\intake.py "https://example.org/one" "https://example.org/two" --out .\results

# 从入口开始最多抓取 5 个同源页面，包含入口页
python -X utf8 -B .\scripts\intake.py "https://example.org/docs" --crawl 5 --out .\results

# 保存视频并为内容分析准备字幕和截图
python -X utf8 -B .\scripts\intake.py "<视频链接>" --download --frames 6 --language zh --out .\results

# 分析本地视频，已有同名字幕时自动使用
python -X utf8 -B .\scripts\intake.py "D:\data\讲座.mp4" --frames 6 --out .\results

# 仅临时抽帧检查色卡
python -X utf8 -B .\scripts\intake.py "<视频链接>" --frames 3 --frames-only --out "$env:TEMP\palette-review"
~~~

每份输入在输出目录中有独立子目录。网页保存正文 `content.md` 和链接 `links.json`。媒体可保存带时间戳的 `transcript.txt`、`transcript.json`、JPEG 截图及按要求保留的视频源文件。`manifest.json` 记录来源、处理状态、输出路径与局限。清单和独立的链接列表省略 URL 查询字符串。网页正文仍可能包含原始链接。

默认网页处理使用 Scrapling 的 HTTP 抓取。遇到空内容或部分连接错误，可在明确授权后回退到 Firecrawl。站点返回 401、403、429 时会停止当前爬取。站内爬取最多尝试 50 个页面并查询 `robots.txt`。需要操作交互界面、登录或接入特定站点官方 API 时，由调用方另选授权工具。下载兼容性取决于平台当前支持，视频网站的非标准链接可用 `--kind media` 指定。

时间戳字幕选择以指定语言为优先，默认优先中文、再英文。抽样帧记录请求时间且可能略偏离实际图像时间。提取到的段落和帧供 Codex 根据用户的任务写摘要、整理引文或输出字段表。

上游参考：[Scrapling](https://scrapling.readthedocs.io/en/latest/fetching/static.html)、[Firecrawl Scrape API](https://docs.firecrawl.dev/api-reference/endpoint/scrape)、[yt-dlp](https://github.com/yt-dlp/yt-dlp)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[FFmpeg](https://ffmpeg.org/ffmpeg.html)。
