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
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from research_control.io import atomic_write_text
from research_control.resources import runtime_limits


WHISPER_MODEL = os.environ.get("RESEARCH_CONTROL_WHISPER_MODEL", "small.en")
MEDIA_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "wistia.com", "loom.com", "spotify.com",
               "podcasts.apple.com", "buzzsprout.com", "podbean.com", "transistor.fm", "megaphone.fm",
               "simplecast.com", "libsyn.com", "anchor.fm", "soundcloud.com")
AUDIO_SUFFIXES = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".mp4", ".webm")


MEDIA_PATH_SEGMENTS = {"video", "videos", "watch", "episode", "episodes", "podcast", "podcasts", "webinar", "webinars"}


def is_media_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    segments = {segment for segment in path.split("/") if segment}
    return (
        any(host == name or host.endswith(f".{name}") for name in MEDIA_HOSTS)
        or path.endswith(AUDIO_SUFFIXES)
        or bool(segments & MEDIA_PATH_SEGMENTS)
    )


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
_youtube_lock = threading.Lock()
# Whisper is CPU-bound; job count and threads per job come from the host.
_whisper_slots = threading.BoundedSemaphore(runtime_limits()["whisper_jobs"])


def _pace_youtube() -> None:
    """Space YouTube requests across all threads; bursts trigger 429s and bot checks."""
    global _last_youtube_request
    with _youtube_lock:
        now = time.monotonic()
        start = max(now, _last_youtube_request + YT_REQUEST_SPACING_SECONDS)
        _last_youtube_request = start
    if start > now:
        time.sleep(start - now)


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


_preferred_client: list[str | None] = []


def _client_order() -> tuple[str | None, ...]:
    """Try the player client that last worked first; YouTube's blocking varies by hour."""
    preferred = _preferred_client[-1:] if _preferred_client else []
    return tuple(dict.fromkeys([*preferred, *YT_CAPTION_CLIENTS]))


def _remember_client(client: str | None) -> None:
    _preferred_client.append(client)
    del _preferred_client[:-1]


def _ytdlp_captions(url: str, directory: Path) -> tuple[list[tuple[float, str]], str]:
    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp is unavailable for caption download")
    failures: list[str] = []
    for client in _client_order():
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
                _remember_client(client)
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


def _download_audio(url: str, directory: Path, clients: tuple[str | None, ...] = (None,)) -> tuple[Path, str]:
    """Download the best audio with yt-dlp, trying each player client in turn."""
    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp is unavailable for public audio download")
    failures: list[str] = []
    for client in clients:
        if youtube_id(url):
            _pace_youtube()
        command = [
            "yt-dlp", "--no-playlist", "--no-progress", "-f", "bestaudio/best",
            "--max-filesize", "500M", "-o", str(directory / "audio.%(ext)s"), "--", url,
        ]
        if shutil.which("node"):
            command[1:1] = ["--js-runtimes", "node", "--remote-components", "ejs:github"]
        if client:
            command[1:1] = ["--extractor-args", f"youtube:player_client={client}"]
        result = subprocess.run(command, text=True, capture_output=True, timeout=1800)
        files = [path for path in sorted(directory.glob("audio.*")) if not path.name.endswith((".part", ".ytdl"))]
        if result.returncode == 0 and files:
            return files[0], client or "default"
        for leftover in directory.glob("audio.*"):
            leftover.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout).strip().splitlines()
        reason = next((line for line in reversed(detail) if "ERROR" in line), detail[-1] if detail else "unknown error")
        failures.append(f"{client or 'default'}: {reason.split(' Use --cookies', 1)[0][:200]}")
    raise RuntimeError("public audio download failed: " + "; ".join(failures))


def _transcribe_audio(audio: Path) -> tuple[list[tuple[float, str]], str, str]:
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    try:
        lines, speaker_note = _whisper(audio)
        return lines, digest, speaker_note
    finally:
        audio.unlink(missing_ok=True)


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


DIARIZATION_RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
DIARIZATION_MODELS = {
    "segmentation.onnx": f"{DIARIZATION_RELEASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
    "embedding.onnx": f"{DIARIZATION_RELEASE}/speaker-recongition-models/nemo_en_titanet_large.onnx",
}
DIARIZATION_CACHE = Path(os.environ.get("RESEARCH_CONTROL_MODEL_CACHE", Path.home() / ".cache/research_control")) / "diarization"
# Distance threshold for joining voices. Lower splits one voice into several
# speakers; higher merges different voices. With TitaNet-Large embeddings, 0.7
# separated two hosts and a guest with similar voices on a podcast and placed
# every turn change correctly; very short utterances can still get a label of
# their own. (A smaller WeSpeaker model merged all three voices.)
DIARIZATION_THRESHOLD = float(os.environ.get("RESEARCH_CONTROL_DIARIZATION_THRESHOLD", "0.7"))
_diarization_lock = threading.Lock()


