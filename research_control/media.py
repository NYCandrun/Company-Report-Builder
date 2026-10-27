"""Timestamped transcripts for public video and audio sources.

Order of preference for YouTube: published captions, captions through yt-dlp
with alternate player clients, then audio through a public Invidious instance
transcribed locally with Whisper. Other media: a public audio download
transcribed with Whisper. YouTube requests are spaced to avoid rate limits. A source that yields neither is recorded
with the reason. Machine transcripts do
not establish speaker identity.

The tools are optional host capabilities (``yt-dlp``, ``youtube-transcript-api``,
``faster-whisper``). When one is missing the transcript is recorded as
unavailable with that reason; the page capture itself still stands.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from research_control.io import atomic_write_text


WHISPER_MODEL = os.environ.get("RESEARCH_CONTROL_WHISPER_MODEL", "small.en")
MEDIA_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "wistia.com", "loom.com", "spotify.com",
               "podcasts.apple.com", "buzzsprout.com", "podbean.com", "transistor.fm", "megaphone.fm",
               "simplecast.com", "libsyn.com", "anchor.fm", "soundcloud.com")
AUDIO_SUFFIXES = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".mp4", ".webm")


def is_media_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    return any(host == name or host.endswith(f".{name}") for name in MEDIA_HOSTS) or parsed.path.casefold().endswith(AUDIO_SUFFIXES)


def youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0] or None
    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live", "v"}:
            return parts[1]
    return None


def _stamp(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600:02d}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


def _captions(video_id: str) -> list[tuple[float, str]]:
    from youtube_transcript_api import YouTubeTranscriptApi

    fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en", "en-US", "en-GB"])
    return [(float(item.start), item.text.replace("\n", " ").strip()) for item in fetched if item.text.strip()]


YT_CAPTION_CLIENTS = (None, "web_embedded", "android_vr")
YT_REQUEST_SPACING_SECONDS = float(os.environ.get("RESEARCH_CONTROL_YT_SPACING", "20"))
INVIDIOUS_INSTANCES = tuple(
    value.strip().rstrip("/") for value in os.environ.get(
        "RESEARCH_CONTROL_INVIDIOUS", "https://invidious.schenkel.eti.br"
    ).split(",") if value.strip()
)
_last_youtube_request = 0.0


def _pace_youtube() -> None:
    """Space YouTube requests; bursts trigger 429s and bot checks."""
    global _last_youtube_request
    wait = YT_REQUEST_SPACING_SECONDS - (time.monotonic() - _last_youtube_request)
    if wait > 0:
        time.sleep(wait)
    _last_youtube_request = time.monotonic()


def _vtt_lines(text: str) -> list[tuple[float, str]]:
    """Parse WebVTT, dropping inline tags and the rolling repeats of auto-captions."""
    lines: list[tuple[float, str]] = []
    start: float | None = None
    for raw in text.splitlines():
        timing = re.match(r"(\d+):(\d{2}):(\d{2})[.,](\d{3}) -->", raw.strip())
        if timing:
            hours, minutes, seconds, millis = (int(value) for value in timing.groups())
            start = hours * 3600 + minutes * 60 + seconds + millis / 1000
            continue
        value = re.sub(r"<[^>]+>", "", raw).strip()
        if start is None or not value or value.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if lines and (value == lines[-1][1] or lines[-1][1].endswith(value)):
            continue
        lines.append((start, value))
    return lines


def _ytdlp_captions(url: str, directory: Path) -> tuple[list[tuple[float, str]], str]:
    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp is unavailable for caption download")
    failures: list[str] = []
    for client in YT_CAPTION_CLIENTS:
        _pace_youtube()
        command = [
            "yt-dlp", "--no-progress", "--skip-download", "--write-subs", "--write-auto-subs",
            "--sub-langs", "en,en-orig,en-US,en-GB", "--sub-format", "vtt",
            "-o", str(directory / "captions"), "--", url,
        ]
        if shutil.which("node"):
            command[1:1] = ["--js-runtimes", "node", "--remote-components", "ejs:github"]
        if client:
            command[1:1] = ["--extractor-args", f"youtube:player_client={client}"]
        result = subprocess.run(command, text=True, capture_output=True, timeout=300)
        files = sorted(directory.glob("captions*.vtt"), key=lambda path: ("orig" in path.name, path.name))
        for path in files:
            lines = _vtt_lines(path.read_text(encoding="utf-8", errors="replace"))
            if lines:
                return lines, f"YouTube captions via yt-dlp ({client or 'default'} client; may be machine generated)"
        detail = (result.stderr or result.stdout).strip().splitlines()
        failures.append(f"{client or 'default'}: {next((line for line in reversed(detail) if 'ERROR' in line), 'no captions')[:160]}")
    raise RuntimeError("; ".join(failures))


def _invidious_audio(video_id: str, directory: Path) -> tuple[Path, str]:
    """Fetch audio through a public Invidious instance's local proxy."""
    failures: list[str] = []
    for instance in INVIDIOUS_INSTANCES:
        try:
            request = Request(f"{instance}/api/v1/videos/{video_id}?local=true", headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=60) as response:
                data = json.loads(response.read())
            formats = [item for item in data.get("adaptiveFormats", []) if str(item.get("type", "")).startswith("audio/")]
            chosen = next((item for item in formats if str(item.get("itag")) == "140"), formats[0] if formats else None)
            if not chosen:
                raise RuntimeError("no audio formats listed")
            stream = chosen["url"] if chosen["url"].startswith("http") else f"{instance}{chosen['url']}"
            path = directory / "audio.m4a"
            with urlopen(Request(stream, headers={"User-Agent": "Mozilla/5.0"}), timeout=600) as response, path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            if path.stat().st_size < 10_000:
                raise RuntimeError("audio stream was empty")
            return path, instance
        except Exception as error:
            failures.append(f"{instance}: {type(error).__name__}: {str(error)[:120]}")
    raise RuntimeError("; ".join(failures) or "no Invidious instance configured")


