"""Build a harder test set: the same 60 documents as image-only "scans".

    python scripts/make_scanned_set.py            # writes data/docs_scanned/doc_*.pdf

Each page is rasterized to grayscale and degraded the way office scans are: a slight skew, blur,
sensor noise, lower contrast, heavy JPEG compression, and a rubber stamp that can land on top of
printed values. The result has no text layer, so the answer keys in data/truth/ still apply
unchanged and the amount-grounding rule cannot run (it needs text - see README).

No API calls. Seeded per document, so the set is reproducible. To evaluate it (needs API credit):

    python scripts/run_eval.py --docs-dir data/docs_scanned --out results_scanned --n 60 \
        --configs claude-haiku-5-5:low claude-opus-5-5:low
"""

from __future__ import annotations

import random
import sys
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "data" / "docs"
OUT_DIR = ROOT / "data" / "docs_scanned"
DPI = 150
MAX_SKEW_DEGREES = 2.5
JPEG_QUALITY_RANGE = (30, 55)
NOISE_TILE = 257  # odd size so the repeat does not line up with text rows
STAMP_WORDS = ("RECEIVED", "VERIFIED", "COPY", "SCANNED")


def _rasterize(pdf_path: Path) -> list[Image.Image]:
    with pymupdf.open(pdf_path) as doc:
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
            pages.append(Image.frombytes("L", (pix.width, pix.height), pix.samples))
        return pages


def _stamp(img: Image.Image, rng: random.Random) -> Image.Image:
    """A faint oval rubber stamp somewhere on the page, possibly over printed values."""
    stamped = img.copy()
    draw = ImageDraw.Draw(stamped)
    w, h = stamped.size
    cx, cy = rng.randint(w // 4, 3 * w // 4), rng.randint(h // 6, h // 2)
    rx, ry = w // 7, h // 22
    shade = rng.randint(90, 140)
    for offset in (0, 4):
        draw.ellipse((cx - rx - offset, cy - ry - offset, cx + rx + offset, cy + ry + offset), outline=shade, width=3)
    draw.text((cx - rx // 2, cy - 6), rng.choice(STAMP_WORDS), fill=shade)
    return stamped


def _jpeg_round_trip(img: Image.Image, quality: int) -> Image.Image:
    """The blocky artefacts of a cheap office scanner."""
    buffer = BytesIO()
    img.save(buffer, "JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("L")


def _noise(size: tuple[int, int], rng: random.Random) -> Image.Image:
    """Seeded sensor noise: a random tile repeated across the page (Image.effect_noise is unseeded)."""
    tile = Image.frombytes("L", (NOISE_TILE, NOISE_TILE), rng.randbytes(NOISE_TILE * NOISE_TILE))
    noise = Image.new("L", size)
    for x in range(0, size[0], NOISE_TILE):
        for y in range(0, size[1], NOISE_TILE):
            noise.paste(tile, (x, y))
    return noise


def _degrade(img: Image.Image, rng: random.Random) -> Image.Image:
    img = _stamp(img, rng)
    img = img.rotate(rng.uniform(-MAX_SKEW_DEGREES, MAX_SKEW_DEGREES), resample=Image.BICUBIC, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.5, 1.1)))
    img = Image.blend(img, _noise(img.size, rng), alpha=rng.uniform(0.06, 0.12))
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.65, 0.85))
    return _jpeg_round_trip(img, rng.randint(*JPEG_QUALITY_RANGE))


def main() -> int:
    sources = sorted(SRC_DIR.glob("doc_*.pdf"))
    if not sources:
        print(f"No source PDFs in {SRC_DIR}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for src in sources:
        rng = random.Random(src.stem)  # reproducible per document
        pages = [_degrade(page, rng) for page in _rasterize(src)]
        pages[0].save(OUT_DIR / src.name, "PDF", resolution=DPI, save_all=True, append_images=pages[1:])
    print(f"{len(sources)} scanned-style PDFs -> {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
