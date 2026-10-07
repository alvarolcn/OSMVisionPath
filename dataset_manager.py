from ortho_sources import provider
"""Local PNOA datasets, CVAT mask exchange and background training jobs."""
import base64
import atexit
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
import zipfile

import cv2
import numpy as np
import requests
from flask import Blueprint, jsonify, request, send_file
import extraction

ROOT = Path(__file__).resolve().parent
DATASETS = ROOT / 'datasets'
WMS = 'https://www.ign.es/wms-inspire/pnoa-ma'
R = 6378137.
jobs = {}
job_lock = threading.Lock()
data_lock = threading.RLock()
ensure_model = None
blueprint = Blueprint('datasets',__name__)


def write_json(path,value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)


def checked_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,90}',value):
        raise ValueError('Identificador no válido.')
    return value


def directory(dataset_id):
    path = DATASETS / checked_id(dataset_id)
    if not (path/'manifest.json').is_file():
        raise ValueError('Dataset no encontrado.')
    return path


def manifest(path):
    return json.loads((path/'manifest.json').read_text(encoding='utf-8'))


def tile_record(path,tile_id):
    tile_id = checked_id(tile_id)
    for tile in manifest(path)['tiles']:
        if tile['id']==tile_id:
            return tile
    raise ValueError('Tesela no encontrada.')


def project(lon,lat):
    return R*math.radians(lon),R*math.log(math.tan(math.pi/4+math.radians(lat)/2))


def plan(config):
    source = config.get("source","pnoa")
    provider(source)
    gsd = float(config.get('gsd',.2))
    threshold = float(config.get('threshold',.5))
    if not math.isfinite(gsd) or not .1<=gsd<=1:
        raise ValueError('La resolución debe estar entre 0,1 y 1 m/píxel.')
    if not math.isfinite(threshold) or not .05<=threshold<=.95:
        raise ValueError('El umbral debe estar entre 0,05 y 0,95.')
    areas = config.get('areas')
    if not isinstance(areas,list) or not 1<=len(areas)<=8:
        raise ValueError('Añade entre 1 y 8 zonas.')
    tiles,regions = [],[]
    for index,area in enumerate(areas):
        if not isinstance(area,dict):
            raise ValueError('Zona no válida.')
        bbox = area.get('bbox')
        if not isinstance(bbox,list) or len(bbox)!=4:
            raise ValueError('Cada bbox debe ser [oeste, sur, este, norte] en longitud/latitud WGS84.')
        west,south,east,north = map(float,bbox)
        if not all(math.isfinite(v) for v in (west,south,east,north)) or not (-19<=west<east<=5 and 27<=south<north<=44.5):
            raise ValueError('Bounding box no válido: debe estar en España y tener extensión positiva.')
        split = area.get('split','train')
        if split not in ('train','val','test'):
            raise ValueError('El conjunto debe ser train, val o test.')
        x0,y0 = project(west,south)
        x1,y1 = project(east,north)
        cell = 512*gsd/math.cos(math.radians((south+north)/2))
        columns,rows = math.ceil((x1-x0)/cell),math.ceil((y1-y0)/cell)
        if len(tiles)+columns*rows>256:
            raise ValueError('El lote supera 256 teselas. Reduce las zonas o aumenta los metros por píxel.')
        extent = [x0,y1-rows*cell,x0+columns*cell,y1]
        # Keep overlapping/adjacent footprints out of different splits.
        for old in regions:
            other = old['extent']
            margin = max(cell,old['cell'])
            overlap = extent[0]<other[2]+margin and extent[2]>other[0]-margin and extent[1]<other[3]+margin and extent[3]>other[1]-margin
            if overlap and split!=old['split']:
                raise ValueError('Las zonas de conjuntos distintos se solapan o son demasiado próximas. Separa entrenamiento y validación al menos una tesela.')
        regions.append({'bbox':[west,south,east,north],'split':split,'extent':extent,'cell':cell})
        for row in range(rows):
            for column in range(columns):
                tiles.append({'id':f'a{index:02d}_r{row:03d}_c{column:03d}',
                    'area':index,'split':split,'bbox_3857':[x0+column*cell,y1-(row+1)*cell,x0+(column+1)*cell,y1-row*cell],
                    'reviewed':False,'mask_source':'automatic'})
    return {'source_id':source,'gsd':gsd,'threshold':threshold,'areas':regions,'tiles':tiles,'tile_count':len(tiles)}


