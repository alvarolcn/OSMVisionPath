from ortho_sources import provider, image_key
"""Local PNOA orthophoto viewer and assisted path extraction."""
import base64
import heapq
import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import requests
import extraction
import wololo
import ortho_mosaic
import polygon_area
import system_memory
from collections import OrderedDict
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024 * 1024
WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
R = 6378137.0
ORTHO_SIZE = 4096  # GetCapabilities advertises MaxWidth/MaxHeight = 4096.
local_model_checked = False
downloaded_images = OrderedDict()


def ensure_local_model():
    """Also support flask run and IDE launches that import app instead of running it."""
    global local_model_checked
    with extraction.model_lock:
        if extraction.model is not None or local_model_checked:
            return
        local_model_checked = True
        local_model = Path(__file__).resolve().parent / 'models' / 'model.onnx'
        if not local_model.is_file() or not local_model.with_suffix('.verification.json').is_file():
            return
        try:
            net = cv2.dnn.readNetFromONNX(str(local_model))
            extraction.probabilities(net,np.zeros((512,512,3),np.uint8))
            extraction.model = net
            extraction.model_name = local_model.name
            app.logger.info('Modelo local cargado: %s',local_model.name)
        except (cv2.error,ValueError):
            app.logger.exception('No se pudo cargar el modelo local; puedes cargar otro ONNX en la GUI')


def project(lon, lat):
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def unproject(x, y):
    return [math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)]


def encode(image):
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("No se pudo codificar la imagen.")
    return "data:image/png;base64," + base64.b64encode(data).decode()


@lru_cache(maxsize=2)
def orthophoto(bbox, source="pnoa"):
    service = provider(source)
    size = service["size"]
    ratio = (bbox[3]-bbox[1])/(bbox[2]-bbox[0])
    width,height = (size,max(1,round(size*ratio))) if ratio<=1 else (max(1,round(size/ratio)),size)
    response = requests.get(service["url"], params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
        "LAYERS": service["layer"], "STYLES": "", "CRS": "EPSG:3857",
        "BBOX": ",".join(map(str, bbox)), "WIDTH": width, "HEIGHT": height,
        "FORMAT": "image/jpeg", "TRANSPARENT": "FALSE"}, timeout=(10, 45))
    response.raise_for_status()
    if len(response.content) > 32 * 1024 * 1024:
        raise ValueError("La respuesta WMS excede el tamaño permitido.")
    image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[:2] != (height, width):
        raise ValueError(f"El WMS no devolvió una ortofoto válida de {size} × {size}.")
    return image


