import math
import os
import random
import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ----------------------------------------------------
# 1. โหลดฟอนต์ภาษาไทยสไตล์น่ารัก (Mali-Bold) อัตโนมัติ
# ----------------------------------------------------
FONT_FILENAME = "Mali-Bold.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/mali/Mali-Bold.ttf"

if not os.path.exists(FONT_FILENAME):
    print("⏳ กำลังดาวน์โหลดฟอนต์ภาษาไทยสไตล์น่ารัก (Mali-Bold)...")
    urllib.request.urlretrieve(FONT_URL, FONT_FILENAME)
    print("✅ ดาวน์โหลดฟอนต์เรียบร้อย!")

# ----------------------------------------------------
# 2. ตั้งค่าภาพ Rich Menu ขนาดมาตรฐาน LINE (2500x1686 px)
# ----------------------------------------------------
WIDTH, HEIGHT = 2500, 1686
W_THIRD = WIDTH // 3
H_HALF = HEIGHT // 2

# พื้นที่กด (tap area) ของ Rich Menu ยังคงเป็นกริด 3x2 เดิมทุกประการ
# ส่วนการ์ดที่มองเห็นจะ "ลอย" อยู่ในกริดนั้นโดยเว้นระยะขอบเข้ามา ไม่กระทบพื้นที่กด
CARD_GAP = 46
CARD_RADIUS = 64
BADGE_RADIUS = 150

SHADOW_COLOR = (196, 130, 165, 95)
SHADOW_OFFSET = (0, 18)
SHADOW_BLUR = 24

cards = [
    # แถวบน (Row 1)
    {
        "box": [0, 0, W_THIRD, H_HALF],
        "accent": "#FF9DBB",
        "color": "#C75B7A",
        "title": "บันทึกรอบเดือน",
        "icon": "calendar",
    },
    {
        "box": [W_THIRD, 0, W_THIRD * 2, H_HALF],
        "accent": "#B79CF0",
        "color": "#7E60BF",
        "title": "ดูประวัติ",
        "icon": "history",
    },
    {
        "box": [W_THIRD * 2, 0, WIDTH, H_HALF],
        "accent": "#FF8FAE",
        "color": "#D6336C",
        "title": "แชร์ให้แฟน",
        "icon": "heart",
    },
    # แถวล่าง (Row 2)
    {
        "box": [0, H_HALF, W_THIRD, HEIGHT],
        "accent": "#A48CEE",
        "color": "#5E35B1",
        "title": "แจ้งเตือน",
        "icon": "bell",
    },
    {
        "box": [W_THIRD, H_HALF, W_THIRD * 2, HEIGHT],
        "accent": "#F2A8C9",
        "color": "#A8467A",
        "title": "ลบรายการล่าสุด",
        "icon": "trash",
    },
    {
        "box": [W_THIRD * 2, H_HALF, WIDTH, HEIGHT],
        "accent": "#CBA4E8",
        "color": "#6B3FA0",
        "title": "รีเซ็ตประวัติ",
        "icon": "reset",
    },
]

font_title = ImageFont.truetype(FONT_FILENAME, 76)


# ----------------------------------------------------
# 3. Helper: สี / เกรเดียนต์พาสเทล
# ----------------------------------------------------
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def tint_white(hex_color, amount):
    r, g, b = hex_to_rgb(hex_color)
    return (
        int(r + (255 - r) * amount),
        int(g + (255 - g) * amount),
        int(b + (255 - b) * amount),
    )


def rgba(rgb_tuple, alpha=255):
    return (rgb_tuple[0], rgb_tuple[1], rgb_tuple[2], alpha)


def vertical_gradient(width, height, top_hex, bottom_hex):
    top_rgb, bottom_rgb = hex_to_rgb(top_hex), hex_to_rgb(bottom_hex)
    layer = Image.new("RGB", (width, height))
    gdraw = ImageDraw.Draw(layer)
    for y in range(height):
        gdraw.line([(0, y), (width, y)], fill=lerp_color(top_rgb, bottom_rgb, y / height))
    return layer