def download_tile(bbox,source="pnoa"):
    service = provider(source)
    response = requests.get(service["url"],params={'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetMap',
        'LAYERS':service['layer'],'STYLES':'','CRS':'EPSG:3857','BBOX':','.join(map(str,bbox)),
        'WIDTH':512,'HEIGHT':512,'FORMAT':'image/jpeg','TRANSPARENT':'FALSE'},timeout=(10,45))
    response.raise_for_status()
    if len(response.content)>8*1024**2:
        raise ValueError('Respuesta WMS demasiado grande.')
    image = cv2.imdecode(np.frombuffer(response.content,np.uint8),cv2.IMREAD_COLOR)
    if image is None or image.shape!=(512,512,3):
        raise ValueError('El WMS no devolvió una imagen válida de 512×512.')
    return image


def generate(path,config,net,model_name,progress=lambda **kwargs:None,cancel=lambda:False):
    specification = plan(config)
    path.mkdir(parents=True,exist_ok=False)
    (path/'images').mkdir()
    (path/'masks').mkdir()
    meta = {**specification,'id':path.name,'name':str(config.get('name','Dataset PNOA'))[:100],
        'source':provider(specification['source_id'])['label'],'source_model':model_name,'status':'generating','tiles':[],
        'created_at':time.time(),'classes':{'background':0,'road':1}}
    write_json(path/'manifest.json',meta)
    try:
        for index,tile in enumerate(specification['tiles']):
            if cancel():
                meta['status']='cancelled'
                break
            progress(message=f'Descargando y segmentando tesela {index+1}/{specification["tile_count"]}',completed=index,total=specification['tile_count'])
            image = download_tile(tile['bbox_3857']) if specification['source_id']=='pnoa' else download_tile(tile['bbox_3857'],specification['source_id'])
            if cancel():
                meta['status']='cancelled'
                break
            with extraction.model_lock:
                probability = extraction.probabilities(net,image)
            mask = np.uint8(probability>=specification['threshold'])*255
            for folder,array in (('images',image),('masks',mask)):
                if not cv2.imwrite(str(path/folder/f'{tile["id"]}.png'),array):
                    raise ValueError('No se pudo guardar la tesela.')
            tile['road_fraction'] = round(float(np.mean(mask>0)),4)
            tile['probability_max'] = float(probability.max())
            meta['tiles'].append(tile)
            with data_lock:
                write_json(path/'manifest.json',meta)
        else:
            meta['status']='ready'
    except Exception:
        meta['status']='failed'
        raise
    finally:
        with data_lock:
            write_json(path/'manifest.json',meta)
    return meta


def public_job(job):
    return {k:v for k,v in job.items() if k not in ('cancel','process')}


def start_job(kind,dataset_id,operation):
    with job_lock:
        if any(j['status']=='running' for j in jobs.values()):
            raise ValueError('Ya hay un trabajo de dataset o entrenamiento en curso. Espera o cancélalo.')
        job_id = uuid.uuid4().hex
        job = {'id':job_id,'kind':kind,'dataset_id':dataset_id,'status':'running','message':'Preparando…',
               'completed':0,'total':1,'cancel':threading.Event(),'log':[]}
        jobs[job_id] = job
        if len(jobs)>100:
            jobs.pop(next(iter(jobs)))
    def progress(**values):
        with job_lock:
            job.update(values)
    def worker():
        try:
            result = operation(job,progress)
            progress(status='cancelled' if job['cancel'].is_set() else 'done',result=result,
                     completed=job['completed'] if job['cancel'].is_set() else job['total'],
                     message='Cancelado. Se conservan los archivos ya generados.' if job['cancel'].is_set() else 'Trabajo completado.')
        except Exception as exc:
            progress(status='cancelled' if job['cancel'].is_set() else 'failed',message=str(exc))
    threading.Thread(target=worker,daemon=True).start()
    return public_job(job)


def idle():
    with job_lock:
        if any(j['status']=='running' for j in jobs.values()):
            raise ValueError('Espera a que termine el trabajo activo antes de modificar los datasets.')


def validate_mask(image):
    if image is None or image.shape!=(512,512) or not set(np.unique(image)).issubset({0,255}):
        raise ValueError('La máscara debe ser PNG de 512×512, con fondo 0 y vía 255.')
    return image


