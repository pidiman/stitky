"""Original hand-drawn 5×7 test lettering, expanded with uppercase ASCII glyphs."""
from PIL import Image, ImageDraw

# Rows are five bits, most significant visible bit on the left. U/S/B/C/-/>
# are identical to the physically accepted ESP32 USB-C test (JOB003).
GLYPHS = {
 'A':[14,17,17,31,17,17,17], 'B':[30,17,17,30,17,17,30],
 'C':[14,17,16,16,16,17,14], 'D':[30,17,17,17,17,17,30],
 'E':[31,16,16,30,16,16,31], 'F':[31,16,16,30,16,16,16],
 'G':[14,17,16,23,17,17,15], 'H':[17,17,17,31,17,17,17],
 'I':[31,4,4,4,4,4,31], 'J':[7,2,2,2,18,18,12],
 'K':[17,18,20,24,20,18,17], 'L':[16,16,16,16,16,16,31],
 'M':[17,27,21,21,17,17,17], 'N':[17,25,21,19,17,17,17],
 'O':[14,17,17,17,17,17,14], 'P':[30,17,17,30,16,16,16],
 'Q':[14,17,17,17,21,18,13], 'R':[30,17,17,30,20,18,17],
 'S':[15,16,16,14,1,1,30], 'T':[31,4,4,4,4,4,4],
 'U':[17,17,17,17,17,17,14], 'V':[17,17,17,17,17,10,4],
 'W':[17,17,17,21,21,27,17], 'X':[17,17,10,4,10,17,17],
 'Y':[17,17,10,4,4,4,4], 'Z':[31,1,2,4,8,16,31],
 '0':[14,17,19,21,25,17,14], '1':[4,12,4,4,4,4,14],
 '2':[14,17,1,2,4,8,31], '3':[30,1,1,14,1,1,30],
 '4':[2,6,10,18,31,2,2], '5':[31,16,16,30,1,1,30],
 '6':[14,16,16,30,17,17,14], '7':[31,1,2,4,8,8,8],
 '8':[14,17,17,14,17,17,14], '9':[14,17,17,15,1,1,14],
 ' ':[0]*7, '-':[0,0,0,31,0,0,0], '>':[16,8,4,2,4,8,16],
 '<':[1,2,4,8,4,2,1], '_':[0,0,0,0,0,0,31],
 '.':[0,0,0,0,0,12,12], ',':[0,0,0,0,4,4,8],
 ':':[0,12,12,0,12,12,0], ';':[0,12,12,0,4,4,8],
 '/':[1,2,2,4,8,8,16], '\\':[16,8,8,4,2,2,1],
 '+':[0,4,4,31,4,4,0], '=':[0,31,0,31,0,0,0],
 '(':[2,4,8,8,8,4,2], ')':[8,4,2,2,2,4,8],
 '[':[14,8,8,8,8,8,14], ']':[14,2,2,2,2,2,14],
 '!':[4,4,4,4,4,0,4], '?':[14,17,1,2,4,0,4],
 '#':[10,10,31,10,31,10,10], '%':[17,2,4,8,16,17,0],
 '*':[0,21,14,31,14,21,0], '"':[10,10,10,0,0,0,0],
 "'":[4,4,8,0,0,0,0], '@':[14,17,23,21,23,16,14],
 '&':[12,18,20,8,21,18,13], '|':[4,4,4,4,4,4,4],
}


def render_pixel(text: str, font_size: int) -> Image.Image:
    # Lowercase ASCII uses the same uppercase shapes; other scripts are rejected,
    # never silently dropped or replaced in a physical label.
    text = ''.join(c.upper() if 'a' <= c <= 'z' else c for c in text)
    if any(c not in GLYPHS and c != '\n' for c in text):
        raise ValueError('Pixelové písmo podporuje A–Z, číslice a bežné symboly bez diakritiky. Pre ostatné znaky vyber iné písmo.')
    lines = text.split('\n')
    widths = [max(0, len(line) * 6 - 1) for line in lines]
    height = len(lines) * 8 - 1
    if font_size and font_size % 7:
        raise ValueError('Pixelové písmo používa veľkosti 7, 14, 21, 28, 35, 42, 49, 56 alebo 63.')
    scales = [font_size // 7] if font_size else range(9, 0, -1)
    scale = next((n for n in scales if max(widths) * n <= 296 and height * n <= 72), None)
    if scale is None:
        raise ValueError('Text sa nezmestí na 40 × 12 mm; skráť text alebo zmenši písmo.')
    image = Image.new('1', (320, 96), 1)
    draw = ImageDraw.Draw(image)
    top = (96 - height * scale) // 2
    for line_index, line in enumerate(lines):
        left = (320 - widths[line_index] * scale) // 2
        for index, char in enumerate(line):
            for row, bits in enumerate(GLYPHS[char]):
                for col in range(5):
                    if bits & (1 << (4 - col)):
                        x = left + (index * 6 + col) * scale
                        y = top + (line_index * 8 + row) * scale
                        draw.rectangle((x, y, x + scale - 1, y + scale - 1), fill=0)
    return image
