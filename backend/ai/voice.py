from typing import Dict
import io
import math
from pydub import AudioSegment


def analyze_voice_bytes(raw: bytes, content_hint: str | None = None) -> Dict:
    file_like = io.BytesIO(raw)

    fmt = None
    if content_hint:
        h = content_hint.lower()
        if ".ogg" in h or "ogg" in h:
            fmt = "ogg"
        elif ".mp3" in h or "mpeg" in h:
            fmt = "mp3"
        elif ".wav" in h:
            fmt = "wav"
        elif ".m4a" in h or "mp4" in h or "aac" in h:
            fmt = "mp4"

    segment = AudioSegment.from_file(file_like, format=fmt)
    duration_sec = len(segment) / 1000.0 or 0.01

    mono = segment.set_channels(1)
    frame_ms = 100
    energies = []
    for i in range(0, len(mono), frame_ms):
        frame = mono[i:i+frame_ms]
        if len(frame) == 0:
            continue
        energies.append(frame.rms)

    if not energies:
        energies = [mono.rms]

    avg_energy = sum(energies) / len(energies)
    var_energy = sum((e - avg_energy)**2 for e in energies) / len(energies)
    std_energy = math.sqrt(var_energy)

    norm = avg_energy / 1000.0 + std_energy / 1500.0
    stress_score = max(0.0, min(100.0, norm * 50.0))

    if stress_score < 33:
        level = "низький"
    elif stress_score < 66:
        level = "середній"
    else:
        level = "високий"

    return {
        "duration_sec": duration_sec,
        "avg_energy": avg_energy,
        "std_energy": std_energy,
        "stress_score": round(stress_score, 2),
        "level": level,
    }