def _diarization_models() -> tuple[Path, Path]:
    """Fetch the public pyannote segmentation and TitaNet-Large embedding ONNX models once."""
    import tarfile

    segmentation = DIARIZATION_CACHE / "segmentation.onnx"
    embedding = DIARIZATION_CACHE / "embedding.onnx"
    with _diarization_lock:
        DIARIZATION_CACHE.mkdir(parents=True, exist_ok=True)
        if not segmentation.is_file():
            archive = DIARIZATION_CACHE / "segmentation.tar.bz2"
            with urlopen(DIARIZATION_MODELS["segmentation.onnx"], timeout=300) as response, archive.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            with tarfile.open(archive) as bundle:
                member = next(item for item in bundle.getmembers() if item.name.endswith("/model.int8.onnx"))
                extracted = bundle.extractfile(member)
                assert extracted is not None
                segmentation.write_bytes(extracted.read())
            archive.unlink(missing_ok=True)
        if not embedding.is_file():
            with urlopen(DIARIZATION_MODELS["embedding.onnx"], timeout=300) as response, embedding.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    return segmentation, embedding


SORTFORMER_MODEL = os.environ.get("RESEARCH_CONTROL_SORTFORMER_MODEL", "nvidia/diar_streaming_sortformer_4spk-v2")
_sortformer_pool: list[Any] = []
_sortformer_lock = threading.Lock()


def _sortformer_turns(samples: Any) -> list[tuple[float, float, int]]:
    """Diarize with NVIDIA Sortformer (end-to-end, up to four speakers).

    On a test podcast it kept the guest on one label across a two-second reply
    and a long answer, and resolved a fast host-guest exchange that clustering
    diarizers split or merged. Models are pooled, one per concurrent job.
    """
    import tempfile

    import soundfile
    from nemo.collections.asr.models import SortformerEncLabelModel

    with _sortformer_lock:
        model = _sortformer_pool.pop() if _sortformer_pool else None
    if model is None:
        model = SortformerEncLabelModel.from_pretrained(SORTFORMER_MODEL, map_location="cpu")
        model.eval()
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
            soundfile.write(handle.name, samples, 16000)
            output = model.diarize(audio=[handle.name], batch_size=1, verbose=False)
    finally:
        with _sortformer_lock:
            _sortformer_pool.append(model)
    rows = output[0] if output and isinstance(output[0], list) else output
    turns: list[tuple[float, float, int]] = []
    for row in rows:
        start, end, label = str(row).split()
        turns.append((float(start), float(end), int(label.rsplit("_", 1)[-1])))
    return sorted(turns)


def _diarize(samples: Any) -> tuple[list[tuple[float, float, int]], str]:
    """Return (start, end, speaker) turns and the method used.

    Sortformer when NeMo is installed; otherwise sherpa-onnx clustering.
    """
    try:
        return _sortformer_turns(samples), f"NVIDIA Sortformer ({SORTFORMER_MODEL}, up to 4 speakers)"
    except ImportError:
        return _sherpa_turns(samples), f"sherpa-onnx pyannote segmentation + TitaNet-Large, threshold {DIARIZATION_THRESHOLD}"


def _sherpa_turns(samples: Any) -> list[tuple[float, float, int]]:
    """Return (start, end, speaker) turns; speaker numbers group similar voices."""
    import sherpa_onnx

    segmentation, embedding = _diarization_models()
    threads = runtime_limits()["whisper_threads"]
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation)),
            num_threads=threads,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(embedding), num_threads=threads),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=DIARIZATION_THRESHOLD),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    result = sherpa_onnx.OfflineSpeakerDiarization(config).process(samples).sort_by_start_time()
    return [(float(turn.start), float(turn.end), int(turn.speaker)) for turn in result]


def _speaker_at(moment: float, turns: list[tuple[float, float, int]]) -> int | None:
    best: tuple[float, int] | None = None
    for turn_start, turn_end, speaker in turns:
        if turn_start <= moment <= turn_end:
            return speaker
        distance = min(abs(moment - turn_start), abs(moment - turn_end))
        if best is None or distance < best[0]:
            best = (distance, speaker)
    # A word in a short gap between turns belongs to the nearest turn.
    return best[1] if best and best[0] <= 1.0 else None