def _download_audio(url: str, directory: Path) -> Path:
    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp is unavailable for public audio download")
    command = [
        "yt-dlp", "--no-playlist", "--no-cookies", "--no-progress", "-f", "bestaudio/best",
        "--max-filesize", "500M", "-o", str(directory / "audio.%(ext)s"), url,
    ]
    if shutil.which("node"):
        command[1:1] = ["--js-runtimes", "node"]
    result = subprocess.run(command, text=True, capture_output=True, timeout=1800)
    files = sorted(directory.glob("audio.*"))
    if result.returncode != 0 or not files:
        detail = (result.stderr or result.stdout).strip().splitlines()
        reason = next((line for line in reversed(detail) if "ERROR" in line), detail[-1] if detail else "unknown error")
        reason = reason.split(" Use --cookies", 1)[0]
        raise RuntimeError(f"public audio download failed: {reason[:300]}")
    return files[0]


def _decode(audio: Path) -> Any:
    """Decode to 16 kHz mono float samples with ffmpeg, independent of PyAV versions."""
    import numpy

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is unavailable for audio decoding")
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(audio), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True, timeout=1800,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(f"ffmpeg decode failed: {result.stderr.decode('utf-8', errors='replace')[:300]}")
    return numpy.frombuffer(result.stdout, numpy.int16).astype(numpy.float32) / 32768.0


def _whisper(audio: Path) -> list[tuple[float, str]]:
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(_decode(audio), vad_filter=True, beam_size=5)
    return [(float(segment.start), segment.text.strip()) for segment in segments if segment.text.strip()]


def transcribe(url: str, directory: Path) -> dict[str, Any]:
    """Write ``transcript.txt`` in ``directory``; return a transcript receipt."""
    directory.mkdir(parents=True, exist_ok=True)
    attempts: list[str] = []
    lines: list[tuple[float, str]] = []
    method = ""
    audio_sha256 = ""
    video_id = youtube_id(url)
    if video_id:
        try:
            lines = _captions(video_id)
            method = "published YouTube captions (may be machine generated)"
        except Exception as error:
            attempts.append(f"captions: {type(error).__name__}: {str(error).splitlines()[0][:200]}")
        if not lines:
            try:
                lines, method = _ytdlp_captions(url, directory)
            except Exception as error:
                attempts.append(f"yt-dlp captions: {str(error)[:400]}")
        if not lines:
            try:
                audio, instance = _invidious_audio(video_id, directory)
                audio_sha256 = hashlib.sha256(audio.read_bytes()).hexdigest()
                try:
                    lines = _whisper(audio)
                finally:
                    audio.unlink(missing_ok=True)
                method = f"audio via Invidious ({instance}) + local Whisper ({WHISPER_MODEL}) machine transcript"
            except Exception as error:
                attempts.append(f"invidious audio: {str(error)[:300]}")
    if not lines:
        try:
            audio = _download_audio(url, directory)
            audio_sha256 = hashlib.sha256(audio.read_bytes()).hexdigest()
            try:
                lines = _whisper(audio)
            finally:
                audio.unlink(missing_ok=True)
            method = f"public audio download + local Whisper ({WHISPER_MODEL}) machine transcript"
        except Exception as error:
            attempts.append(f"audio: {type(error).__name__}: {str(error)[:300]}")
    if not lines:
        return {"status": "unavailable", "reason": "; ".join(attempts) or "no transcript produced", "attempts": attempts}
    body = [
        f"# Transcript: {url}",
        f"# Method: {method}",
        "# Speaker identity is not established by this transcript.",
        "",
        *(f"[{_stamp(start)}] {text}" for start, text in lines),
    ]
    path = directory / "transcript.txt"
    atomic_write_text(path, "\n".join(body) + "\n")
    return {
        "status": "transcribed",
        "method": method,
        "path": path,
        "segments": len(lines),
        "audio_sha256": audio_sha256,
        "attempts": attempts,
    }
