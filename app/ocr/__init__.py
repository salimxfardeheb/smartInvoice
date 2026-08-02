"""Moteur OCR : abstraction, implémentation PaddleOCR et chargement documents."""

from app.ocr.base import OcrEngine, OcrResult, get_ocr_engine
from app.ocr.document import DocumentLoader
from app.ocr.paddle import PaddleOcrEngine

__all__ = [
    "DocumentLoader",
    "OcrEngine",
    "OcrResult",
    "PaddleOcrEngine",
    "get_ocr_engine",
]
