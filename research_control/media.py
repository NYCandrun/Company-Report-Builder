"""Timestamped transcripts for public video and audio sources.

Order of preference: published captions, then a public audio download
transcribed locally with Whisper. Downloads never use cookies or accounts; a
source that yields neither is recorded with the reason. Machine transcripts do
not establish speaker identity.

The tools are optional host capabilities (``yt-dlp``, ``youtube-transcript-api``,
``faster-whisper``). When one is missing the transcript is recorded as
unavailable with that reason; the page capture itself still stands.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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