def _label_speakers(
    words: list[tuple[float, float, str]], turns: list[tuple[float, float, int]]
) -> list[tuple[float, str]]:
    """Label each word by the speaker turn at its midpoint and break lines at speaker changes.

    Speakers are renumbered in order of first appearance (Speaker 1, 2, ...).
    Lines also break at sentence ends after about 25 words so they stay citable.
    """
    order: dict[int, int] = {}
    lines: list[tuple[float, str]] = []
    current: int | None | str = "unset"
    line_start = 0.0
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            label = "?" if current is None else str(order.setdefault(current, len(order) + 1))
            lines.append((line_start, f"Speaker {label}: " + "".join(buffer).strip()))

    for start, end, word in words:
        speaker = _speaker_at((start + end) / 2, turns)
        sentence_end = bool(buffer) and buffer[-1].rstrip().endswith((".", "?", "!")) and len(buffer) >= 25
        if speaker != current or sentence_end:
            flush()
            buffer = []
            current = speaker
            line_start = start
        buffer.append(word)
    flush()
    return lines


def _whisper(audio: Path) -> tuple[list[tuple[float, str]], str]:
    """Transcribe with Whisper and label speakers when diarization is available.

    Returns the timestamped lines and a note on speaker labeling.
    """
    from faster_whisper import WhisperModel

    samples = _decode(audio)
    with _whisper_slots:
        model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=runtime_limits()["whisper_threads"])
        raw, _info = model.transcribe(samples, vad_filter=True, beam_size=5, word_timestamps=True)
        segments = [item for item in raw if item.text.strip()]
        try:
            turns, diarizer = _diarize(samples)
        except Exception as error:  # speaker labels are an enhancement; the transcript stands without them
            plain = [(float(item.start), item.text.strip()) for item in segments]
            return plain, f"no speaker labels ({type(error).__name__}: {str(error)[:120]})"
    words = [(float(word.start), float(word.end), word.word) for item in segments for word in (item.words or [])]
    speakers = len({speaker for _start, _end, speaker in turns})
    note = (
        f"speaker labels per word by automatic diarization ({diarizer}; {speakers} voices); "
        "labels mark turns and group voices, they do not identify anyone"
    )
    return _label_speakers(words, turns), note


def transcribe(url: str, directory: Path) -> dict[str, Any]:
    """Write ``transcript.txt`` in ``directory``; return a transcript receipt."""
    directory.mkdir(parents=True, exist_ok=True)
    attempts: list[str] = []
    lines: list[tuple[float, str]] = []
    method = ""
    audio_sha256 = ""
    speaker_note = "no speaker labels (published captions carry no speaker information)"
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
            # No captions: transcribe the audio, trying each player client, then Invidious.
            try:
                audio, client = _download_audio(url, directory, _client_order())
                _remember_client(None if client == "default" else client)
                lines, audio_sha256, speaker_note = _transcribe_audio(audio)
                method = f"YouTube audio via yt-dlp ({client} client) + local Whisper ({WHISPER_MODEL}) machine transcript"
            except Exception as error:
                attempts.append(f"yt-dlp audio: {str(error)[:400]}")
        if not lines:
            try:
                audio, instance = _invidious_audio(video_id, directory)
                lines, audio_sha256, speaker_note = _transcribe_audio(audio)
                method = f"audio via Invidious ({instance}) + local Whisper ({WHISPER_MODEL}) machine transcript"
            except Exception as error:
                attempts.append(f"invidious audio: {str(error)[:300]}")
    else:
        try:
            audio, _client = _download_audio(url, directory)
            lines, audio_sha256, speaker_note = _transcribe_audio(audio)
            method = f"public audio download + local Whisper ({WHISPER_MODEL}) machine transcript"
        except Exception as error:
            attempts.append(f"audio: {type(error).__name__}: {str(error)[:300]}")
    if not lines:
        return {"status": "unavailable", "reason": "; ".join(attempts) or "no transcript produced", "attempts": attempts}
    body = [
        f"# Transcript: {url}",
        f"# Method: {method}",
        f"# Speakers: {speaker_note}",
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
        "speakers": speaker_note,
        "audio_sha256": audio_sha256,
        "attempts": attempts,
    }
