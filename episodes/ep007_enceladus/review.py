"""Сборка монтажного листа черновика и компактной раскадровки, без финального рендера.

python review.py edit — после TTS/build_edit; python review.py board — после verify_video.
Для board нужен Pillow из bundled runtime. Сам Blender запускается отдельно с проверкой GPU.
"""
import json
from pathlib import Path
import sys
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'out'/'ep007_enceladus'/'9x16'
KEYS=[121,541,1021,1501,2161,2815,3181]


def prepare():
    sys.path.insert(0,str(ROOT))
    from tools.framecheck import scan
    cfg=json.loads((HERE/'episode.json').read_text(encoding='utf-8'))
    count=0; bad=[]
    for shot in cfg['edit']:
        for f in range(1,shot['frames']+1):
            _,why=scan(OUT/'draft_r2'/shot['shot']/f'{f:04d}.png',540,960)
            count+=1
            if why: bad.append((shot['shot'],f,why))
    if bad: raise SystemExit('INTEGRITY FAIL '+str(bad[:12]))
    print(f'INTEGRITY PASS {count} PNG, 540x960, signature/IHDR/IEND')
    dest=OUT/'previews_r2'; dest.mkdir(exist_ok=True)
    keys={'v1':[1,100,200,300],'v2':[1,160,320,480],'v3':[1,180,360,540],
          'v4':[1,140,280,420],'v5':[1,200,400,600],'v6':[1,200,400,600],'v7':[1,210,420,631]}
    for shot,frames in keys.items():
        for f in frames:
            target=dest/f'{shot}_f{f:04d}.png'
            if shot=='v7' and f==631:
                if not target.is_file(): raise SystemExit('Нет служебного кадра v7/631')
            else: shutil.copyfile(OUT/'draft_r2'/shot/f'{f:04d}.png',target)
    print('CONTACT INPUTS 28, from 15 FPS draft plus exact loop reference')


def edit():
    cfg=json.loads((HERE/'edit_9x16_en_preview.json').read_text(encoding='utf-8'))
    cfg['output']='out/ep007_enceladus/9x16/ep007_enceladus_en_draft_r2.mp4'
    cfg['format'].update(w=540,h=960)
    cfg['video'].update(bitrate_kbps=3400,preset='GOOD')
    for shot in cfg['shots']: shot['dir']=shot['dir'].replace('/frames/','/draft_r2/')
    for title in cfg['titles']: title['size']=round(title.get('size',56)*.5)
    cfg['captions']['size']=round(cfg['captions']['size']*.5)
    cfg['titles'].append(dict(text='PREVIEW R2 · MOTION 15 FPS',start=1,length=3570,
        size=11,x=.5,y=.14,font='C:/Windows/Fonts/segoeui.ttf',color=[.4,.48,.58],fade=0))
    dest=OUT/'edit_draft.json'; dest.write_text(json.dumps(cfg,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print(dest)


def board():
    from PIL import Image,ImageDraw,ImageFont
    cw,ch,band=270,480,64
    sheet=Image.new('RGB',(4*cw,68+2*(ch+band)+35),(9,14,21))
    draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',17)
    bold=ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf',26)
    draw.text((18,17),'EP007 — ENCELADUS · REVISION 2 · 59.5 s · EN',font=bold,fill=(217,235,245))
    names=['Вопрос и шлейфы','Маленькая луна Сатурна','Трещины и скрытый океан',
           'Льдинка, увеличенная','Химический состав','Предел знания о жизни','Материал океана / петля']
    times=['0–5 с','5–13 с','13–22 с','22–29 с','29–39 с','39–49 с','49–59.5 с']
    for i,f in enumerate(KEYS):
        x=(i%4)*cw; y=68+(i//4)*(ch+band)
        im=Image.open(OUT/'draft_qa_r2'/f'frame_{f:04d}.png').convert('RGB').resize((cw,ch),Image.Resampling.LANCZOS)
        sheet.paste(im,(x,y))
        draw.text((x+10,y+ch+6),f'v{i+1} · {times[i]}',font=font,fill=(143,195,225))
        draw.text((x+10,y+ch+32),names[i],font=font,fill=(220,228,237))
    x=3*cw+18; y=68+ch+band+110
    draw.multiline_text((x,y),'НА СОГЛАСОВАНИЕ\n\nКадры: Blender Cycles\nДвижение: 15 фаз/с\nДва перехода зумом\n\nОзвучка + своя музыка\nФинал не запущен.',font=font,fill=(193,212,227),spacing=10)
    draw.text((18,sheet.height-29),'Черновик 540×960. Детали поверхности и звёзды — в отдельных кадрах 1080×1920.',font=font,fill=(130,150,169))
    sheet.save(OUT/'storyboard_r2.jpg',quality=95)
    print(OUT/'storyboard_r2.jpg')


def zooms():
    from PIL import Image,ImageDraw,ImageFont
    frames=[1171,1225,1297,1333,1621,1669,1729,1753]
    cw,ch=270,480
    sheet=Image.new('RGB',(cw*4,2*(ch+48)+68),(9,14,21)); draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',18)
    title=ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf',25)
    draw.text((18,18),'EP007 R2 — v3 → v4 / v4 → v5 · ZOOM',font=title,fill=(215,232,244))
    for i,f in enumerate(frames):
        x=i%4*cw; y=68+i//4*(ch+48)
        im=Image.open(OUT/'draft_qa_r2'/f'frame_{f:04d}.png').convert('RGB').resize((cw,ch),Image.Resampling.LANCZOS)
        sheet.paste(im,(x,y)); draw.text((x+12,y+ch+10),f'{(f-1)/60:.1f} s',font=font,fill=(170,207,231))
    sheet.save(OUT/'zooms_r2.jpg',quality=95); print(OUT/'zooms_r2.jpg')


def qa():
    from PIL import Image,ImageDraw,ImageFont
    files=sorted((OUT/'draft_qa_r2').glob('frame_*.png'))
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',13)
    for page in range((len(files)+15)//16):
        group=files[page*16:(page+1)*16]; rows=(len(group)+3)//4
        sheet=Image.new('RGB',(1080,rows*502),(8,12,18)); draw=ImageDraw.Draw(sheet)
        for j,p in enumerate(group):
            x=j%4*270; y=j//4*502
            im=Image.open(p).convert('RGB').resize((270,480),Image.Resampling.LANCZOS)
            sheet.paste(im,(x,y)); draw.text((x+8,y+483),p.stem,font=font,fill=(185,205,220))
        p=OUT/f'qa_r2_{page+1}.jpg'; sheet.save(p,quality=95); print(p)


if __name__=='__main__':
    {'edit':edit,'board':board,'zooms':zooms,'prepare':prepare,'qa':qa}[sys.argv[1]]()
