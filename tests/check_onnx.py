"""Optional integration check; requires pip install onnx. Not a trained road model."""
import io
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import onnx
from onnx import helper, TensorProto, numpy_helper
from unittest.mock import patch
from app import app

weights = numpy_helper.from_array(np.full((1,3,1,1),1/3,np.float32),name='weights')
graph = helper.make_graph([helper.make_node('Conv',['rgb','weights'],['probability'],kernel_shape=[1,1])],
    'TEST_ONLY_brightness_not_road_segmentation',
    [helper.make_tensor_value_info('rgb',TensorProto.FLOAT,[1,3,512,512])],
    [helper.make_tensor_value_info('probability',TensorProto.FLOAT,[1,1,512,512])],[weights])
model = helper.make_model(graph,opset_imports=[helper.make_opsetid('',11)],ir_version=7)
onnx.checker.check_model(model)
image = np.full((1024,1024,3),(35,100,35),np.uint8)
cv2.polylines(image,[np.array([[100,800],[350,350],[850,200]],np.int32)],False,(180,185,195),35)
directory = Path(__file__).resolve().parents[1]/'.qa'
directory.mkdir(exist_ok=True)
(directory/'test-only.onnx').write_bytes(model.SerializeToString())
cv2.imwrite(str(directory/'sample.png'),image)
with app.test_client() as client:
    uploaded = client.post('/api/model',data={'model':(io.BytesIO(model.SerializeToString()),'test-only.onnx')})
    assert uploaded.status_code == 200,uploaded.json
    with patch('app.orthophoto',return_value=image):
        result = client.post('/api/extract',json={'bbox':[0,0,1000,1000],'mode':'segmentation','threshold':.5})
    assert result.status_code == 200,result.json
    assert result.json['paths'],'No centerlines from ONNX inference'
    print('ONNX OK: real upload, inference and centerlines. Model is a test fixture, not trained.')
