"""Candidate masks and centerlines, independent of the web interface."""
import threading
import cv2
import numpy as np

model_lock = threading.Lock()
model = None
model_name = None


def probabilities(net, image):
    # Explicit contract: RGB [0,1], NCHW 1x3x512x512; binary probability output.
    blob = cv2.dnn.blobFromImage(image, 1/255.0, (512,512), swapRB=True)
    net.setInput(blob)
    result = np.asarray(net.forward())
    if result.ndim != 4 or result.shape[:2] != (1,1) or min(result.shape[2:]) < 2:
        raise ValueError('El modelo debe devolver probabilidades con forma 1×1×H×W.')
    result = result[0,0]
    if not np.isfinite(result).all() or result.min() < 0 or result.max() > 1:
        raise ValueError('La salida debe contener probabilidades entre 0 y 1 (sigmoid incluida).')
    return cv2.resize(result, (512,512))


def tiled_probabilities(net, image):
    """Keep original raster detail; blend overlapping 512px predictions."""
    height, width = image.shape[:2]
    padded = cv2.copyMakeBorder(image,0,max(0,512-height),0,max(0,512-width),cv2.BORDER_REFLECT_101)
    h,w = padded.shape[:2]
    def starts(length):
        return sorted(set(list(range(0,length-512+1,256))+[length-512]))
    window = np.maximum(.05,np.outer(np.hanning(512),np.hanning(512))).astype(np.float32)
    total,weights = np.zeros((h,w),np.float32),np.zeros((h,w),np.float32)
    tiles = 0
    for y in starts(h):
        for x in starts(w):
            tile = probabilities(net,padded[y:y+512,x:x+512])
            total[y:y+512,x:x+512] += tile*window
            weights[y:y+512,x:x+512] += window
            tiles += 1
    return np.clip((total/weights)[:height,:width],0,1),tiles


def candidate_mask(image, mode, threshold, return_info=False):
    info = {'mode':mode}
    if mode == 'segmentation':
        with model_lock:
            if model is None:
                raise ValueError('Carga primero un modelo ONNX de segmentación de caminos.')
            probability,tiles = tiled_probabilities(model, image)
        info.update(probability_max=float(probability.max()), tiles=tiles)
        mask = np.uint8(probability >= threshold) * 255
    elif mode == 'automatic':
        small = image  # Analyze downloaded pixels; display zoom never controls processing.
        hsv = cv2.cvtColor(cv2.GaussianBlur(small,(5,5),0),cv2.COLOR_BGR2HSV)
        # Bright, low-saturation ground; deliberately a heuristic, not a classifier.
        mask = np.uint8((hsv[:,:,1] <= 125 - threshold*90) & (hsv[:,:,2] >= 65 + threshold*100))*255
    else:
        raise ValueError('Modo de detección desconocido.')
    info['pixels_before_cleanup'] = int(np.count_nonzero(mask))
    mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    clean = np.zeros_like(mask)
    for i in range(1,count):
        _,_,w,h,area = stats[i]
        if area >= 35 and max(w,h) >= 25 and (mode == 'segmentation' or area / max(w*h,1) < .7):
            clean[labels == i] = 255
    info['pixels_after_cleanup'] = int(np.count_nonzero(clean))
    info['coverage_percent'] = round(100*info['pixels_after_cleanup']/clean.size,2)
    return (clean,info) if return_info else clean


def thin(mask):
    pixels = np.pad(mask > 0,1).astype(np.uint8)
    while True:
        changed = False
        for phase in (0,1):
            p = pixels[1:-1,1:-1]
            n = [pixels[:-2,1:-1],pixels[:-2,2:],pixels[1:-1,2:],pixels[2:,2:],
                 pixels[2:,1:-1],pixels[2:,:-2],pixels[1:-1,:-2],pixels[:-2,:-2]]
            neighbors = sum(n)
            transitions = sum(((n[i] == 0) & (n[(i+1)%8] == 1)).astype(np.uint8) for i in range(8))
            if phase == 0:
                products = (n[0]*n[2]*n[4] == 0) & (n[2]*n[4]*n[6] == 0)
            else:
                products = (n[0]*n[2]*n[6] == 0) & (n[0]*n[4]*n[6] == 0)
            remove = (p == 1) & (neighbors >= 2) & (neighbors <= 6) & (transitions == 1) & products
            if remove.any():
                p[remove] = 0
                changed = True
        if not changed:
            return pixels[1:-1,1:-1]


def centerlines(mask):
    skeleton = thin(mask)
    pixels = set(zip(*np.nonzero(skeleton)))
    adjacency = {p: sorted((p[0]+dy,p[1]+dx) for dy in (-1,0,1) for dx in (-1,0,1)
        if (dx or dy) and (p[0]+dy,p[1]+dx) in pixels
        and not (dx and dy and ((p[0],p[1]+dx) in pixels or (p[0]+dy,p[1]) in pixels))) for p in pixels}
    visited = set()
    paths = []
    # Begin at ends and junctions, then cover closed loops.
    starts = sorted(p for p in pixels if len(adjacency[p]) != 2) + sorted(pixels)
    for start in starts:
        for neighbor in adjacency[start]:
            edge = frozenset((start,neighbor))
            if edge in visited:
                continue
            visited.add(edge)
            chain = [start,neighbor]
            while len(adjacency[chain[-1]]) == 2:
                options = [p for p in adjacency[chain[-1]] if frozenset((chain[-1],p)) not in visited]
                if not options:
                    break
                nxt = options[0]
                visited.add(frozenset((chain[-1],nxt)))
                chain.append(nxt)
            if len(chain) < 12:
                continue
            xy = np.array([[(x+.5)/mask.shape[1],(y+.5)/mask.shape[0]] for y,x in chain],np.float32)
            line = cv2.approxPolyDP(xy.reshape(-1,1,2),1/max(mask.shape),False).reshape(-1,2).tolist()
            if len(line) >= 2:
                paths.append(line)
    return sorted(paths,key=lambda p:sum(np.linalg.norm(np.subtract(a,b)) for a,b in zip(p,p[1:])),reverse=True)[:200]