def save_mask(path,tile_id,mask,reviewed,source):
    validate_mask(mask)
    meta = manifest(path)
    tile = next((t for t in meta['tiles'] if t['id']==checked_id(tile_id)),None)
    if tile is None:
        raise ValueError('Tesela no encontrada.')
    if not cv2.imwrite(str(path/'masks'/f'{tile_id}.png'),mask):
        raise ValueError('No se pudo guardar la máscara.')
    tile.update(reviewed=reviewed,mask_source=source,road_fraction=round(float(np.mean(mask>0)),4))
    write_json(path/'manifest.json',meta)


def archive(path,kind):
    meta = manifest(path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as output:
        if kind in ('images','bundle'):
            for tile in meta['tiles']:
                output.write(path/'images'/f'{tile["id"]}.png',f'{tile["id"]}.png' if kind=='images' else f'images/{tile["id"]}.png')
        if kind in ('cvat','bundle'):
            output.writestr('labelmap.txt','background:0,0,0::\nroad:255,255,255::\n')
            output.writestr('ImageSets/Segmentation/default.txt','\n'.join(t['id'] for t in meta['tiles'])+'\n')
            for tile in meta['tiles']:
                mask = cv2.imread(str(path/'masks'/f'{tile["id"]}.png'),cv2.IMREAD_GRAYSCALE)
                # CVAT grayscale PNGs encode class indices; export RGB to use the labelmap colours.
                ok,encoded = cv2.imencode('.png',cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
                if not ok:
                    raise ValueError('No se pudo exportar la máscara.')
                output.writestr(f'SegmentationClass/{tile["id"]}.png',encoded.tobytes())
        if kind=='bundle':
            output.writestr('manifest.json',json.dumps(meta,indent=2,ensure_ascii=False))
            for tile in meta['tiles']:
                output.write(path/'masks'/f'{tile["id"]}.png',f'masks/{tile["id"]}.png')
    buffer.seek(0)
    return buffer


def import_cvat(path,stream):
    """Read archive members without extracting paths; convert class colours explicitly."""
    meta = manifest(path)
    known = {t['id'] for t in meta['tiles']}
    converted = {}
    with zipfile.ZipFile(stream) as source:
        infos = source.infolist()
        if len(infos)>2000 or sum(i.file_size for i in infos)>256*1024**2:
            raise ValueError('El ZIP supera el límite de importación.')
        labelmaps = [i for i in infos if Path(i.filename).name=='labelmap.txt']
        colours = {'background':(0,0,0),'road':(255,255,255)}
        class_order = ['background','road']
        if len(labelmaps)>1:
            raise ValueError('El ZIP contiene varios labelmap.txt.')
        if labelmaps:
            colours = {}
            class_order = []
            for line in source.read(labelmaps[0]).decode('utf-8-sig').splitlines():
                if not line.strip() or line.startswith('#'):
                    continue
                parts = line.split(':')
                if len(parts)<2:
                    continue
                name = parts[0].strip()
                if name not in ('background','road'):
                    raise ValueError('Usa únicamente las etiquetas background y road en CVAT.')
                colour = tuple(int(v) for v in parts[1].split(','))
                if len(colour)!=3 or any(v<0 or v>255 for v in colour):
                    raise ValueError('Color de etiqueta no válido.')
                colours[name] = colour
                class_order.append(name)
            colours.setdefault('background',(0,0,0))
        if 'road' not in colours or colours['road']==colours['background']:
            raise ValueError('Falta la etiqueta road o su color coincide con el fondo.')
        for info in infos:
            parts = info.filename.replace('\\','/').split('/')
            if 'SegmentationClass' not in parts or not parts[-1].lower().endswith('.png'):
                continue
            tile_id = Path(parts[-1]).stem
            if tile_id not in known:
                raise ValueError(f'La máscara {tile_id} no pertenece a este dataset.')
            if tile_id in converted:
                raise ValueError('Hay máscaras duplicadas en el ZIP.')
            if info.file_size>4*1024**2:
                raise ValueError('Máscara demasiado grande.')
            raw = np.frombuffer(source.read(info),np.uint8)
            indexed = cv2.imdecode(raw,cv2.IMREAD_UNCHANGED)
            if indexed is not None and indexed.shape==(512,512) and labelmaps and set(np.unique(indexed)).issubset(set(range(len(class_order)))):
                converted[tile_id] = np.uint8(indexed==class_order.index('road'))*255
                continue
            image = cv2.imdecode(raw,cv2.IMREAD_COLOR)
            if image is None or image.shape!=(512,512,3):
                raise ValueError('Todas las máscaras deben medir 512×512.')
            road = np.all(image==tuple(reversed(colours['road'])),axis=2)
            background = np.all(image==tuple(reversed(colours['background'])),axis=2)
            if not np.all(road|background):
                raise ValueError('La máscara contiene colores que no corresponden a road/background.')
            converted[tile_id] = np.uint8(road)*255
    if not converted:
        raise ValueError('No hay máscaras SegmentationClass en el ZIP.')
    for tile_id,mask in converted.items():
        save_mask(path,tile_id,mask,True,'cvat-reviewed')
    return len(converted)


def training_selection(meta,allow_automatic):
    tiles = [t for t in meta['tiles'] if t['reviewed'] or allow_automatic]
    train = [t for t in tiles if t['split']=='train']
    validation = [t for t in tiles if t['split']=='val']
    if not train or not validation:
        raise ValueError('Necesitas teselas de zonas separadas de entrenamiento y validación. Revisa sus máscaras o activa el modo experimental de máscaras automáticas.')
    if {t['area'] for t in train}&{t['area'] for t in validation}:
        raise ValueError('Entrenamiento y validación deben proceder de zonas distintas.')
    return train,validation


def run_process(arguments,job,progress):
    env = {**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1'}
    process = subprocess.Popen([sys.executable,*map(str,arguments)],cwd=ROOT,env=env,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    with job_lock:
        job['process'] = process
        if job['cancel'].is_set():
            process.terminate()
    for line in process.stdout:
        line = line.strip()
        with job_lock:
            job['log'] = (job['log']+[line])[-20:]
        try:
            event = json.loads(line)
            if 'epoch' in event:
                progress(completed=event['epoch'],message=f'Época {event["epoch"]}: IoU {event["val_iou"]:.3f}',metrics=event)
        except (ValueError,TypeError,KeyError):
            pass
    process.stdout.close()
    code = process.wait()
    with job_lock:
        job.pop('process',None)
    if code and not job['cancel'].is_set():
        raise ValueError('El proceso falló. '+ '\n'.join(job['log'][-6:]))


@blueprint.get('/api/datasets')
def list_datasets():
    items = []
    if DATASETS.exists():
        with data_lock:
            for path in sorted(DATASETS.iterdir(),key=lambda p:p.name,reverse=True):
                if not (path/'manifest.json').is_file():
                    continue
                meta = manifest(path)
                items.append({k:meta[k] for k in ('id','name','status','created_at')})
                items[-1].update(count=len(meta['tiles']),reviewed=sum(t['reviewed'] for t in meta['tiles']))
    with job_lock:
        running = [public_job(j) for j in jobs.values() if j['status']=='running']
    return jsonify(datasets=items,jobs=running)


@blueprint.post('/api/datasets/plan')
def dataset_plan():
    result = plan(request.get_json())
    return jsonify(tile_count=result['tile_count'],areas=result['areas'])


@blueprint.post('/api/datasets')
def create_dataset():
    config = request.get_json()
    plan(config)
    ensure_model()
    with extraction.model_lock:
        net,name = extraction.model,extraction.model_name
    if net is None:
        raise ValueError('Carga un modelo ONNX en el editor para generar las máscaras iniciales.')
    dataset_id = request.get_json().get('source','pnoa')+'-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    return jsonify(start_job('generate',dataset_id,lambda job,progress:
        {'dataset_id':generate(DATASETS/dataset_id,config,net,name,progress,job['cancel'].is_set)['id']})),202


@blueprint.get('/api/datasets/<dataset_id>')
def get_dataset(dataset_id):
    path = directory(dataset_id)
    with data_lock:
        meta = manifest(path)
    meta['directory'] = str(path.relative_to(ROOT))
    meta['runs'] = []
    if (path/'runs').exists():
        for report in sorted((path/'runs').glob('*/report.json')):
            info = json.loads(report.read_text(encoding='utf-8'))
            meta['runs'].append({**info,'id':report.parent.name,'has_onnx':(report.parent/'model.onnx').is_file() and (report.parent/'model.verification.json').is_file()})
    return jsonify(meta)


@blueprint.get('/api/datasets/<dataset_id>/tiles/<tile_id>/<kind>')
def tile_image(dataset_id,tile_id,kind):
    if kind not in ('image','mask'):
        raise ValueError('Tipo de imagen no válido.')
    path = directory(dataset_id)
    tile_record(path,tile_id)
    return send_file(path/('images' if kind=='image' else 'masks')/f'{tile_id}.png',max_age=0)


@blueprint.put('/api/datasets/<dataset_id>/tiles/<tile_id>')
def review_tile(dataset_id,tile_id):
    with data_lock:
        idle()
        path = directory(dataset_id)
        data = request.get_json()
        payload = data.get('mask','')
        if not isinstance(payload,str) or not payload.startswith('data:image/png;base64,') or len(payload)>4*1024**2:
            raise ValueError('Máscara PNG no válida.')
        raw = base64.b64decode(payload.split(',',1)[1],validate=True)
        decoded = cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_UNCHANGED)
        # Browser canvas exports RGBA; all colour channels must encode the same binary mask.
        if decoded is not None and decoded.ndim==3 and decoded.shape[2] in (3,4):
            if not np.array_equal(decoded[:,:,0],decoded[:,:,1]) or not np.array_equal(decoded[:,:,0],decoded[:,:,2]):
                raise ValueError('La máscara no es binaria.')
            decoded = decoded[:,:,0]
        if not isinstance(data.get('reviewed'),bool):
            raise ValueError('Indica si has revisado la máscara.')
        save_mask(path,tile_id,decoded,data['reviewed'],'gui-reviewed' if data['reviewed'] else 'gui-draft')
    return jsonify(saved=True)


@blueprint.get('/api/datasets/<dataset_id>/export/<kind>')
def export_dataset(dataset_id,kind):
    if kind not in ('images','cvat','bundle'):
        raise ValueError('Formato de exportación no válido.')
    path = directory(dataset_id)
    with data_lock:
        buffer = archive(path,kind)
    return send_file(buffer,mimetype='application/zip',as_attachment=True,download_name=f'{dataset_id}-{kind}.zip')


@blueprint.post('/api/datasets/<dataset_id>/import-cvat')
def import_masks(dataset_id):
    uploaded = request.files.get('file')
    if uploaded is None:
        raise ValueError('Selecciona el ZIP exportado por CVAT en formato Segmentation Mask.')
    with data_lock:
        idle()
        try:
            count = import_cvat(directory(dataset_id),uploaded.stream)
        except zipfile.BadZipFile as exc:
            raise ValueError('El archivo no es un ZIP válido.') from exc
    return jsonify(imported=count)


def editor_models():
    candidates = [*sorted((ROOT/'models').glob('*.onnx')), *sorted(ROOT.glob('*.onnx')), *sorted(DATASETS.glob('*/runs/*/model.onnx'))]
    models = []
    for path in candidates:
        if not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()) or (path.is_relative_to(DATASETS) and not path.with_suffix('.verification.json').is_file()):
            continue
        key = path.relative_to(ROOT).as_posix()
        title = 'Modelo predeterminado' if key=='models/model.onnx' else path.stem
        if path.is_relative_to(DATASETS):
            try:
                title = manifest(path.parents[2]).get('name',path.parents[2].name)
            except (OSError,ValueError):
                title = path.parents[2].name
        models.append({'id':key,'label':key,'title':title,'exported_at':path.stat().st_mtime,'run':path.parent.name if path.is_relative_to(DATASETS) else None})
    return models