def read_bbox(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("Área no válida.")
    bbox = tuple(float(x) for x in value)
    if not all(math.isfinite(x) and abs(x) < 21000000 for x in bbox):
        raise ValueError("Coordenadas fuera de rango.")
    width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if not (100 <= width <= 50000 and 100 <= height <= 50000):
        raise ValueError("El área debe tener ancho y alto entre 100 y 50000 metros proyectados.")
    return bbox


def shortest_path(cost, start, end):
    h, w = cost.shape
    distances = np.full((h, w), np.inf)
    parents = np.full((h, w, 2), -1, dtype=np.int16)
    sx, sy = start
    ex, ey = end
    distances[sy, sx] = 0
    queue = [(0.0, sx, sy)]
    steps = [(dx, dy, math.hypot(dx, dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    while queue:
        distance, x, y = heapq.heappop(queue)
        if distance > distances[y, x]:
            continue
        if (x, y) == (ex, ey):
            break
        for dx, dy, length in steps:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                candidate = distance + length * (float(cost[y, x]) + float(cost[ny, nx])) / 2
                if candidate < distances[ny, nx]:
                    distances[ny, nx] = candidate
                    parents[ny, nx] = [x, y]
                    heapq.heappush(queue, (candidate, nx, ny))
    result = [(ex, ey)]
    while result[-1] != (sx, sy):
        x, y = result[-1]
        px, py = parents[y, x]
        if px < 0:
            raise ValueError("No se encontró conexión entre los puntos.")
        result.append((int(px), int(py)))
    return result[::-1]


def detect(image, points, sensitivity):
    """Color-based least-cost path; user anchors define intent, not a road classifier."""
    size = 384
    small = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(cv2.GaussianBlur(small, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    anchors = [(min(size - 1, int(x * size)), min(size - 1, int(y * size))) for x, y in points]
    samples = [np.median(lab[max(0,y-2):y+3, max(0,x-2):x+3].reshape(-1, 3), axis=0) for x, y in anchors]
    color_distance = np.minimum.reduce([np.linalg.norm(lab - s, axis=2) for s in samples])
    cost = 1 + (color_distance / sensitivity) ** 2
    routes = []
    for a, b in zip(anchors, anchors[1:]):
        section = shortest_path(cost, a, b)
        routes.extend(section if not routes else section[1:])
    # Pixel centers preserve the raster-to-map convention used by the viewer.
    path = np.array([[(x + .5) / size, (y + .5) / size] for x, y in routes], dtype=np.float32)
    simplified = cv2.approxPolyDP(path.reshape(-1, 1, 2), 1 / size, False).reshape(-1, 2).tolist()
    simplified[0], simplified[-1] = points[0], points[-1]
    return simplified


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/health")
def health():
    ensure_local_model()
    return jsonify(opencv=cv2.__version__, model=extraction.model_name)


@app.post('/api/model')
def upload_model():
    uploaded = request.files.get('model')
    if uploaded is None or not uploaded.filename.lower().endswith('.onnx'):
        raise ValueError('Selecciona un archivo ONNX de segmentación (máximo 255 MB de archivo).')
    try:
        net = cv2.dnn.readNetFromONNX(np.frombuffer(uploaded.read(),np.uint8))
        extraction.probabilities(net,np.zeros((512,512,3),np.uint8))
    except cv2.error as exc:
        raise ValueError('OpenCV no puede ejecutar este ONNX con la entrada requerida. Consulta el contrato del modelo.') from exc
    with extraction.model_lock:
        extraction.model = net
        extraction.model_name = uploaded.filename.replace('\\','/').split('/')[-1]
        wololo.cache.clear()
    return jsonify(model=extraction.model_name)


@app.post('/api/extract')
def extract():
    data = request.get_json()
    bbox = read_bbox(data['bbox'])
    threshold = float(data.get('threshold',.5))
    if not math.isfinite(threshold) or not .05 <= threshold <= .95:
        raise ValueError('El umbral debe estar entre 0.05 y 0.95.')
    mode = data.get('mode','automatic')
    if mode == 'segmentation':
        ensure_local_model()
    polygon = polygon_area.validate(data.get('polygon'))
    mask,info = extraction.candidate_mask(analysis_image(bbox,data.get("source","pnoa")),mode,threshold,return_info=True)
    if polygon is not None:
        mask[polygon_area.mask(polygon,mask.shape)==0] = 0
        info['coverage_percent'] = round(100*float(np.count_nonzero(mask))/mask.size,2)
    paths = polygon_area.clip(extraction.centerlines(mask),polygon)
    return jsonify(paths=paths, mask=encode(mask), diagnostics=info, geojson=paths_geojson(paths,bbox,mode,data.get("source","pnoa")),
                   message='Candidatos detectados. Selecciona uno para corregirlo.' if paths else 'No se encontraron trazados. Ajusta el umbral o usa puntos manuales.')


def paths_geojson(paths,bbox,method,source="pnoa"):
    return {'type':'FeatureCollection','features':[{'type':'Feature','properties':{
        'source':provider(source)['label'],'method':method,'review_required':True},'geometry':{'type':'LineString',
        'coordinates':[unproject(bbox[0]+x*(bbox[2]-bbox[0]),bbox[3]-y*(bbox[3]-bbox[1])) for x,y in path]}}
        for path in paths]}


@app.get('/api/system-memory')
def system_memory_info():
    return jsonify(system_memory.memory_info())


@app.get('/api/ortho-progress/<token>')
def ortho_progress(token):
    with ortho_mosaic.progress_lock:
        return jsonify(ortho_mosaic.progress.get(token,{'status':'waiting','completed':0,'total':0}))


def analysis_image(bbox,source='pnoa'):
    cached = downloaded_images.get(image_key(bbox,source))
    if cached is not None: return cached
    return orthophoto(bbox) if source=='pnoa' else orthophoto(bbox,source)


@app.post("/api/ortho")
def load():
    data = request.get_json()
    lon, lat, span = float(data["lon"]), float(data["lat"]), float(data["span"])
    if not all(math.isfinite(v) for v in (lon, lat, span)) or not (-19 <= lon <= 5 and 27 <= lat <= 44.5 and 100 <= span <= 30000):
        raise ValueError("Introduce un centro en España y un ancho de 100 a 30000 m.")
    x, y = project(lon, lat)
    # Ground distance converted to Web Mercator distance at the center latitude.
    half = span / math.cos(math.radians(lat)) / 2
    if half * 2 > 50000:
        raise ValueError("Reduce el ancho: el límite es 50000 m en la proyección.")
    bbox = (x-half, y-half, x+half, y+half)
    source = data.get("source","pnoa")
    provider(source)
    if "bbox" in data:
        bbox = read_bbox(data["bbox"])
    polygon_area.validate(data.get('polygon'))
    tiles = 1
    if 'gsd' in data:
        token = data.get('progress_id')
        if token is not None and (not isinstance(token,str) or not token.isalnum() or len(token)>64):
            raise ValueError('Identificador de descarga no valido.')
        megapixels=data.get('max_megapixels')
        if megapixels is not None and (isinstance(megapixels,bool) or not isinstance(megapixels,(int,float)) or not math.isfinite(megapixels) or megapixels<0):
            raise ValueError('El limite de megapixeles debe ser un numero positivo, o 0 sin limite.')
        limit=None if megapixels is None else int(megapixels*1e6)
        image,tiles = ortho_mosaic.download(bbox,source,data['gsd'],token,max_pixels=limit)
    else:
        image = orthophoto(bbox) if source=="pnoa" else orthophoto(bbox,source)
    downloaded_images[image_key(bbox,source)] = image
    downloaded_images.move_to_end(image_key(bbox,source))
    while len(downloaded_images) > 2:
        downloaded_images.popitem(last=False)
    height,width = image.shape[:2]
    preview = image
    if max(width,height)>4096:
        ratio = 4096/max(width,height)
        preview = cv2.resize(image,(round(width*ratio),round(height*ratio)),interpolation=cv2.INTER_AREA)
    ground_width = (bbox[2]-bbox[0])*math.cos(math.radians(unproject((bbox[0]+bbox[2])/2,(bbox[1]+bbox[3])/2)[1]))
    return jsonify(image=encode(preview), bbox=bbox, width=width, height=height,
                   meters_per_pixel=round(ground_width/width,4),source=source,tiles=tiles)


@app.post('/api/wololo')
def guided_trace():
    data = request.get_json()
    bbox = read_bbox(data['bbox'])
    image = downloaded_images.get(image_key(bbox,data.get("source","pnoa")))
    if image is None:
        raise ValueError('Vuelve a cargar la ortofoto: ya no está disponible en memoria. Wololo no descarga imágenes nuevas.')
    anchors = data.get('points')
    if not isinstance(anchors,list) or not 2 <= len(anchors) <= 20:
        raise ValueError('Marca inicio y fin, con un máximo de 18 puntos intermedios.')
    checked = []
    for point in anchors:
        if not isinstance(point,list) or len(point) != 2:
            raise ValueError('Marcador no válido.')
        point = [float(v) for v in point]
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in point):
            raise ValueError('Los marcadores deben estar dentro de la ortofoto.')
        checked.append(point)
    if any(math.dist(a,b) < .003 for a,b in zip(checked,checked[1:])):
        raise ValueError('Separa los marcadores consecutivos.')
    threshold = float(data.get('threshold',.5))
    if not math.isfinite(threshold) or not .05 <= threshold <= .95:
        raise ValueError('El umbral debe estar entre 0.05 y 0.95.')
    ensure_local_model()
    search_limit = data.get('search_limit',wololo.DEFAULT_SEARCH_LIMIT)
    if isinstance(search_limit,bool) or not isinstance(search_limit,int) or not wololo.MIN_SEARCH_LIMIT <= search_limit <= wololo.MAX_SEARCH_LIMIT:
        raise ValueError('El límite de búsqueda debe ser un entero entre 10.000 y 3.000.000 píxeles por conexión.')
    tolerance = float(data.get('tolerance_m',.5))
    if not math.isfinite(tolerance) or tolerance not in (.25,.5,1.,2.,5.):
        raise ValueError('Selecciona una tolerancia de 0,25; 0,5; 1; 2 o 5 metros.')
    polygon = polygon_area.validate(data.get('polygon'))
    if polygon is not None and any(not polygon_area.inside(point,polygon) for point in checked):
        raise ValueError('Todos los marcadores deben estar dentro del poligono seleccionado.')
    options = {'polygon':polygon} if polygon is not None else {}
    sections, diagnostics = wololo.trace(image,checked,threshold,bbox,search_limit,tolerance_m=tolerance,bbox=bbox,**options)
    return jsonify(sections=sections,diagnostics=diagnostics)


@app.post("/api/detect")
def trace():
    data = request.get_json()
    bbox = read_bbox(data["bbox"])
    points = data["points"]
    if not isinstance(points, list) or not 2 <= len(points) <= 20:
        raise ValueError("Marca entre 2 y 20 puntos sobre el camino.")
    checked = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("Punto no válido.")
        point = [float(v) for v in point]
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in point):
            raise ValueError("Los puntos deben quedar dentro de la imagen.")
        checked.append(point)
    if any(math.dist(a,b) < .003 for a,b in zip(checked,checked[1:])):
        raise ValueError("Separa los puntos consecutivos del trazado.")
    sensitivity = float(data.get("sensitivity", 25))
    if not math.isfinite(sensitivity) or not 5 <= sensitivity <= 80:
        raise ValueError("Sensibilidad fuera de rango.")
    path = detect(analysis_image(bbox,data.get("source","pnoa")), checked, sensitivity)
    coords = [unproject(bbox[0]+x*(bbox[2]-bbox[0]), bbox[3]-y*(bbox[3]-bbox[1])) for x,y in path]
    meters = 0
    for a,b in zip(coords,coords[1:]):
        lat1,lat2 = math.radians(a[1]),math.radians(b[1])
        dlat,dlon = lat2-lat1,math.radians(b[0]-a[0])
        v = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        meters += 2*R*math.asin(min(1,math.sqrt(v)))
    geojson = {"type":"FeatureCollection", "features":[{"type":"Feature", "properties":{
        "source":provider(data.get("source","pnoa"))["label"], "method":"assisted-color-least-cost", "review_required":True, "length_m":round(meters,1)},
        "geometry":{"type":"LineString", "coordinates":coords}}]}
    return jsonify(path=path, geojson=geojson, length=round(meters,1))


@app.errorhandler(Exception)
def error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description), exc.code
    if isinstance(exc, (ValueError, KeyError, TypeError, OverflowError)):
        return jsonify(error=str(exc)), 400
    if isinstance(exc, requests.RequestException):
        app.logger.warning("Error al conectar con el WMS del IGN: %s", exc)
        if "10013" in str(exc):
            message = ("Windows ha bloqueado la conexión del servidor al IGN (WinError 10013). "
                       "Ejecuta app.py desde una terminal local con acceso a internet "
                       "o autoriza el acceso a red si lo ejecutas desde Codex.")
        elif isinstance(exc, requests.Timeout):
            message = "El WMS de ortofotos ha tardado demasiado en responder. Inténtalo de nuevo."
        elif isinstance(exc, requests.exceptions.SSLError):
            message = "No se pudo verificar el certificado HTTPS del IGN. Revisa los certificados y el proxy de tu red."
        elif isinstance(exc, requests.HTTPError):
            message = f"El WMS de ortofotos devolvió HTTP {exc.response.status_code}. Inténtalo de nuevo más tarde."
        else:
            message = "No se pudo conectar con el WMS de ortofotos. Revisa la conexión a internet y el proxy de tu red."
        return jsonify(error=message), 502
    app.logger.exception("Unexpected error")
    return jsonify(error="Error interno al procesar la imagen."), 500


import dataset_manager
dataset_manager.register(app,ensure_local_model)


if __name__ == "__main__":
    ensure_local_model()
    app.run(host="127.0.0.1", port=5000, debug=False)
