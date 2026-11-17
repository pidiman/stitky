"""Monochrome layout shared by preview and printer raster."""
from PIL import Image, ImageDraw, ImageFont, ImageOps
try:
    from .pixel_font import GLYPHS, render_pixel
except ImportError:
    from pixel_font import GLYPHS, render_pixel

SYMBOLS = {
    '☺': [14,17,21,17,21,17,14], '☹': [14,17,21,17,14,17,14],
    '♥': [0,10,31,31,14,14,4], '★': [4,4,31,14,31,10,17],
    '✓': [0,1,1,18,20,8,0], '✕': [17,17,10,4,10,17,17],
    '⚠': [4,10,10,21,21,17,31], '⚡': [2,4,8,31,2,4,8],
    '→': [0,4,2,31,2,4,0], '←': [0,4,8,31,8,4,0],
    '↔': [0,10,17,31,17,10,0], '↑': [4,14,21,4,4,4,0],
    '↓': [0,4,4,4,21,14,4],
}
EMOJI_ALIASES = {'🙂':'☺', '😊':'☺', '😀':'☺', '🙁':'☹', '❤':'♥', '⭐':'★', '✅':'✓', '❌':'✕'}


def normalize_symbols(text):
    result=[]; previous_symbol=False
    for char in text:
        if char in ('\ufe0f','\ufe0e'):
            if not previous_symbol:
                raise ValueError('Emoji prezentácia je podporovaná iba pri symbole z ponuky.')
            previous_symbol=False
            continue
        if char=='\u200d':
            raise ValueError('Zložené emoji nie sú podporované. Použi symbol z ponuky.')
        char=EMOJI_ALIASES.get(char,char)
        result.append(char);previous_symbol=char in SYMBOLS
    return ''.join(result)


STYLE_DEFAULTS = {'align':'center', 'bold':False, 'italic':False, 'underline':False,
                  'line_spacing':4, 'letter_spacing':0, 'border':False, 'invert':False}


def style_dict(label):
    return {key: getattr(label, key) for key in STYLE_DEFAULTS}


def _glyph_mask(rows, size):
    mask = Image.new('1', (5, 7), 0)
    for y, bits in enumerate(rows):
        for x in range(5):
            if bits & (1 << (4-x)): mask.putpixel((x,y),1)
    height = max(7, size)
    return mask.resize((max(5,round(height*5/7)),height),Image.Resampling.NEAREST)


def _has_glyph(font, char):
    if char.isspace(): return True
    missing = font.getmask('\U0010ffff')
    actual = font.getmask(char)
    return actual.size != missing.size or bytes(actual) != bytes(missing)


def render_canvas(label, font_path, width=320, height=96, max_font_size=64):
    text = normalize_symbols(label.text)
    label = label.model_copy(update={"text":text})
    if any(ord(c)>0xffff for c in text):
        raise ValueError('Tento emotikon nie je podporovaný. Použi symbol z ponuky v editore.')
    style = style_dict(label)
    basic = all(style[k] == v for k,v in STYLE_DEFAULTS.items() if k not in ('border','invert'))
    if width == 320 and height == 96 and label.font == 'pixel' and basic and not any(c in SYMBOLS for c in text):
        image = render_pixel(text,label.font_size)
    elif label.font != 'pixel' and basic and not any(c in SYMBOLS for c in text):
        # Preserve prior layout and kerning when formatting has not been changed.
        image = _legacy_truetype(label,font_path,width,height,max_font_size)
    else:
        image = _styled(label,font_path,width,height,max_font_size)
    if label.border:
        ImageDraw.Draw(image).rounded_rectangle((3,3,width-4,height-4),radius=5,outline=0,width=1)
    if label.invert:
        image = ImageOps.invert(image.convert('L')).convert('1')
    return image


def _legacy_truetype(label,font_path,width=320,height=96,max_font_size=64):
    image=Image.new('1',(width,height),1);draw=ImageDraw.Draw(image)
    for size in ([label.font_size] if label.font_size else range(max_font_size,5,-1)):
        font=ImageFont.truetype(font_path(label.font,False,False),size)
        if not all(_has_glyph(font,c) for c in label.text if c!='\n'):
            return _styled(label,font_path,width,height,max_font_size)
        bbox=draw.multiline_textbbox((0,0),label.text,font=font,spacing=4,align='center')
        if bbox[2]-bbox[0]<=width-24 and bbox[3]-bbox[1]<=height-24:
            x=(width-(bbox[2]-bbox[0]))//2-bbox[0];y=(height-(bbox[3]-bbox[1]))//2-bbox[1]
            draw.multiline_text((x,y),label.text,font=font,fill=0,spacing=4,align='center')
            return image
    raise ValueError('Text sa nezmestí do dostupného priestoru; skráť text alebo zmenši písmo.')


