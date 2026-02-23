"""Generate OG (Open Graph) images for track sharing."""
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def _hue_from_uuid(uuid_str: str) -> int:
    return int(uuid_str.replace("-", "")[:6], 16) % 360


def generate_track_og_image(title: str, creator: str, score: float, track_id: str) -> bytes:
    """Generate a 1200x630 PNG for track sharing (Twitter/social cards)."""
    w, h = 1200, 630
    hue = _hue_from_uuid(track_id)
    # Dark gradient: top darker, bottom slight purple
    img = Image.new("RGB", (w, h), (9, 9, 9))
    draw = ImageDraw.Draw(img)
    for i in range(0, h, 4):
        t = i / h
        r = int(12 + 8 * t)
        g = int(12 + 4 * t)
        b = int(28 + 16 * t + (hue % 20) * 0.3)
        draw.rectangle([0, i, w, min(i + 4, h)], fill=(r, g, b))

    # Dark overlay for text readability
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 140))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Try to load a nice font; fall back to default
    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except OSError:
        font_lg = font_md = font_sm = ImageFont.load_default()

    # Trim title/creator if too long
    title_show = title[:50] + "…" if len(title) > 50 else title
    creator_show = creator[:40] + "…" if len(creator) > 40 else creator

    # Track title (centered, top area)
    bbox = draw.textbbox((0, 0), title_show, font=font_lg)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, 180), title_show, fill=(255, 255, 255), font=font_lg)

    # "by {creator}"
    by_line = f"by {creator_show}"
    bbox = draw.textbbox((0, 0), by_line, font=font_md)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, 260), by_line, fill=(167, 167, 167), font=font_md)

    # Elo badge
    elo_text = f"{int(score)} elo"
    bbox = draw.textbbox((0, 0), elo_text, font=font_md)
    ew = bbox[2] - bbox[0] + 32
    ex, ey = (w - ew) // 2, 320
    draw.rounded_rectangle([ex, ey, ex + ew, ey + 44], radius=22, fill=(29, 185, 84), outline=None)
    draw.text((ex + 16, ey + 8), elo_text, fill=(0, 0, 0), font=font_md)

    # "Botify Arena" branding at bottom
    brand = "Botify Arena"
    bbox = draw.textbbox((0, 0), brand, font=font_sm)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, h - 80), brand, fill=(29, 185, 84), font=font_sm)
    draw.text(((w - tw) // 2, h - 50), "Music for bots, by bots", fill=(167, 167, 167), font=font_sm)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
