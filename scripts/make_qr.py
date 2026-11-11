#!/usr/bin/env python3
"""Generate the QR cards used in the README and on the poster.

Requires Pillow and qrcode:

    python3 -m pip install "qrcode[pil]"
    python3 scripts/make_qr.py

Outputs (docs/assets/):
    qr-repo.png / qr-repo.svg       -> repository root (star / share)
    qr-plugin.png / qr-plugin.svg   -> plugin directory on main
    qr-branch.png / qr-branch.svg   -> repo-adaptation branch (pre-merge preview)
"""

from __future__ import annotations

from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.image.svg import SvgPathImage

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
REPO_URL = "https://github.com/Biomed-imaging-lab/SciDataMAS"
PLUGIN_URL = f"{REPO_URL}/tree/main/plugin"
BRANCH = "repo-adaptation"
BRANCH_URL = f"{REPO_URL}/tree/{BRANCH}"

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def make_qr_image(url: str, size: int = 960) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="white").convert("RGB")
    return img.resize((size, size), Image.NEAREST)


def make_card(url: str, title: str, out: Path) -> None:
    width, height = 1200, 1460
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)

    # Top accent bar and a thin frame keep the card readable on a poster.
    draw.rectangle([0, 0, width, 12], fill="#1d4ed8")
    draw.rectangle([40, 40, width - 40, height - 40], outline="#e2e8f0", width=3)

    qr = make_qr_image(url, 960)
    canvas.paste(qr, ((width - 960) // 2, 110))

    bold = ImageFont.truetype(FONT_BOLD, 56)
    regular = ImageFont.truetype(FONT_REG, 30)
    small = ImageFont.truetype(FONT_REG, 26)

    draw.text((width / 2, 1135), title, font=bold, fill="#0f172a", anchor="ma")
    draw.text(
        (width / 2, 1210),
        url.replace("https://", ""),
        font=regular,
        fill="#334155",
        anchor="ma",
    )
    draw.text((width / 2, 1268), "scan · star · share", font=small, fill="#64748b", anchor="ma")

    canvas.save(out, optimize=True)


def make_svg(url: str, out: Path) -> None:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgPathImage)
    img.save(out)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    make_card(REPO_URL, "SciDataMAS", ASSETS / "qr-repo.png")
    make_svg(REPO_URL, ASSETS / "qr-repo.svg")

    make_card(PLUGIN_URL, "DeepSeek Harness plugin", ASSETS / "qr-plugin.png")
    make_svg(PLUGIN_URL, ASSETS / "qr-plugin.svg")

    make_card(BRANCH_URL, "SciDataMAS (preview)", ASSETS / "qr-branch.png")
    make_svg(BRANCH_URL, ASSETS / "qr-branch.svg")

    for name in (
        "qr-repo.png",
        "qr-repo.svg",
        "qr-plugin.png",
        "qr-plugin.svg",
        "qr-branch.png",
        "qr-branch.svg",
    ):
        print(f"wrote docs/assets/{name}")


if __name__ == "__main__":
    main()
