"""Convert user-supplied D-LinkNet34 tensor weights and verify OpenCV parity."""
import argparse
import hashlib
import json
from pathlib import Path
import warnings

import cv2
import numpy as np
import onnx
import torch
from dlinknet34 import DinkNet34, GuiCompatibleDLinkNet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint',type=Path)
    parser.add_argument('--output',type=Path,default=Path('models/dlinknet34.onnx'))
    parser.add_argument('--image',type=Path,help='Optional local orthophoto for numerical verification')
    args = parser.parse_args()
    if not args.checkpoint.is_file():
        parser.error(f'Checkpoint not found: {args.checkpoint}')
    if args.output.exists() or args.output.with_suffix('.verification.json').exists():
        parser.error(f'Output already exists: {args.output}; select a new --output path')
    torch.set_num_threads(4)
    print('Loading checkpoint with weights_only=True on CPU…',flush=True)
    # Never fall back to unpickling arbitrary Python objects.
    checkpoint = torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    if isinstance(checkpoint,dict) and 'state_dict' in checkpoint:
        checkpoint = checkpoint['state_dict']
    if not isinstance(checkpoint,dict) or not all(isinstance(k,str) and isinstance(v,torch.Tensor) for k,v in checkpoint.items()):
        raise ValueError('Expected a tensor state_dict, not a serialized Python model.')
    state = {key.removeprefix('module.'):value for key,value in checkpoint.items()}
    network = DinkNet34()
    # Old PyTorch checkpoints predate num_batches_tracked; these buffers do not affect eval.
    for key,value in network.state_dict().items():
        if key.endswith('.num_batches_tracked') and key not in state:
            state[key] = value
    network.load_state_dict(state,strict=True)
    wrapped = GuiCompatibleDLinkNet(network).eval()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    example = torch.zeros(1,3,512,512)
    print('Exporting ONNX opset 13, fixed RGB 512×512…',flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',DeprecationWarning)
        torch.onnx.export(wrapped,example,str(args.output),opset_version=13,
            input_names=['rgb'],output_names=['road_probability'],dynamo=False)
    onnx.checker.check_model(str(args.output))
    net = cv2.dnn.readNetFromONNX(str(args.output))
    rng = np.random.default_rng(42)
    images = [rng.integers(0,256,(512,512,3),dtype=np.uint8),np.zeros((512,512,3),np.uint8)]
    if args.image:
        image = cv2.imread(str(args.image))
        if image is None:
            raise ValueError(f'Cannot read image: {args.image}')
        images.append(image)
    checks = []
    for i,image in enumerate(images):
        print(f'Checking PyTorch/OpenCV parity ({i+1}/{len(images)})…',flush=True)
        blob = cv2.dnn.blobFromImage(image,1/255.0,(512,512),swapRB=True)
        with torch.inference_mode():
            expected = wrapped(torch.from_numpy(blob)).numpy()
        net.setInput(blob)
        actual = net.forward()
        if actual.shape != (1,1,512,512) or not np.isfinite(actual).all() or actual.min()<0 or actual.max()>1:
            raise ValueError('Invalid probability output from OpenCV')
        difference = np.abs(expected-actual)
        np.testing.assert_allclose(actual,expected,rtol=1e-3,atol=1e-4)
        checks.append({'image':i,'max_abs_error':float(difference.max()),'mean_abs_error':float(difference.mean())})
    with args.checkpoint.open('rb') as checkpoint_file:
        checkpoint_sha256 = hashlib.file_digest(checkpoint_file,'sha256').hexdigest()
    report = {'checkpoint':args.checkpoint.name,'checkpoint_sha256':checkpoint_sha256,
        'onnx':args.output.name,'opencv':cv2.__version__,'torch':torch.__version__,
        'input':'RGB float32 [0,1], NCHW 1x3x512x512',
        'embedded_preprocessing':'RGB to BGR; multiply by 3.2 and subtract 1.6',
        'output':'road probability 1x1x512x512','verification':checks,
        'limitations':'single-pass resized image; no original 8-way test-time augmentation; no PNOA accuracy claim'}
    args.output.with_suffix('.verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'OK: {args.output.resolve()} ({args.output.stat().st_size/1024**2:.1f} MiB)',flush=True)


if __name__ == '__main__':
    main()
