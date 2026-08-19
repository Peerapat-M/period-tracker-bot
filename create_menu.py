import os
import urllib.request
from PIL import Image, ImageDraw, ImageFont

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
image = Image.new("RGB", (WIDTH, HEIGHT))
draw = ImageDraw.Draw(image)

W_THIRD = WIDTH // 3
H_HALF = HEIGHT // 2

cards = [
    # แถวบน (Row 1)
    {
        "box": [0, 0, W_THIRD, H_HALF],
        "bg": "#FFE4E8",        # ชมพูพาสเทล
        "title": "บันทึกรอบเดือน",
        "color": "#C75B7A",
        "icon": "calendar",
    },
    {
        "box": [W_THIRD, 0, W_THIRD * 2, H_HALF],
        "bg": "#F0E6FF",        # ม่วงพาสเทล
        "title": "ดูประวัติ",
        "color": "#7E60BF",
        "icon": "history",
    },
    {
        "box": [W_THIRD * 2, 0, WIDTH, H_HALF],
        "bg": "#FFE5D9",        # ส้มพีชพาสเทล
        "title": "แชร์ให้แฟน",
        "color": "#D35400",
        "icon": "heart",
    },
    # แถวล่าง (Row 2)
    {
        "box": [0, H_HALF, W_THIRD, HEIGHT],
        "bg": "#E8DFF5",        # ลาเวนเดอร์พาสเทล
        "title": "แจ้งเตือน",    # ✏️ เปลี่ยนเป็นคำนี้เพื่อไม่ให้สระซ้อนชั้นและตัวหนังสือไม่เพี้ยน
        "color": "#5E35B1",
        "icon": "bell",
    },
    {
        "box": [W_THIRD, H_HALF, W_THIRD * 2, HEIGHT],
        "bg": "#FFF0F5",        # ชมพูอ่อนพาสเทล
        "title": "ลบรายการล่าสุด",
        "color": "#D2649A",
        "icon": "trash",
    },
    {
        "box": [W_THIRD * 2, H_HALF, WIDTH, HEIGHT],
        "bg": "#E6F4EA",        # เขียวมิ้นต์พาสเทล
        "title": "รีเซ็ตประวัติ",
        "color": "#438855",
        "icon": "reset",
    },
]

font = ImageFont.truetype(FONT_FILENAME, 85)

# ----------------------------------------------------
# 3. ฟังก์ชันวาด Vector Icons
# ----------------------------------------------------
def draw_icon(draw, icon_type, cx, cy, color):
    w = 16  # ความหนาของเส้น Vector Icon

    if icon_type == "calendar":
        draw.rounded_rectangle([cx - 65, cy - 50, cx + 65, cy + 65], radius=18, outline=color, width=w)
        draw.line([cx - 65, cy - 10, cx + 65, cy - 10], fill=color, width=w)
        draw.line([cx - 30, cy - 70, cx - 30, cy - 40], fill=color, width=w)
        draw.line([cx + 30, cy - 70, cx + 30, cy - 40], fill=color, width=w)
        for dx in [-30, 0, 30]:
            for dy in [15, 38]:
                draw.ellipse([cx + dx - 5, cy + dy - 5, cx + dx + 5, cy + dy + 5], fill=color)

    elif icon_type == "history":
        draw.ellipse([cx - 65, cy - 65, cx + 65, cy + 65], outline=color, width=w)
        draw.line([cx, cy - 40, cx, cy], fill=color, width=w)
        draw.line([cx, cy, cx + 30, cy], fill=color, width=w)

    elif icon_type == "heart":
        points = []
        for t in range(0, 101):
            t /= 100.0
            x = (1-t)**3 * cx + 3*(1-t)**2 * t * (cx - 100) + 3*(1-t) * t**2 * (cx - 80) + t**3 * cx
            y = (1-t)**3 * (cy + 65) + 3*(1-t)**2 * t * (cy + 20) + 3*(1-t) * t**2 * (cy - 75) + t**3 * (cy - 25)
            points.append((x, y))
        for t in range(0, 101):
            t /= 100.0
            x = (1-t)**3 * cx + 3*(1-t)**2 * t * (cx + 80) + 3*(1-t) * t**2 * (cx + 100) + t**3 * cx
            y = (1-t)**3 * (cy - 25) + 3*(1-t)**2 * t * (cy - 75) + 3*(1-t) * t**2 * (cy + 20) + t**3 * (cy + 65)
            points.append((x, y))

        draw.polygon(points, fill=color)

    elif icon_type == "bell":
        draw.ellipse([cx - 15, cy + 42, cx + 15, cy + 68], fill=color)
        draw.rounded_rectangle([cx - 50, cy + 18, cx + 50, cy + 40], radius=10, fill=color)
        draw.arc([cx - 40, cy - 45, cx + 40, cy + 35], start=180, end=360, fill=color, width=w*2)
        draw.ellipse([cx - 10, cy - 58, cx + 10, cy - 38], fill=color)

    elif icon_type == "trash":
        draw.line([cx - 65, cy - 38, cx + 65, cy - 38], fill=color, width=w)
        draw.rounded_rectangle([cx - 24, cy - 58, cx + 24, cy - 38], radius=6, outline=color, width=8)
        draw.rounded_rectangle([cx - 48, cy - 25, cx + 48, cy + 58], radius=14, outline=color, width=w)
        draw.line([cx - 18, cy - 5, cx - 18, cy + 38], fill=color, width=8)
        draw.line([cx + 18, cy - 5, cx + 18, cy + 38], fill=color, width=8)

    elif icon_type == "reset":
        draw.arc([cx - 60, cy - 60, cx + 60, cy + 60], start=40, end=320, fill=color, width=w)
        points = [(cx + 30, cy - 60), (cx + 68, cy - 40), (cx + 68, cy - 80)]
        draw.polygon(points, fill=color)

# ----------------------------------------------------
# 4. วาดบล็อก เส้นแบ่ง และข้อความ
# ----------------------------------------------------
for card in cards:
    box = card["box"]
    color = card["color"]

    draw.rectangle(box, fill=card["bg"])

    card_cx = box[0] + (box[2] - box[0]) / 2
    card_cy = box[1] + (box[3] - box[1]) / 2

    draw_icon(draw, card["icon"], card_cx, card_cy - 60, color)

    title = card["title"]
    bbox = font.getbbox(title)
    text_w = bbox[2] - bbox[0]
    
    text_x = card_cx - (text_w / 2)
    text_y = card_cy + 55

    draw.text((text_x, text_y), title, fill=color, font=font)

# เส้นแบ่งช่องสีขาว
draw.line([W_THIRD, 0, W_THIRD, HEIGHT], fill="#FFFFFF", width=8)
draw.line([W_THIRD * 2, 0, W_THIRD * 2, HEIGHT], fill="#FFFFFF", width=8)
draw.line([0, H_HALF, WIDTH, H_HALF], fill="#FFFFFF", width=8)

image.save("rich_menu.png")
print("🎉 บันทึกรูปภาพสำเร็จ ตัวหนังสือไม่เพี้ยนแล้วครับ!")