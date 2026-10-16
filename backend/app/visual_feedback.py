"""Conservative pixel checks for a tightly cropped, single-row CartoDle image.

Text still comes from Ollama. Other themes/layouts fall back to its result.
"""
from collections import deque
import io
from PIL import Image
from .models import FIELDS


def background(rgb):
    r,g,b=rgb
    if r>160 and g>110 and b<100 and r>=g:return 'yellow'
    if g>65 and g>r*1.3 and g>b*1.15:return 'green'
    if 22<=r<=80 and 14<=g<=70 and 30<=b<=100 and b>=r>=g and b-g>=10:return 'gray'
    return None


def cells(image):
    w,h=image.size
    # Only a cropped row with seven wide, evenly spaced colored tiles is supported.
    if not (650<=w<=2400 and 70<=h<=480 and 5<w/h<12):return None
    pixels=image.load()
    for fraction in (.38,.32,.45,.25):
        y=int(h*fraction);runs=[];start=0;previous=None
        for x in range(w+1):
            color=background(pixels[x,y]) if x<w else None
            if color!=previous:
                if previous and x-start>w*.06:runs.append((start,x,previous))
                start=x;previous=color
        if len(runs)!=7:continue
        widths=[b-a for a,b,_ in runs]
        gaps=[runs[i+1][0]-runs[i][1] for i in range(6)]
        if min(widths)<max(widths)*.8 or any(g<1 or g>max(widths)*.3 for g in gaps):continue
        # Require the same backgrounds above and below this scan, avoiding text.
        if any(sum(background(pixels[int((a+b)/2),int(h*f)])==color for f in (.15,.3,.45,.6))<2 for a,b,color in runs):continue
        return runs
    return None


def arrow(image,left,right,color):
    """A large connected shaft/chevron has more ink at its arrowhead end."""
    w,h=image.size
    x0=int(left+(right-left)*.61);x1=right-2
    y0=int(h*.53);y1=int(h*.93)
    if x1<=x0 or y1<=y0:return None
    pixels=image.load()
    # Interior blank patch gives the local background, including JPEG variations.
    samples=[pixels[int((left+right)/2),int(h*f)] for f in (.25,.35,.45)]
    samples=[p for p in samples if background(p)==color]
    if not samples:return None
    bg=tuple(sorted(p[c] for p in samples)[len(samples)//2] for c in range(3))
    points=set()
    for y in range(y0,y1):
        for x in range(x0,x1):
            p=pixels[x,y]
            delta=sum(p[c]-bg[c] for c in range(3))/3
            if (25<delta<140 if color=='gray' else -160<delta<-25):points.add((x,y))
    components=[]
    while points:
        seed=points.pop();queue=deque([seed]);component=[seed]
        while queue:
            x,y=queue.popleft()
            for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if point in points:points.remove(point);queue.append(point);component.append(point)
        components.append(component)
    for component in sorted(components,key=len,reverse=True):
        xs=[p[0] for p in component];ys=[p[1] for p in component]
        height=max(ys)-min(ys)+1;width=max(xs)-min(xs)+1
        if height<h*.18 or width<(right-left)*.16 or len(component)<h*(right-left)*.009:continue
        top=sum(y<min(ys)+height/3 for _,y in component)
        bottom=sum(y>=max(ys)-height/3 for _,y in component)
        if top>bottom*1.45:return 'up'
        if bottom>top*1.45:return 'down'
    return None


def reconcile(content,payload):
    """Override only positively recognized backgrounds/arrows, never text values."""
    if not isinstance(payload,dict) or not isinstance(payload.get('rows'),list) or len(payload['rows'])!=1:return payload
    clues=payload['rows'][0].get('clues') if isinstance(payload['rows'][0],dict) else None
    if not isinstance(clues,dict) or any(not isinstance(clues.get(f),dict) for f in FIELDS):return payload
    with Image.open(io.BytesIO(content)) as original:image=original.convert('RGB')
    runs=cells(image)
    if not runs:return payload
    for field,(left,right,color) in zip(FIELDS,runs):
        clues[field]['color']=color
        if color=='green':clues[field]['arrow']=None
        elif field in ('pokedex','hp','rarity','set'):
            detected=arrow(image,left,right,color)
            if detected:clues[field]['arrow']=detected
    return payload
