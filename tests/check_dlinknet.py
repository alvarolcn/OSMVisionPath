"""Online integration check for the user's converted D-LinkNet34; requires torch."""
import io
import sys
import json
import math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import cv2
import numpy as np
import torch
from dlinknet34 import DinkNet34, GuiCompatibleDLinkNet
from app import app,orthophoto,project

root = Path(__file__).resolve().parents[1]
(root/'.qa').mkdir(exist_ok=True)
torch.set_num_threads(4)
network = DinkNet34()
checkpoint = torch.load(root/'log01_dink34.th',map_location='cpu',weights_only=True)
state = {k.removeprefix('module.'):v for k,v in checkpoint.items()}
for k,v in network.state_dict().items():
    if k.endswith('.num_batches_tracked') and k not in state: state[k] = v
network.load_state_dict(state,strict=True)
wrapped = GuiCompatibleDLinkNet(network).eval()
x,y = project(-4.1,40.42)
half = 750 / math.cos(math.radians(40.42)) / 2
bbox = (x-half,y-half,x+half,y+half)
image = orthophoto(bbox)
cv2.imwrite(str(root/'.qa/dlinknet-pnoa.png'),image)
blob = cv2.dnn.blobFromImage(image,1/255.0,(512,512),swapRB=True)
with torch.inference_mode(): expected = wrapped(torch.from_numpy(blob)).numpy()
net = cv2.dnn.readNetFromONNX(str(root/'models/dlinknet34.onnx'))
net.setInput(blob)
actual = net.forward()
np.testing.assert_allclose(actual,expected,rtol=1e-3,atol=1e-4)
print('Real PNOA parity max error:',float(np.abs(actual-expected).max()),flush=True)
# Real multipart upload verifies that the GUI can load a model larger than 64 MB.
with app.test_client() as client:
    with (root/'models/dlinknet34.onnx').open('rb') as model_file:
        uploaded = client.post('/api/model',data={'model':(io.BytesIO(model_file.read()),'dlinknet34.onnx')})
    assert uploaded.status_code == 200,uploaded.json
    result = client.post('/api/extract',json={'bbox':list(bbox),'mode':'segmentation','threshold':.5})
    assert result.status_code == 200,result.json
    assert client.get('/api/health').json['model'] == 'dlinknet34.onnx'
    print('D-LinkNet real upload and PNOA segmentation: HTTP 200; candidates:',len(result.json['paths']),flush=True)
    report = {'max_abs_error':float(np.abs(actual-expected).max()),'mean_abs_error':float(np.abs(actual-expected).mean()),
        'bbox':bbox,'candidates':len(result.json['paths']),'note':'Inference verification only, not an accuracy assessment.'}
    (root/'.qa/dlinknet-pnoa-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
