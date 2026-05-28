import math, os
from PIL import Image, ImageDraw
OUT = r"C:/Users/ASUS/AppData/Roaming/Autodesk/Autodesk Fusion 360/API/AddIns/Smart_AI_CAM/resources"
STROKE = (51, 51, 51, 255)
ACCENT = (0, 163, 163, 255)
DSTROKE = (160, 160, 160, 255)
DACCENT = (140, 180, 180, 255)

def draw(size, dis=False):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    stroke = DSTROKE if dis else STROKE
    accent = DACCENT if dis else ACCENT
    cx = cy = size / 2.0
    sc = size / 64.0
    hr = 13.0 * sc
    sw = max(2, int(round(2.8 * sc)))
    pad = 3.0 * sc
    d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], outline=stroke, width=sw)
    pr = max(1, int(round(2.5 * sc)))
    d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=accent)
    ar = hr + 7.0 * sc
    ab = [cx - ar, cy - ar, cx + ar, cy + ar]
    d.arc(ab, start=35, end=145, fill=stroke, width=sw)
    rad = math.radians(38)
    nx = cx + ar * math.cos(rad)
    ny = cy - ar * math.sin(rad)
    nr = max(2, int(round(2.4 * sc)))
    d.ellipse([nx - nr, ny - nr, nx + nr, ny + nr], fill=accent)
    return img

os.makedirs(OUT, exist_ok=True)
for s in (16, 32, 64):
    draw(s, False).save(os.path.join(OUT, "%dx%d.png" % (s, s)))
    draw(s, True).save(os.path.join(OUT, "%dx%d-disabled.png" % (s, s)))
print("OK")