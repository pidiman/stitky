"""Native 300 dpi Brother QL-810W monochrome profiles and raster stream.

Geometry/commands: Brother QL-800/810W/820NWB Raster Command Reference v1.01.
No network access and no printer-specific address is stored here.
"""
from dataclasses import dataclass
import io
import struct

from PIL import Image, ImageDraw
import qrcode

try:
    from .rendering import render_canvas
except ImportError:
    from rendering import render_canvas


@dataclass(frozen=True)
class Media:
    id: str
    name: str
    width_mm: int
    media_length_mm: int
    width_dots: int
    printable_dots: int
    right_pins: int
    page_dots: int = 0
    raster_lines: int = 0

    @property
    def continuous(self):
        return self.media_length_mm == 0

    def geometry(self, length_mm=50):
        if self.continuous:
            page = round(length_mm * 300 / 25.4)
            lines = page - 70
        else:
            page, lines = self.page_dots, self.raster_lines
        return page, lines


MEDIA = {
    m.id: m for m in [
        Media("brother_29", "Brother · DK 29 mm · súvislá páska", 29, 0, 342, 306, 6),
        Media("brother_62", "Brother · DK 62 mm · súvislá páska", 62, 0, 732, 696, 12),
        Media("brother_29x90", "Brother · DK 29 × 90 mm", 29, 90, 342, 306, 6, 1061, 991),
        Media("brother_62x100", "Brother · DK 62 × 100 mm", 62, 100, 732, 696, 12, 1179, 1109),
    ]
}


def profile_catalog():
    return [{"id": "p15_40x12", "name": "P15 · 40 × 12 mm", "printer_model": "p15",
             "width_mm": 12, "length_mm": 40, "dpi": 203, "continuous": False}] + [
        {"id": m.id, "name": m.name, "printer_model": "brother_ql810w", "width_mm": m.width_mm,
         "length_mm": m.media_length_mm, "dpi": 300, "continuous": m.continuous}
        for m in MEDIA.values()
    ]


def model_for_profile(profile_id):
    return "brother_ql810w" if profile_id in MEDIA else "p15"


def job_geometry(label):
    if label.profile_id == "p15_40x12":
        return "p15-raster", 96, 320
    media = MEDIA[label.profile_id]
    return "brother-raster-v1", 720, media.geometry(label.length_mm)[1]


def _content(label, width, height, font_path):
    if label.kind != "qr":
        return render_canvas(label, font_path, width=width, height=height, max_font_size=128)
    if label.border or label.invert:
        raise ValueError("QR nepodporuje rámik ani inverziu.")
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=1)
    qr.add_data(label.text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    box_width = min(height, int(width * .45)) if label.qr_caption else width
    scale = min(box_width, height) // len(matrix)
    if scale < 3:
        raise ValueError("QR je pre zvolený formát príliš hustý. Skráť obsah alebo zväčši štítok.")
    image = Image.new("1", (width, height), 1)
    draw = ImageDraw.Draw(image)
    left = (box_width - len(matrix) * scale) // 2
    top = (height - len(matrix) * scale) // 2
    for y, row in enumerate(matrix):
        for x, black in enumerate(row):
            if black:
                draw.rectangle((left+x*scale, top+y*scale, left+(x+1)*scale-1, top+(y+1)*scale-1), fill=0)
    if label.qr_caption:
        offset = box_width + 12
        caption = label.model_copy(update={"text": label.qr_caption, "kind": "text", "qr_caption": ""})
        image.paste(render_canvas(caption, font_path, width=width-offset, height=height,
                                  max_font_size=128), (offset, 0))
    return image


def encode_raster(content, media, auto_cut=True):
    """Map the landscape printable canvas to the Brother 720-pin scanline order."""
    # Page is landscape; feed runs along its x axis. Rotate CCW, pad on head,
    # mirror into pin order, then invert white=1 to ink=1.
    rotated = content.transpose(Image.Transpose.ROTATE_90)
    head = Image.new("1", (720, rotated.height), 1)
    head.paste(rotated, (720-media.printable_dots-media.right_pins, 0))
    raw = bytes(v ^ 255 for v in head.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())
    lines = rotated.height
    stream = bytearray(b"\x1bia\x01" + b"\0" * 400 + b"\x1b@\x1bia\x01")
    stream += b"\x1bi!\x00"
    stream += b"\x1biz" + bytes([0xce, 0x0a if media.continuous else 0x0b,
                                media.width_mm, media.media_length_mm])
    stream += struct.pack("<I", lines) + b"\0\0"
    stream += b"\x1biM" + bytes([0x40 if auto_cut else 0])
    stream += b"\x1biA\x01\x1biK" + bytes([8 if auto_cut else 0])
    stream += b"\x1bid" + struct.pack("<H", 35 if media.continuous else 0)
    stream += b"M\0"
    for start in range(0, len(raw), 90):
        stream += b"g\0\x5a" + raw[start:start+90]
    stream += b"\x1a"
    return bytes(stream)


def render_brother(label, font_path):
    media = MEDIA[label.profile_id]
    page_dots, lines = media.geometry(label.length_mm)
    content = _content(label, lines, media.printable_dots, font_path)
    preview = Image.new("1", (page_dots, media.width_dots), 1)
    preview.paste(content, (35, (media.width_dots-media.printable_dots)//2))
    output = io.BytesIO()
    preview.save(output, format="PNG")
    payload = encode_raster(content, media, label.auto_cut)
    if len(payload) > 250_000:
        raise ValueError("Tlačové dáta prekročili kapacitu mosta.")
    return output.getvalue(), payload
