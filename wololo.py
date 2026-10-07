"""Endpoint-guided segmentation of native pixels, with bounded cached tiles."""
import heapq
import math
from collections import OrderedDict

import cv2
import numpy as np
import extraction

cache = OrderedDict()
DEFAULT_SEARCH_LIMIT = 2300000
MIN_SEARCH_LIMIT = 10000
MAX_SEARCH_LIMIT = 3000000


def center_penalty(probability, threshold):
    """Prefer medial ridges of the detected road; keep uncertain gaps traversable."""
    mask = np.uint8(probability >= threshold)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3,3),np.uint8))
    padded = cv2.copyMakeBorder(mask,1,1,1,1,cv2.BORDER_CONSTANT,value=0)
    distance = cv2.distanceTransform(padded,cv2.DIST_L2,cv2.DIST_MASK_PRECISE)[1:-1,1:-1]
    local_width = cv2.dilate(distance,np.ones((65,65),np.uint8))
    ratio = np.divide(distance,local_width,out=np.zeros_like(distance),where=local_width>0)
    return np.where(mask>0,12*(1-ratio)**2,0).astype(np.float32)


def simplify_path(points, tolerance_m, bbox):
    """Douglas-Peucker in ground metres, with exact endpoints retained."""
    if len(points)<=2:
        return points
    latitude = 2*math.atan(math.exp((bbox[1]+bbox[3])/2/6378137))-math.pi/2
    sx,sy = (bbox[2]-bbox[0])*math.cos(latitude),(bbox[3]-bbox[1])*math.cos(latitude)
    metric = np.array([[x*sx,y*sy] for x,y in points],np.float32)
    line = cv2.approxPolyDP(metric.reshape(-1,1,2),tolerance_m,False).reshape(-1,2)
    original = {tuple(xy):p for xy,p in zip(metric,points)}
    result = [list(original[tuple(xy)]) for xy in line]
    result[0],result[-1] = points[0],points[-1]
    return result


def route(probability, start, end, search_limit=DEFAULT_SEARCH_LIMIT, centering=None):
    """A* keeps alternatives open; no irreversible tile-by-tile choices."""
    h, w = probability.shape
    queue = [(math.dist(start, end), 0., start)]
    distances = {start: 0.}
    parents = {}
    steps = [(dx, dy, math.hypot(dx, dy)) for dx in (-1, 0, 1)
             for dy in (-1, 0, 1) if dx or dy]
    while queue:
        _, distance, current = heapq.heappop(queue)
        if distance != distances.get(current):
            continue
        if current == end:
            result = [end]
            while result[-1] != start:
                result.append(parents[result[-1]])
            return result[::-1]
        if len(distances) > search_limit:
            raise ValueError(f'Se ha alcanzado el límite de {search_limit:,} píxeles por conexión. Aumenta el límite de búsqueda o añade un punto sobre el camino y reintenta.')
        x, y = current
        for dx, dy, length in steps:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h) or probability[ny, nx] < 0:
                continue
            cost = 1 + 30 * (1 - float(probability[ny, nx])) ** 2
            if centering is not None:
                cost += float(centering[ny,nx])
            candidate = distance + length * cost
            neighbour = (nx, ny)
            if candidate < distances.get(neighbour, math.inf):
                distances[neighbour] = candidate
                parents[neighbour] = current
                heapq.heappush(queue, (candidate + math.dist(neighbour, end), candidate, neighbour))
    raise ValueError('No hay conexión en la zona analizada. Añade un punto intermedio para indicar el desvío.')


def trace(image, anchors, threshold, image_key, search_limit=DEFAULT_SEARCH_LIMIT, tolerance_m=.5, bbox=None):
    h, w = image.shape[:2]
    if bbox is None:
        bbox = (0.,0.,float(w),float(h))
    pixels = [(min(w-1, int(x*w)), min(h-1, int(y*h))) for x, y in anchors]
    probability = np.full((h, w), -1., np.float32)
    sums, weights = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
    padded = cv2.copyMakeBorder(image, 0, max(0,512-h), 0, max(0,512-w), cv2.BORDER_REFLECT_101)
    window = np.maximum(.05, np.outer(np.hanning(512), np.hanning(512))).astype(np.float32)
    tiles = set()
    # A broad corridor leaves room for curves and alternative directions.
    for a, b in zip(pixels, pixels[1:]):
        for t in np.linspace(0, 1, max(2, int(math.dist(a,b)/128)+1)):
            x, y = a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])
            for dx in (-256, 0, 256):
                for dy in (-256, 0, 256):
                    tx = max(0, min(max(0,w-512), int((x+dx-256)//256)*256))
                    ty = max(0, min(max(0,h-512), int((y+dy-256)//256)*256))
                    tiles.add((tx,ty))
    computed = 0
    with extraction.model_lock:
        if extraction.model is None:
            raise ValueError('Wololo necesita un modelo ONNX activo.')
        for x, y in sorted(tiles):
            key = (image_key, id(extraction.model), x, y)
            if key not in cache:
                cache[key] = extraction.probabilities(extraction.model, padded[y:y+512,x:x+512])
                computed += 1
                if len(cache) > 256:
                    cache.popitem(last=False)
            tile = cache[key]
            cache.move_to_end(key)
            hh, ww = min(512,h-y), min(512,w-x)
            sums[y:y+hh,x:x+ww] += tile[:hh,:ww]*window[:hh,:ww]
            weights[y:y+hh,x:x+ww] += window[:hh,:ww]
    valid = weights > 0
    probability[valid] = sums[valid]/weights[valid]
    centering = center_penalty(probability,threshold)
    sections = []
    raw_nodes = 0
    for leg,(a, b) in enumerate(zip(pixels, pixels[1:])):
        raw = route(probability, a, b, search_limit,centering)
        # Review one short stretch at a time, preserving all original pixels for search.
        for offset in range(0, len(raw)-1, 192):
            part = raw[offset:min(offset+193,len(raw))]
            values = np.array([probability[y,x] for x,y in part])
            junction = False
            for x,y in part[::48]:
                if x<32 or y<32 or x+33>w or y+33>h:
                    continue
                patch = probability[y-32:y+33,x-32:x+33]
                yy,xx = np.ogrid[-32:33,-32:33]
                ring = np.uint8((patch >= threshold) & (xx*xx+yy*yy >= 24**2) & (xx*xx+yy*yy <= 27**2))
                count,_,stats,_ = cv2.connectedComponentsWithStats(ring,8)
                if sum(stats[i,cv2.CC_STAT_AREA] >= 4 for i in range(1,count)) >= 3:
                    junction = True
                    break
            points = [[float((x+.5)/w),float((y+.5)/h)] for x,y in part]
            if offset==0:
                points[0] = anchors[leg]
            if offset+193>=len(raw):
                points[-1] = anchors[leg+1]
            raw_nodes += len(points)
            points = simplify_path(points,tolerance_m,bbox)
            low = float(np.mean(values < threshold))
            sections.append({'path': points, 'uncertain': low > .15 or junction, 'junction':junction,
                             'low_fraction': round(low,3), 'confidence': round(float(values.mean()),3)})
    if not sections:
        raise ValueError('Separa los marcadores de inicio y fin.')
    sections[0]['path'][0] = anchors[0]
    sections[-1]['path'][-1] = anchors[-1]
    return sections, {'tiles':len(tiles), 'computed_tiles':computed, 'search_limit':search_limit,
                      'centered':True, 'tolerance_m':tolerance_m,'raw_nodes':raw_nodes,
                      'simplified_nodes':sum(len(s['path']) for s in sections)}
