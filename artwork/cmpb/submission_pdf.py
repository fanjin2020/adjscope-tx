"""Vector export with measured blank bands and checks against the rendered PDF."""
import io
import hashlib
import itertools
import math
from pathlib import Path

import matplotlib
from matplotlib.transforms import Bbox
import numpy as np
from PIL import Image
import pypdfium2 as pdfium
import pypdfium2.raw as raw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, RectangleObject

SHEETS='Figures'
PT_MM=25.4/72
ANCHORS={1:('1.490','1.498','29 of 40'),2:('3,744','0.450','0.334','17,064','S3.5'),
         3:('29 / 40','0 / 40','5,688','17,064','S3.6'),4:('5.11','57.27%','4.54%','5.69%','13,312','S20.10'),
         5:('1.490','1.498','13,312','Design-specific','S16.4'),6:('95.00%','95.24%','4.8%','10.8%','10.6%','S23.2')}

def render(doc,i,dpi):
    page=doc[i]
    try:
        bitmap=page.render(scale=dpi/72)
        try:return bitmap.to_pil().convert('RGB')
        finally:bitmap.close()
    finally:page.close()

def edge_pixels(im):
    ink=np.any(np.asarray(im)!=255,axis=2)
    x=np.flatnonzero(ink.any(axis=0));y=np.flatnonzero(ink.any(axis=1))
    if not len(x) or not len(y):raise ValueError('Blank page.')
    return [int(y[0]),int(im.height-y[-1]-1),int(x[0]),int(im.width-x[-1]-1)]

def objects(doc):
    page=doc[0];textpage=page.get_textpage()
    try:
        result=[]
        for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_TEXT],textpage=textpage):
            s=obj.extract().strip()
            if s:
                font=obj.get_font()
                result.append((s,np.array(obj.get_bounds()),obj.get_font_size(),font.get_base_name(),font.is_embedded))
        return result
    finally:textpage.close();page.close()

def auto_padding(unpadded,minimum):
    with pdfium.PdfDocument(unpadded) as doc:
        px=edge_pixels(render(doc,0,360))[:2]
    return [max(0,math.ceil(minimum/PT_MM-v/5+.35)) for v in px]

def make_plot(plate,extra=None):
    buf=io.BytesIO(); kw={}
    if extra is not None:
        t,b=extra;w,h=plate.fig.get_size_inches()
        kw={'bbox_inches':Bbox.from_extents(0,-b/72,w,h+t/72),'pad_inches':0}
    meta={'Title':f'AdjScope-Tx: Figure {plate.n}','Author':'',
          'Creator':f'Python / Matplotlib {matplotlib.__version__} | AdjScope-Tx',
          'CreationDate':None,'ModDate':None}
    plate.fig.savefig(buf,format='pdf',facecolor='white',metadata=meta,**kw)
    return buf.getvalue()

def export_plot(plate,root,minimum):
    raw_pdf=make_plot(plate);extra=auto_padding(raw_pdf,minimum)
    final=make_plot(plate,extra)
    return save_checked(plate.n,raw_pdf,final,extra,root,minimum)

def export_framework(source,root,minimum):
    raw_pdf=Path(source).read_bytes()
    reader=PdfReader(io.BytesIO(raw_pdf))
    if len(reader.pages)!=1:raise ValueError('Figure 1 must be the original one-page diagram.')
    old=reader.pages[0];w,h=float(old.mediabox.width),float(old.mediabox.height)
    if old.rotation or list(old.cropbox)!=[0,0,w,h]:raise ValueError('Unexpected Figure 1 source page geometry.')
    extra=auto_padding(raw_pdf,minimum);top,bottom=extra
    writer=PdfWriter();p=writer.add_page(old)
    # Keep every original drawing instruction verbatim, including font and path operators.
    prefix=f'q\n1 0 0 1 0 {bottom} cm\n'.encode('ascii');suffix=b'\nQ\n'
    original_stream=old.get_contents().get_data()
    stream=DecodedStreamObject();stream.set_data(prefix+original_stream+suffix);p.replace_contents(stream)
    for attribute in ['mediabox','cropbox','trimbox','bleedbox','artbox']:
        setattr(p,attribute,RectangleObject([0,0,w,h+top+bottom]))
    writer.add_metadata({'/Title':'AdjScope-Tx: Figure 1','/Subject':'Unscaled original vector artwork; blank page margins only.'})
    buf=io.BytesIO();writer.write(buf)
    result=buf.getvalue()
    if PdfReader(io.BytesIO(result)).pages[0].get_contents().get_data()!=prefix+original_stream+suffix:
        raise ValueError('Figure 1 drawing instructions changed while adding margins.')
    row=save_checked(1,raw_pdf,result,extra,root,minimum)
    row['original_drawing_instructions_verbatim']=True
    return row

