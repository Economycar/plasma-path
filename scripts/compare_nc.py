"""Compare two .nc files: rasterize torch-on moves, report overlap and max deviation."""
import os, sys, math, numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skill", "plasma-path", "scripts"))
from pp import parse_nc
def segs(path):
    mv = parse_nc(path); prev=(0,0); out=[]
    for k,x,y in mv:
        if k=="cut": out.append((prev,(x,y)))
        prev=(x,y)
    return out
def raster(sg, ppi, W, H):
    im = Image.new("L",(W,H),0); d=ImageDraw.Draw(im)
    for a,b in sg: d.line([(a[0]*ppi,H-a[1]*ppi),(b[0]*ppi,H-b[1]*ppi)], fill=255, width=2)
    return np.array(im)>0
A, B = sys.argv[1], sys.argv[2]
sa, sb = segs(A), segs(B)
ppi=100
allp=[p for s in sa+sb for p in s]; W=int(max(p[0] for p in allp)*ppi)+20; H=int(max(p[1] for p in allp)*ppi)+20
ra, rb = raster(sa,ppi,W,H), raster(sb,ppi,W,H)
da, db = ndi.distance_transform_edt(~ra), ndi.distance_transform_edt(~rb)
print(f"A={A}\nB={B}")
print(f"cut length A {sum(math.dist(*s) for s in sa):.2f}  B {sum(math.dist(*s) for s in sb):.2f}")
print(f"pierces A {sum(1 for l in open(A) if l.startswith('M3'))}  B {sum(1 for l in open(B) if l.startswith('M3'))}")
print(f"max deviation of A from B: {da[rb].max()/ppi:.3f} in, 95th pct {np.percentile(da[rb],95)/ppi:.3f} in")
print(f"max deviation of B from A: {db[ra].max()/ppi:.3f} in, 95th pct {np.percentile(db[ra],95)/ppi:.3f} in")
print(f"fraction of B within 0.02 in of A: {(da[rb]<=2).mean():.4f}")
# overlay image
rgb=np.full((H,W,3),255,np.uint8); rgb[ra]=(220,40,40); rgb[rb]=(40,80,220); rgb[ra&rb]=(30,30,30)
Image.fromarray(rgb).save(sys.argv[3]); print("overlay", sys.argv[3])