@blueprint.get('/api/editor-models')
def list_editor_models():
    ensure_model()
    return jsonify(models=editor_models(),active=extraction.model_name)


@blueprint.post('/api/editor-models/activate')
def select_editor_model():
    model_id = request.get_json().get('model')
    if not isinstance(model_id,str) or model_id not in {item['id'] for item in editor_models()}:
        raise ValueError('Selecciona un modelo ONNX disponible en el proyecto.')
    net = cv2.dnn.readNetFromONNX(str(ROOT/model_id))
    extraction.probabilities(net,np.zeros((512,512,3),np.uint8))
    with extraction.model_lock:
        extraction.model,extraction.model_name = net,model_id
        import wololo
        wololo.cache.clear()
    return jsonify(model=model_id)


def training_checkpoints():
    candidates = [ROOT/'models'/'best.th', *sorted(ROOT.glob('*.th')), *sorted((ROOT/'models').glob('*.th')), *sorted(DATASETS.glob('*/runs/*/best.th'))]
    result = {}
    for path in candidates:
        if path.is_file() and path.resolve().is_relative_to(ROOT.resolve()):
            key = path.relative_to(ROOT).as_posix()
            result[key] = {'id':key,'path':key,'label':'Modelo predeterminado' if key=='models/best.th' else key}
    return list(result.values())


