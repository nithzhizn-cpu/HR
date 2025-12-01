from typing import Dict, Optional
import math


def analyze_voice_bytes(raw: bytes, content_hint: Optional[str] = None) -> Dict:
    """
    Дуже спрощений аналіз голосу без зовнішніх бібліотек.
    Працює на будь-якому Python (в т.ч. 3.13) і не використовує pydub/ffmpeg.

    Ми не аналізуємо реальний спектр, а оцінюємо:
      - тривалість (приблизно)
      - "інтенсивність" за розміром файлу
    """

    if not raw:
        return {
            "duration_sec": 0.0,
            "avg_energy": 0.0,
            "std_energy": 0.0,
            "stress_score": 0.0,
            "level": "низький",
        }

    # груба оцінка тривалості за розміром (в байтах)
    # 16 кб/сек → 16000 байт ~ 1 сек
    approx_duration = max(len(raw) / 16000.0, 0.3)
    if approx_duration > 120:
        approx_duration = 120.0

    # "енергія" = логарифм розміру
    size_kb = len(raw) / 1024.0
    avg_energy = math.log10(1.0 + size_kb) * 100.0

    # варіація умовна — фіксована частка
    std_energy = avg_energy * 0.35

    # нормуємо в 0–100
    norm = avg_energy / 200.0 + std_energy / 300.0
    stress_score = max(0.0, min(100.0, norm * 50.0))

    if stress_score < 33:
        level = "низький"
    elif stress_score < 66:
        level = "середній"
    else:
        level = "високий"

    return {
        "duration_sec": round(approx_duration, 2),
        "avg_energy": round(avg_energy, 2),
        "std_energy": round(std_energy, 2),
        "stress_score": round(stress_score, 2),
        "level": level,
    }