"""Polygon validation, raster masks and exact polyline clipping."""
import math
import cv2
import numpy as np

def validate(value):
    if value is None: return None
    if not isinstance(value,list) or not 3<=len(value)<=128: raise ValueError('El poligono necesita entre 3 y 128 vertices.')
    points=[]
    for p in value:
        if not isinstance(p,list) or len(p)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in p): raise ValueError('Vertices de poligono no validos.')
        points.append(list(p))
    if points[0]==points[-1]: points.pop()
    contour=np.array(points,np.float32)
    if len(points)<3 or abs(cv2.contourArea(contour))<1e-8: raise ValueError('El poligono no tiene superficie.')
    for i in range(len(points)):
        for j in range(i+1,len(points)):
            if j==i+1 or (i==0 and j==len(points)-1): continue
            if intersections(points[i],points[(i+1)%len(points)],points[j],points[(j+1)%len(points)]): raise ValueError('El poligono no puede cruzarse consigo mismo.')
    return points

def inside(point,polygon):
    return cv2.pointPolygonTest(np.array(polygon,np.float32),tuple(map(float,point)),False)>=0

def mask(polygon,shape):
    h,w=shape[:2];result=np.zeros((h,w),np.uint8)
    cv2.fillPoly(result,[np.rint(np.array(polygon)*[w-1,h-1]).astype(np.int32)],255)
    return result

def intersections(a,b,c,d):
    v=np.subtract(b,a);u=np.subtract(d,c);q=np.subtract(c,a)
    den=v[0]*u[1]-v[1]*u[0]
    if abs(den)<1e-12: return []
    t=(q[0]*u[1]-q[1]*u[0])/den;s=(q[0]*v[1]-q[1]*v[0])/den
    return [float(t)] if -1e-10<=t<=1+1e-10 and -1e-10<=s<=1+1e-10 else []

def clip(lines,polygon):
    if polygon is None: return lines
    output=[]
    for line in lines:
        current=[]
        for a,b in zip(line,line[1:]):
            values=[0.,1.]
            for c,d in zip(polygon,polygon[1:]+polygon[:1]): values+=intersections(a,b,c,d)
            values=sorted(set(max(0.,min(1.,t)) for t in values))
            for t0,t1 in zip(values,values[1:]):
                if t1-t0<1e-10: continue
                at=lambda t:[float(a[0]+t*(b[0]-a[0])),float(a[1]+t*(b[1]-a[1]))]
                if inside(at((t0+t1)/2),polygon):
                    start,end=at(t0),at(t1)
                    if current and math.dist(current[-1],start)>1e-8:
                        if len(current)>1: output.append(current)
                        current=[]
                    if not current: current=[start]
                    current.append(end)
                elif current:
                    if len(current)>1: output.append(current)
                    current=[]
        if len(current)>1: output.append(current)
    return output