@blueprint.get('/api/training-checkpoints')
def list_training_checkpoints():
    return jsonify(checkpoints=training_checkpoints(),root=str(ROOT),default='models/best.th')


@blueprint.post('/api/datasets/<dataset_id>/train')
def train_dataset(dataset_id):
    path = directory(dataset_id)
    config = request.get_json()
    allow = config.get('allow_automatic',False)
    if not isinstance(allow,bool):
        raise ValueError('La opción de máscaras automáticas debe ser booleana.')
    train,validation = training_selection(manifest(path),allow)
    epochs = config.get('epochs',10)
    if isinstance(epochs,bool) or not isinstance(epochs,int) or not 1<=epochs<=100:
        raise ValueError('Selecciona entre 1 y 100 épocas.')
    device = config.get('device','auto')
    if device not in ('auto','cpu','cuda'):
        raise ValueError('Dispositivo no válido.')
    checkpoint_id = config.get('checkpoint','models/best.th')
    if not isinstance(checkpoint_id,str) or checkpoint_id not in {item['id'] for item in training_checkpoints()}:
        raise ValueError('Selecciona un archivo .th disponible en el selector de modelos de partida.')
    checkpoint = ROOT/checkpoint_id
    # Do not import heavy training dependencies into the web server.
    import importlib.util
    if any(importlib.util.find_spec(name) is None for name in ('torch','torchvision','onnx')):
        raise ValueError('Instala requirements-training.txt en el entorno del servidor para entrenar.')
    run_id = 'run-'+uuid.uuid4().hex[:12]
    output = path/'runs'/run_id
    def operation(job,progress):
        progress(total=epochs,message='Iniciando PyTorch…')
        args = [ROOT/'tools/train_segmentation.py','--dataset',path,'--checkpoint',checkpoint,'--output',output,'--epochs',epochs,'--device',device]
        if allow:
            args.append('--allow-automatic')
        run_process(args,job,progress)
        if not job['cancel'].is_set():
            progress(message='Exportando ONNX y verificando equivalencia con OpenCV…')
            run_process([ROOT/'tools/convert_dlinknet.py',output/'best.th','--output',output/'model.onnx','--image',path/'images'/f'{validation[0]["id"]}.png'],job,progress)
        return {'dataset_id':dataset_id,'run_id':run_id}
    return jsonify(start_job('train',dataset_id,operation)),202


