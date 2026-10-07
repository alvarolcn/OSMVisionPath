"""Isolated browser server: synthetic tiles and fake training jobs, never the main model."""
import json
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import app as server
import dataset_manager as dm
import extraction

dm.DATASETS = dm.ROOT/'.qa'/('gui-datasets-'+uuid.uuid4().hex[:8])
server.local_model_checked = True
extraction.model = cv2.dnn.readNetFromONNX(str(dm.ROOT/'.qa/test-only.onnx'))
extraction.model_name = 'TEST_ONLY_brightness.onnx'
image = np.full((512,512,3),(35,100,35),np.uint8)
image[240:272] = (200,200,200)
dm.download_tile = lambda bbox:image.copy()


def fixture_process(arguments,job,progress):
    arguments = list(map(str,arguments))
    output = Path(arguments[arguments.index('--output')+1])
    if arguments[0].endswith('train_segmentation.py'):
        output.mkdir(parents=True)
        (output/'report.json').write_text(json.dumps({'best_iou':.5,'best_epoch':1,'epochs':1,'label_source':'reviewed','device':'fixture','history':[]}),encoding='utf-8')
        progress(completed=1,metrics={'epoch':1,'val_iou':.5},message='Browser fixture: no real training')
    else:
        os.link(dm.ROOT/'.qa/test-only.onnx',output)
        output.with_suffix('.verification.json').write_text('{"test_fixture":true}',encoding='utf-8')
    job['log'].append('Synthetic GUI test fixture; CPU training verified separately.')


dm.run_process = fixture_process
server.app.run(host='127.0.0.1',port=5002,debug=False)
