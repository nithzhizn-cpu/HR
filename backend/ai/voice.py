import io
import math
from typing import Dict, Optional

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError


# ------------------------------
#   SAFE VOICE ANALYZER FOR RAILWAY
# ------------------------------

def analyze_voice_bytes(raw: bytes, content_hint: Optional[str] = None) -> Dict:
    """
    Safe wrapper — does not crash even if audio is corrupted.
    Railway-friendly version:
      - tries multiple formats
      - always returns valid stress_score
    """

    # Convert raw bytes to file-like object
    file_like = io.BytesIO(raw)

    # Detect audio format
    fmt = None
    if content_hint:
        h = content_hint.lower()
        if "ogg" in h:
            fmt = "ogg"
        elif "mp3" in h or "mpeg" in h:
            fmt = "mp3"
        elif "wav" in h:
            fmt = "wav"
        elif "m4a" in h or "mp4" in h or "aac" in h:
            fmt = "mp4"

    # Try decoding with selected format
    try:
        segment = AudioSegment.from_file(file_like, format=fmt)
    except CouldntDecodeError:
        # Try fallback formats
        for fallback in ["ogg", "mp3", "wav", "mp4", None]:
            try:
                file_like.seek(0)
                segment = AudioSegment.from_file(file_like, format=fallback)
                break
            except:
                segment = None
        if segment is None:
            # Hard fallback → generate silent 1s audio
            segment = AudioSegment.silent(duration=1000)

    # Ensure duration not zero
    duration_sec = max(len(segment) / 1000.0, 0.01)

    # Convert to mono
    mono = segment.set_channels(1)

    # FRAME SIZE — 100 ms
    frame_ms = 100
    energies = []

    for i in range(0, len(mono), frame_ms):
        frame = mono[i:i + frame_ms]
        if len(frame) == 0:
            continue
        energies.append(frame.rms)

    if not energies:
        energies = [mono.rms]

    avg_energy = sum(energies) / len(energies)
    var_energy = sum((e - avg_energy) ** 2 for e in energies) / len(energies)
    std_energy = math.sqrt(var_energy)

    # Stress model: simplified but stable
    norm = avg_energy / 1200.0 + std_energy / 1800.0
    stress_score = max(0.0, min(100.0, norm * 55.0))

    # Level classification
    if stress_score < 33:
        level = "низький"
    elif stress_score < 66:
        level = "середній"
    else:
        level = "високий"

    return {
        "duration_sec": round(duration_sec, 2),
        "avg_energy": round(avg_energy, 3),
        "std_energy": round(std_energy, 3),
        "stress_score": round(stress_score, 2),
        "level": level,
    }