@blueprint.post('/api/datasets/<dataset_id>/runs/<run_id>/activate')
def activate_model(dataset_id,run_id):
    output = directory(dataset_id)/'runs'/checked_id(run_id)
    if not (output/'model.onnx').is_file() or not (output/'model.verification.json').is_file():
        raise ValueError('El modelo todavía no está exportado y verificado.')
    net = cv2.dnn.readNetFromONNX(str(output/'model.onnx'))
    extraction.probabilities(net,np.zeros((512,512,3),np.uint8))
    with extraction.model_lock:
        extraction.model,extraction.model_name = net,f'{dataset_id}/{run_id}'
        import wololo
        wololo.cache.clear()
    return jsonify(model=extraction.model_name)


@blueprint.get('/api/dataset-jobs/<job_id>')
def get_job(job_id):
    with job_lock:
        if job_id not in jobs:
            raise ValueError('Trabajo no encontrado (se pierde el estado al reiniciar el servidor).')
        return jsonify(public_job(jobs[job_id]))


@blueprint.post('/api/dataset-jobs/<job_id>/cancel')
def cancel_job(job_id):
    with job_lock:
        job = jobs.get(job_id)
        if job is None:
            raise ValueError('Trabajo no encontrado.')
        job['cancel'].set()
        process = job.get('process')
        if process is not None and process.poll() is None:
            process.terminate()
    return jsonify(cancelling=True)


def stop_jobs():
    for job in list(jobs.values()):
        job['cancel'].set()
        process = job.get('process')
        if process is not None and process.poll() is None:
            process.terminate()


atexit.register(stop_jobs)


def register(app,model_loader):
    global ensure_model
    ensure_model = model_loader
    app.register_blueprint(blueprint)
