"""Native-resolution WMS tiles with persistent disk cache and progress."""
import hashlib
import json
import math
import threading
import time
from pathlib import Path
import cv2
import numpy as np
import requests
from ortho_sources import provider
ROOT = Path(__file__).resolve().parent / 'cache' / 'orthophotos'
MAX_PIXELS = None  # Temporarily disabled for performance tests; restore 32_000_000 to enable.
TILE_SIZE = 1024
lock = threading.Lock()
progress_lock = threading.Lock()
progress = {}

def update(token, **data):
    if not token: return
    with progress_lock:
        if len(progress)>100: progress.pop(next(iter(progress)))
        progress[token] = {**progress.get(token, {}), **data}

def download(bbox, source, gsd, token=None, max_pixels=None):
    service = provider(source)
    gsd = float(gsd)
    if not math.isfinite(gsd) or not .1<=gsd<=5:
        raise ValueError('Selecciona una resolucion de 0,1 a 5 metros por pixel.')
    lat = math.degrees(2*math.atan(math.exp((bbox[1]+bbox[3])/2/6378137))-math.pi/2)
    factor = math.cos(math.radians(lat))
    w = max(1,math.ceil((bbox[2]-bbox[0])*factor/gsd))
    h = max(1,math.ceil((bbox[3]-bbox[1])*factor/gsd))
    limit = MAX_PIXELS if max_pixels is None else max_pixels
    if limit and w*h>limit:
        raise ValueError(f'El area requiere {w*h/1e6:.1f} millones de pixeles (limite {limit/1e6:g}). Aumenta los metros por pixel o reduce el area; no se reducira la resolucion automaticamente.')
    digest = hashlib.sha256(json.dumps([source,service['layer'],list(bbox),gsd]).encode()).hexdigest()[:24]
    folder = ROOT/digest
    total = math.ceil(w/TILE_SIZE)*math.ceil(h/TILE_SIZE)
    update(token,status='running',completed=0,total=total,width=w,height=h)
    try:
        with lock:
            folder.mkdir(parents=True,exist_ok=True)
            if (folder/'ready.json').is_file():
                update(token,status='done',completed=total,cached=True)
                return np.load(folder/'image.npy',mmap_mode='r'),total
            mosaic = np.lib.format.open_memmap(folder/'image.npy',mode='w+',dtype=np.uint8,shape=(h,w,3))
            completed = 0
            for y in range(0,h,TILE_SIZE):
                for x in range(0,w,TILE_SIZE):
                    tw,th = min(TILE_SIZE,w-x),min(TILE_SIZE,h-y)
                    tile_path = folder/f'{x}-{y}.png'
                    tile = cv2.imread(str(tile_path)) if tile_path.is_file() else None
                    if tile is None or tile.shape!=(th,tw,3):
                        box = [bbox[0]+x/w*(bbox[2]-bbox[0]),bbox[3]-(y+th)/h*(bbox[3]-bbox[1]),bbox[0]+(x+tw)/w*(bbox[2]-bbox[0]),bbox[3]-y/h*(bbox[3]-bbox[1])]
                        for attempt in range(3):
                            try:
                                response = requests.get(service['url'],params={'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetMap','LAYERS':service['layer'],'STYLES':'','CRS':'EPSG:3857','BBOX':','.join(map(str,box)),'WIDTH':tw,'HEIGHT':th,'FORMAT':'image/jpeg','TRANSPARENT':'FALSE'},timeout=(10,45))
                                response.raise_for_status()
                                if len(response.content)>8*1024**2: raise ValueError('Respuesta WMS demasiado grande.')
                                tile = cv2.imdecode(np.frombuffer(response.content,np.uint8),cv2.IMREAD_COLOR)
                                if tile is None or tile.shape!=(th,tw,3): raise ValueError('El WMS devolvio una tesela no valida.')
                                if not cv2.imwrite(str(tile_path),tile): raise ValueError('No se pudo guardar la tesela.')
                                break
                            except (requests.RequestException,ValueError):
                                if attempt==2: raise
                                time.sleep(2**attempt)
                    mosaic[y:y+th,x:x+tw] = tile
                    completed += 1
                    update(token,completed=completed)
            mosaic.flush()
            (folder/'ready.json').write_text(json.dumps({'bbox':bbox,'source':source,'gsd':gsd,'width':w,'height':h,'tiles':total}))
            del mosaic
        update(token,status='done',completed=total,cached=False)
        return np.load(folder/'image.npy',mmap_mode='r'),total
    except Exception as error:
        update(token,status='failed',error=str(error))
        raise