def save_checked(n,before,after,extra,root,minimum):
    top,bottom=extra; path=root/SHEETS/f'Figure_{n}.pdf'
    pg=PdfReader(io.BytesIO(after)).pages[0]
    text=' '.join(pg.extract_text().split())
    if not all(s in text for s in ANCHORS[n]):raise ValueError((n,'expected data labels missing'))
    w,h=float(pg.mediabox.width),float(pg.mediabox.height)
    for box in [pg.cropbox,pg.trimbox,pg.bleedbox,pg.artbox]:
        if not np.allclose(box,[0,0,w,h]):raise ValueError(f'Figure {n}: page boxes disagree.')
    if len(pg.images):raise ValueError(f'Figure {n}: unexpected raster image in vector figure.')
    with pdfium.PdfDocument(before) as original,pdfium.PdfDocument(after) as final:
        src,items=objects(original),objects(final)
        if len(src)!=len(items) or not items:raise ValueError('Text object lost during export.')
        for (s,orig,fs,ff,_),(t,box,fs2,ff2,emb) in zip(src,items):
            if s!=t or ff!=ff2 or not emb or abs(fs-fs2)>.001:raise ValueError((n,'text or font changed',s,t))
            if not np.allclose(box,orig+[0,bottom,0,bottom],atol=.045,rtol=0):
                raise ValueError((n,'content scaled or moved',s,orig,box,extra))
            if not (0<=box[0]<=box[2]<=w and 0<=box[1]<=box[3]<=h):raise ValueError((n,'text off page',s))
        for (s,a,*_),(t,b,*_) in itertools.combinations(items,2):
            dx=min(a[2],b[2])-max(a[0],b[0]);dy=min(a[3],b[3])-max(a[1],b[1])
            area=min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
            if dx>.35 and dy>.35 and dx*dy>.06*area:raise ValueError((n,'overlapping PDF text',s,t,dx,dy))
        mm={}
        for dpi in (288,360):
            im=render(final,0,dpi);px=edge_pixels(im)
            top_mm,bottom_mm=[v*25.4/dpi for v in px[:2]]
            if min(top_mm,bottom_mm)<minimum:raise ValueError((n,'insufficient pure-white margin',dpi,px))
            old_im=render(original,0,dpi)
            y=round(top*dpi/72);x0=0
            if im.width!=old_im.width or im.height!=old_im.height+round((top+bottom)*dpi/72):
                raise ValueError((n,'padded page dimensions differ',dpi))
            crop=np.asarray(im.crop((x0,y,im.width,y+old_im.height)),dtype=np.int16)
            diff=np.abs(crop-np.asarray(old_im,dtype=np.int16))
            if n==1 and (diff.max()>1 or diff.mean()>.0001):
                raise ValueError(('Figure 1 artwork differs beyond raster rounding',dpi,int(diff.max()),float(diff.mean())))
            if diff.mean()>.15:raise ValueError((n,'unexpected artwork shift',dpi,float(diff.mean())))
            mm[str(dpi)]={'top_mm':round(top_mm,3),'bottom_mm':round(bottom_mm,3),
                          'max_8bit_channel_diff_after_alignment':int(diff.max())}
        render(final,0,216).save(root/'Preview'/f'Figure_{n}.png',dpi=(216,216),optimize=True)
    path.write_bytes(after)
    return {'figure':n,'pdf_sha256':hashlib.sha256(after).hexdigest(),
            'page_pt':[w,h],'margin_from_visible_ink':mm,'added_pt':{'top':top,'bottom':bottom},
            'text_runs_checked':len(items),'substantial_text_collisions':0,'all_visible_fonts_embedded':True,
            'image_xobjects':0,'source':'original vector, unchanged' if n==1 else 'Python / Matplotlib; numerical inputs'}

def combine_and_verify(root):
    writer=PdfWriter()
    for n in range(1,7):writer.append(root/SHEETS/f'Figure_{n}.pdf',import_outline=False)
    path=root/'All_Figures_Proof.pdf'
    writer.add_metadata({'/Title':'AdjScope-Tx | Figures 1-6 | page proof'})
    with path.open('wb') as f:writer.write(f)
    with pdfium.PdfDocument(path) as proof:
        if len(proof)!=6:raise ValueError('Six-page proof expected.')
        for i in range(6):
            im=render(proof,i,216)
            with Image.open(root/'Preview'/f'Figure_{i+1}.png') as png:
                if not np.array_equal(np.asarray(im),np.asarray(png)):raise ValueError(f'Proof differs from Figure {i+1}.')
