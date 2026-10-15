"""Optional screenshot input (stretch goal): LOCAL OCR with Tesseract -> text -> the normal pipeline
(redaction happens at analysis time, exactly as for typed text).

The image is processed in memory on this server and never sent to any LLM or third party. There is deliberately
no vision-model path: a `USE_VISION` option would upload the raw image to the AI provider and is NOT implemented
(see DECISIONS.md / README)."""
from __future__ import annotations

import asyncio
import io
from functools import lru_cache

MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 3000


@lru_cache(maxsize=1)
def available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 - missing package or missing binary
        return False


def _ocr_sync(data: bytes) -> str:
    import pytesseract
    from PIL import Image, ImageOps

    if len(data) > MAX_BYTES:
        raise ValueError("image too large")
    img = Image.open(io.BytesIO(data))
    img.load()
    img = ImageOps.exif_transpose(img).convert("L")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    if max(img.size) < 1000:  # small screenshots OCR better when upscaled
        f = 1000 / max(img.size)
        img = img.resize((int(img.width * f), int(img.height * f)))
    img = ImageOps.autocontrast(img)
    return pytesseract.image_to_string(img, config="--psm 6")


def clean(text: str) -> str:
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    return "\n".join(ln for ln in lines if len(ln) > 1)


async def ocr_image(data: bytes) -> str:
    text = await asyncio.get_running_loop().run_in_executor(None, _ocr_sync, data)
    return clean(text)