def _pixel_line(line,scale,label):
    glyphs = {**GLYPHS,**SYMBOLS}
    line=''.join(c.upper() if 'a'<=c<='z' else c for c in line)
    if any(c not in glyphs for c in line):
        raise ValueError('Pixelové písmo podporuje A–Z, číslice a symboly z ponuky bez diakritiky.')
    width=max(0,len(line)*6-1)*scale+max(0,len(line)-1)*label.letter_spacing
    overhang=2*scale if label.italic else 0
    extra=1 if label.bold else 0
    height=7*scale+(max(1,scale//2)+1 if label.underline else 0)
    image=Image.new('1',(max(1,width+overhang+extra),max(1,height)),0);draw=ImageDraw.Draw(image)
    for index,c in enumerate(line):
        for row,bits in enumerate(glyphs[c]):
            shift=(6-row)*scale//3 if label.italic else 0
            for col in range(5):
                if bits&(1<<(4-col)):
                    x=index*(6*scale+label.letter_spacing)+col*scale+shift;y=row*scale
                    draw.rectangle((x,y,x+scale-1+extra,y+scale-1),fill=1)
    if label.underline and line:
        draw.rectangle((0,7*scale+1,image.width-1,image.height-1),fill=1)
    return image


def _true_line(line,size,label,font_path):
    font=ImageFont.truetype(font_path(label.font,label.bold,label.italic),size)
    fallback=ImageFont.truetype(font_path('sans',label.bold,label.italic),size)
    cap=font.getbbox('M');cap_height=max(7,cap[3]-cap[1])
    runs=[];x=0.0;bounds=[]
    # Rendering each run on one baseline keeps fallback glyphs aligned.
    for index,c in enumerate(line):
        if c in SYMBOLS:
            mask=_glyph_mask(SYMBOLS[c],cap_height)
            runs.append(('icon',x,mask,cap[1]));bounds.append((int(x),cap[1],int(x)+mask.width,cap[3]));advance=mask.width+1
        else:
            used=font if _has_glyph(font,c) else fallback
            if not _has_glyph(used,c):
                raise ValueError('Text obsahuje znak, ktorý vybrané písma nevedia vytlačiť. Použi symbol z ponuky.')
            box=used.getbbox(c);runs.append(('text',x,c,used));bounds.append((int(x)+box[0],box[1],int(x)+box[2],box[3]));advance=used.getlength(c)
        x+=advance+(label.letter_spacing if index<len(line)-1 else 0)
    if not line: return Image.new('1',(1,max(1,cap_height)),0)
    left=min(0,min(b[0] for b in bounds));right=max(round(x),max(b[2] for b in bounds))
    top=min(b[1] for b in bounds);bottom=max(b[3] for b in bounds)
    thickness=max(1,size//14)
    if label.underline:bottom+=thickness+2
    out=Image.new('1',(max(1,right-left),max(1,bottom-top)),0);draw=ImageDraw.Draw(out)
    for kind,origin,item,extra in runs:
        if kind=='text':draw.text((origin-left,-top),item,font=extra,fill=1)
        else:out.paste(1,(round(origin)-left,extra-top),item)
    if label.underline:draw.rectangle((0,out.height-thickness,out.width-1,out.height-1),fill=1)
    return out


def _styled(label,font_path,width=320,height=96,max_font_size=64):
    if label.font=='pixel':
        if label.font_size and label.font_size%7:raise ValueError('Pixelové písmo používa násobky 7 bodov.')
        sizes=[label.font_size//7] if label.font_size else range(9,0,-1)
    else:sizes=[label.font_size] if label.font_size else range(max_font_size,5,-1)
    for size in sizes:
        lines=[_pixel_line(line,size,label) if label.font=='pixel' else _true_line(line,size,label,font_path) for line in label.text.split('\n')]
        gap=max(0,size+label.line_spacing-4) if label.font=='pixel' else label.line_spacing
        text_height=sum(line.height for line in lines)+gap*(len(lines)-1)
        if max(line.width for line in lines)>width-24 or text_height>height-24:continue
        image=Image.new('1',(width,height),1);top=(height-text_height)//2
        for line in lines:
            left=12 if label.align=='left' else width-12-line.width if label.align=='right' else (width-line.width)//2
            # Text masks have black backgrounds and white ink.
            image.paste(0,(left,top),line);top+=line.height+gap
        return image
    raise ValueError('Text sa nezmestí do dostupného priestoru; skráť text alebo zmenši písmo.')
