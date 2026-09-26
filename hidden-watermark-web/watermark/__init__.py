"""Image-domain hidden watermark core, independent from the web layer."""

from .decoder import detect_watermark
from .encoder import embed_watermark
from .models import Capacity, DetectionResult, EmbedResult
from .transform import calculate_capacity

__all__ = [
    "Capacity",
    "DetectionResult",
    "EmbedResult",
    "calculate_capacity",
    "detect_watermark",
    "embed_watermark",
]
