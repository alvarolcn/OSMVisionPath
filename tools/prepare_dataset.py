"""Download WGS84 bounding boxes as PNOA 512px tiles and create automatic mask drafts."""
import argparse
import json
from pathlib import Path
import sys

import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataset_manager import generate,archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True,help='JSON with name, gsd, threshold and areas [{bbox:[west,south,east,north],split:train|val|test}]')
    parser.add_argument('--model',type=Path,required=True,help='GUI-compatible ONNX')
    parser.add_argument('--output',type=Path,required=True,help='New output directory; existing datasets are never overwritten')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    net = cv2.dnn.readNetFromONNX(str(args.model))
    meta = generate(args.output,config,net,args.model.name,progress=lambda **values:print(json.dumps(values),flush=True))
    for kind in ('images','cvat'):
        (args.output/f'{kind}.zip').write_bytes(archive(args.output,kind).getvalue())
    print(json.dumps({'directory':str(args.output.resolve()),'tiles':len(meta['tiles']),'masks':'automatic drafts; review before training'}),flush=True)


if __name__=='__main__':
    main()