# ----------------------------------------------------
# 4. ของตกแต่งจิ๋วๆ ลอยตามร่องระหว่างการ์ด (หัวใจ/พระจันทร์/ประกาย)
# ----------------------------------------------------
def draw_mini_heart(d, cx, cy, size, fill):
    points = []
    for i in range(21):
        t = i / 20.0
        x = (1 - t) ** 3 * cx + 3 * (1 - t) ** 2 * t * (cx - size) + 3 * (1 - t) * t ** 2 * (cx - size * 0.6) + t ** 3 * cx
        y = (1 - t) ** 3 * (cy + size * 0.65) + 3 * (1 - t) ** 2 * t * (cy + size * 0.1) + 3 * (1 - t) * t ** 2 * (cy - size * 0.7) + t ** 3 * (cy - size * 0.2)
        points.append((x, y))
    for i in range(21):
        t = i / 20.0
        x = (1 - t) ** 3 * cx + 3 * (1 - t) ** 2 * t * (cx + size * 0.6) + 3 * (1 - t) * t ** 2 * (cx + size) + t ** 3 * cx
        y = (1 - t) ** 3 * (cy - size * 0.2) + 3 * (1 - t) ** 2 * t * (cy - size * 0.7) + 3 * (1 - t) * t ** 2 * (cy + size * 0.1) + t ** 3 * (cy + size * 0.65)
        points.append((x, y))
    d.polygon(points, fill=fill)


def draw_mini_moon(d, cx, cy, size, fill):
    d.ellipse([cx - size, cy - size, cx + size, cy + size], fill=fill)
    bite = size * 0.6
    d.ellipse([cx - size + bite, cy - size, cx + size + bite, cy + size], fill=(0, 0, 0, 0))


def draw_mini_sparkle(d, cx, cy, size, fill):
    w = max(3, size // 4)
    d.line([cx - size, cy, cx + size, cy], fill=fill, width=w)
    d.line([cx, cy - size, cx, cy + size], fill=fill, width=w)


def rounded_line(d, xy, fill, width):
    (x0, y0), (x1, y1) = xy
    d.line([x0, y0, x1, y1], fill=fill, width=width)
    r = width / 2
    d.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=fill)
    d.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=fill)


def scatter_confetti(draw_layer):
    rnd = random.Random(7)  # seed ตายตัว รันซ้ำได้ผลลัพธ์เดิมทุกครั้ง
    palette = ["#FFFFFF", "#FFD3E2", "#E4D6FF", "#F5D9EE"]
    shape_fns = [draw_mini_heart, draw_mini_moon, draw_mini_sparkle]

    bands = [
        (0, 0, WIDTH, CARD_GAP),                                       # ขอบบน
        (0, HEIGHT - CARD_GAP, WIDTH, HEIGHT),                         # ขอบล่าง
        (0, 0, CARD_GAP, HEIGHT),                                      # ขอบซ้าย
        (WIDTH - CARD_GAP, 0, WIDTH, HEIGHT),                          # ขอบขวา
        (W_THIRD - CARD_GAP, 0, W_THIRD + CARD_GAP, HEIGHT),           # ร่องแนวตั้งที่ 1
        (W_THIRD * 2 - CARD_GAP, 0, W_THIRD * 2 + CARD_GAP, HEIGHT),   # ร่องแนวตั้งที่ 2
        (0, H_HALF - CARD_GAP, WIDTH, H_HALF + CARD_GAP),              # ร่องแนวนอน
    ]

    for bx0, by0, bx1, by1 in bands:
        count = max(4, int((bx1 - bx0) * (by1 - by0) / 8000))
        for _ in range(count):
            x = rnd.randint(int(bx0), max(int(bx0), int(bx1) - 1))
            y = rnd.randint(int(by0), max(int(by0), int(by1) - 1))
            size = rnd.randint(7, 14)
            alpha = rnd.randint(90, 170)
            color = hex_to_rgb(rnd.choice(palette)) + (alpha,)
            rnd.choice(shape_fns)(draw_layer, x, y, size, color)


