from typing import Dict
import io
import math
from PIL import Image, ImageStat


def analyze_photo_bytes(raw: bytes) -> Dict:
    img = Image.open(io.BytesIO(raw)).convert("L")
    stat = ImageStat.Stat(img)
    mean = stat.mean[0]
    variance = stat.var[0]
    std = math.sqrt(variance)

    brightness = mean
    contrast = std

    if brightness > 180 and contrast > 40:
        mood = "енергійний / активний"
    elif brightness < 80 and contrast < 30:
        mood = "втомлений / пригнічений"
    else:
        mood = "нейтральний / спокійний"

    if brightness < 90 or contrast < 20:
        fatigue = "високий"
    elif brightness < 130:
        fatigue = "середній"
    else:
        fatigue = "низький"

    return {
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "mood": mood,
        "fatigue_level": fatigue,
    }