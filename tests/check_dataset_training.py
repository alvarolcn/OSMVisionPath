"""Optional end-to-end CPU smoke test; synthetic labels are not a useful road model."""
import json
from pathlib import Path
import subprocess
import sys
import uuid
from unittest.mock import patch

import cv2
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import dataset_manager as dm
import extraction
from test_datasets import specification


work = ROOT/'.qa'/('training-smoke-'+uuid.uuid4().hex[:8])
image = np.full((512,512,3),(35,100,35),np.uint8)
image[240:272] = (200,200,200)
with patch.object(dm,'download_tile',return_value=image),patch.object(extraction,'probabilities',side_effect=lambda _,im:im[:,:,0]/255.):
    dm.generate(work/'dataset',specification(),object(),'synthetic-fixture')
mask = np.zeros((512,512),np.uint8)
mask[240:272] = 255
for tile in dm.manifest(work/'dataset')['tiles']:
    dm.save_mask(work/'dataset',tile['id'],mask,True,'synthetic-reviewed-fixture')
commands = [
    [ROOT/'tools/train_segmentation.py','--dataset',work/'dataset','--checkpoint',ROOT/'log01_dink34.th','--output',work/'run','--epochs','1','--device','cpu'],
    [ROOT/'tools/convert_dlinknet.py',work/'run/best.th','--output',work/'run/model.onnx','--image',work/'dataset/images/a00_r000_c000.png']]
for command in commands:
    subprocess.run([sys.executable,*map(str,command)],cwd=ROOT,check=True)
report = json.loads((work/'run/report.json').read_text(encoding='utf-8'))
assert report['label_source']=='reviewed' and report['train_tiles']==report['val_tiles']==1
net = cv2.dnn.readNetFromONNX(str(work/'run/model.onnx'))
output = extraction.probabilities(net,image)
assert output.shape==(512,512) and np.isfinite(output).all()
(ROOT/'.qa/latest-training-smoke.json').write_text(json.dumps({'directory':str(work),'report':report}),encoding='utf-8')
print(json.dumps({'result':'CPU fine-tuning, best checkpoint, ONNX conversion and OpenCV parity OK','directory':str(work)}),flush=True)