# ----------------------------------------------------
# 5. ฟังก์ชันวาด Vector Icons (สไตล์เส้นหนา + ของตกแต่งจิ๋ว)
# ----------------------------------------------------
def draw_icon(draw, icon_type, cx, cy, color):
    w = 18  # ความหนาของเส้น Vector Icon
    soft_fill = rgba(tint_white(color, 0.72))

    if icon_type == "calendar":
        body = [cx - 65, cy - 50, cx + 65, cy + 65]
        draw.rounded_rectangle(body, radius=18, fill=soft_fill, outline=color, width=w)
        draw.rectangle([cx - 53, cy - 50, cx + 53, cy - 12], fill=color)
        rounded_line(draw, ((cx - 30, cy - 70), (cx - 30, cy - 38)), color, w)
        rounded_line(draw, ((cx + 30, cy - 70), (cx + 30, cy - 38)), color, w)
        day_cells = [(-30, 15), (0, 15), (30, 15), (-30, 38), (0, 38), (30, 38)]
        for i, (dx, dy) in enumerate(day_cells):
            if i == 4:
                draw_mini_heart(draw, cx + dx, cy + dy, 9, color)
            else:
                draw.rounded_rectangle([cx + dx - 7, cy + dy - 7, cx + dx + 7, cy + dy + 7], radius=3, fill=color)

    elif icon_type == "history":
        draw.ellipse([cx - 65, cy - 65, cx + 65, cy + 65], fill=soft_fill, outline=color, width=w)
        for angle in (0, 90, 180, 270):
            rad = math.radians(angle)
            tx, ty = cx + 50 * math.sin(rad), cy - 50 * math.cos(rad)
            draw.ellipse([tx - 5, ty - 5, tx + 5, ty + 5], fill=color)
        rounded_line(draw, ((cx, cy), (cx, cy - 34)), color, w)
        rounded_line(draw, ((cx, cy), (cx + 26, cy)), color, w)
        draw.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=color)

    elif icon_type == "heart":
        points = []
        for t in range(0, 101):
            t /= 100.0
            x = (1 - t) ** 3 * cx + 3 * (1 - t) ** 2 * t * (cx - 100) + 3 * (1 - t) * t ** 2 * (cx - 80) + t ** 3 * cx
            y = (1 - t) ** 3 * (cy + 65) + 3 * (1 - t) ** 2 * t * (cy + 20) + 3 * (1 - t) * t ** 2 * (cy - 75) + t ** 3 * (cy - 25)
            points.append((x, y))
        for t in range(0, 101):
            t /= 100.0
            x = (1 - t) ** 3 * cx + 3 * (1 - t) ** 2 * t * (cx + 80) + 3 * (1 - t) * t ** 2 * (cx + 100) + t ** 3 * cx
            y = (1 - t) ** 3 * (cy - 25) + 3 * (1 - t) ** 2 * t * (cy - 75) + 3 * (1 - t) * t ** 2 * (cy + 20) + t ** 3 * (cy + 65)
            points.append((x, y))
        draw.polygon(points, fill=color)

    elif icon_type == "bell":
        draw.ellipse([cx - 15, cy + 42, cx + 15, cy + 68], fill=color)
        draw.rounded_rectangle([cx - 50, cy + 18, cx + 50, cy + 40], radius=10, fill=color)
        draw.pieslice([cx - 40, cy - 45, cx + 40, cy + 35], start=180, end=360, fill=soft_fill)
        draw.arc([cx - 40, cy - 45, cx + 40, cy + 35], start=180, end=360, fill=color, width=w)
        draw.ellipse([cx - 10, cy - 58, cx + 10, cy - 38], fill=color)
        rounded_line(draw, ((cx - 66, cy - 30), (cx - 52, cy - 22)), color, 9)
        rounded_line(draw, ((cx + 52, cy - 22), (cx + 66, cy - 30)), color, 9)

    elif icon_type == "trash":
        rounded_line(draw, ((cx - 65, cy - 38), (cx + 65, cy - 38)), color, w)
        draw.rounded_rectangle([cx - 24, cy - 58, cx + 24, cy - 38], radius=6, outline=color, width=8)
        draw.rounded_rectangle([cx - 48, cy - 25, cx + 48, cy + 58], radius=14, fill=soft_fill, outline=color, width=w)
        rounded_line(draw, ((cx - 18, cy - 3), (cx - 18, cy + 38)), color, 8)
        rounded_line(draw, ((cx + 18, cy - 3), (cx + 18, cy + 38)), color, 8)

    elif icon_type == "reset":
        # ยางลบ: รูปทรงสี่เหลี่ยมมุมโค้งสองสี ง่ายและไม่มีมุม/ทิศทางให้เพี้ยนแบบลูกศรวงกลม
        body = [cx - 65, cy - 42, cx + 65, cy + 58]
        draw.rounded_rectangle(body, radius=22, fill=soft_fill, outline=color, width=w)
        band = [cx - 65, cy + 18, cx + 65, cy + 58]
        draw.rounded_rectangle(band, radius=22, fill=color, corners=(False, False, True, True))
        for dx, dy, s in [(85, 40, 7), (100, 18, 5), (86, 2, 4)]:
            draw.ellipse([cx + dx - s, cy + dy - s, cx + dx + s, cy + dy + s], fill=color)


