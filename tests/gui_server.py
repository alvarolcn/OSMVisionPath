"""Isolated GUI test server with a synthetic image; never use as the PNOA server."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import app
image = cv2.imread(str(Path(__file__).resolve().parents[1]/'.qa/sample.png'))
if image is None:
    raise SystemExit('Run tests/check_onnx.py first')
app.orthophoto = lambda bbox: image
app.local_model_checked = True  # Isolate test uploads from the real local model.
app.app.run(host='127.0.0.1',port=5001)