# ----------------------------------------------------
# 6. เงาใต้การ์ด (soft drop shadow)
# ----------------------------------------------------
def add_card_shadow(base_rgba, box, radius):
    shadow_layer = Image.new("RGBA", base_rgba.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    sx0, sy0, sx1, sy1 = box
    shadow_draw.rounded_rectangle(
        [sx0 + SHADOW_OFFSET[0], sy0 + SHADOW_OFFSET[1], sx1 + SHADOW_OFFSET[0], sy1 + SHADOW_OFFSET[1]],
        radius=radius,
        fill=SHADOW_COLOR,
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    base_rgba.alpha_composite(shadow_layer)


# ----------------------------------------------------
# 7. วาดพื้นหลังเกรเดียนต์ + ของตกแต่ง
# ----------------------------------------------------
image = vertical_gradient(WIDTH, HEIGHT, "#FFE1EC", "#DCD2F7").convert("RGBA")

confetti_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
scatter_confetti(ImageDraw.Draw(confetti_layer))
image.alpha_composite(confetti_layer)

draw = ImageDraw.Draw(image)

# ----------------------------------------------------
# 8. วาดการ์ดลอย + badge ไอคอน + ข้อความ
# ----------------------------------------------------
for card in cards:
    box = card["box"]
    inset = [box[0] + CARD_GAP, box[1] + CARD_GAP, box[2] - CARD_GAP, box[3] - CARD_GAP]
    accent_rgb = hex_to_rgb(card["accent"])
    primary_hex = card["color"]

    add_card_shadow(image, inset, CARD_RADIUS)

    card_fill = tint_white(card["accent"], 0.78) + (255,)
    draw.rounded_rectangle(inset, radius=CARD_RADIUS, fill=card_fill, outline=accent_rgb + (255,), width=7)

    card_cx = (inset[0] + inset[2]) / 2
    card_h = inset[3] - inset[1]
    badge_cy = inset[1] + card_h * 0.36

    badge_box = [card_cx - BADGE_RADIUS, badge_cy - BADGE_RADIUS, card_cx + BADGE_RADIUS, badge_cy + BADGE_RADIUS]
    draw.ellipse(badge_box, fill=rgba(tint_white(card["accent"], 0.93)), outline=accent_rgb + (255,), width=9)

    # ประกายมันวาวมุมบนซ้ายของ badge วาดก่อนไอคอน ให้อยู่ "หลัง" ไอคอนเสมอ ไม่บังลายเส้น
    draw.ellipse(
        [card_cx - BADGE_RADIUS * 0.55, badge_cy - BADGE_RADIUS * 0.72,
         card_cx - BADGE_RADIUS * 0.05, badge_cy - BADGE_RADIUS * 0.32],
        fill=(255, 255, 255, 110),
    )

    draw_icon(draw, card["icon"], card_cx, badge_cy, primary_hex)

    title = card["title"]
    bbox = font_title.getbbox(title)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    text_x = card_cx - text_w / 2
    text_y = inset[1] + card_h * 0.74 - text_h / 2
    draw.text((text_x, text_y), title, fill=primary_hex, font=font_title)

image.convert("RGB").save("rich_menu.png")
print("🎉 บันทึกรูปภาพสำเร็จ! ธีมน่ารักพาสเทลพร้อมใช้งานแล้วค่ะ 🌸")
