"""Fine-tune D-LinkNet34 on reviewed native PNOA tiles, with area-separated validation."""
import argparse
import json
from pathlib import Path
import random
import sys

import cv2
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader,Dataset
from dlinknet34 import DinkNet34,GuiCompatibleDLinkNet

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataset_manager import training_selection,write_json,plan


class Tiles(Dataset):
    def __init__(self,path,records,augment=False):
        self.path,self.records,self.augment = path,records,augment

    def __len__(self):
        return len(self.records)

    def __getitem__(self,index):
        tile_id = self.records[index]['id']
        image = cv2.imread(str(self.path/'images'/f'{tile_id}.png'))
        mask = cv2.imread(str(self.path/'masks'/f'{tile_id}.png'),cv2.IMREAD_GRAYSCALE)
        if image is None or image.shape!=(512,512,3) or mask is None or mask.shape!=(512,512) or not set(np.unique(mask)).issubset({0,255}):
            raise ValueError(f'Imagen o máscara no válida: {tile_id}')
        rgb = torch.from_numpy(image[:,:,::-1].transpose(2,0,1).copy()).float()/255.
        target = torch.from_numpy((mask>0).astype(np.float32)[None])
        if self.augment:
            for axis in (1,2):
                if random.random()<.5:
                    rgb,target = rgb.flip(axis),target.flip(axis)
            rotations = random.randrange(4)
            rgb,target = torch.rot90(rgb,rotations,(1,2)),torch.rot90(target,rotations,(1,2))
        return rgb,target


def load_checkpoint(network,path):
    state = torch.load(path,map_location='cpu',weights_only=True)
    if isinstance(state,dict) and 'state_dict' in state:
        state = state['state_dict']
    if not isinstance(state,dict) or not all(isinstance(k,str) and isinstance(v,torch.Tensor) for k,v in state.items()):
        raise ValueError('El checkpoint debe contener únicamente un state_dict de tensores.')
    state = {k.removeprefix('module.'):v for k,v in state.items()}
    for key,value in network.state_dict().items():
        if key.endswith('.num_batches_tracked') and key not in state:
            state[key] = value
    network.load_state_dict(state,strict=True)


def segmentation_loss(prediction,target):
    bce = nn.functional.binary_cross_entropy(prediction.clamp(1e-6,1-1e-6),target)
    intersection = (prediction*target).sum((1,2,3))
    dice = (2*intersection+1)/(prediction.sum((1,2,3))+target.sum((1,2,3))+1)
    return bce+(1-dice).mean()


def evaluate(model,loader,device):
    model.eval()
    intersection,union,positive,predicted,loss,total = 0,0,0,0,0.,0
    with torch.inference_mode():
        for rgb,target in loader:
            rgb,target = rgb.to(device),target.to(device)
            output = model(rgb)
            loss += float(segmentation_loss(output,target))*len(rgb)
            total += len(rgb)
            binary,truth = output>=.5,target>0
            intersection += int((binary&truth).sum())
            union += int((binary|truth).sum())
            positive += int(truth.sum())
            predicted += int(binary.sum())
    return {'val_loss':loss/total,'val_iou':intersection/union if union else 1.,
            'val_dice':2*intersection/(positive+predicted) if positive+predicted else 1.}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--epochs',type=int,default=10)
    parser.add_argument('--batch-size',type=int,default=1)
    parser.add_argument('--learning-rate',type=float,default=1e-4)
    parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    parser.add_argument('--allow-automatic',action='store_true',help='Experimental pseudo-label training; validation is not ground-truth accuracy')
    args = parser.parse_args()
    if not 1<=args.epochs<=100 or not 1<=args.batch_size<=8 or not 0<args.learning_rate<=.01:
        parser.error('Invalid epochs, batch size or learning rate')
    meta = json.loads((args.dataset/'manifest.json').read_text(encoding='utf-8'))
    # Revalidate footprints even for CLI datasets; never randomly split neighbouring tiles.
    plan({'gsd':meta['gsd'],'areas':[{'bbox':a['bbox'],'split':a['split']} for a in meta['areas']]})
    train,validation = training_selection(meta,args.allow_automatic)
    device = 'cuda' if args.device=='auto' and torch.cuda.is_available() else ('cpu' if args.device=='auto' else args.device)
    if device=='cuda' and not torch.cuda.is_available():
        parser.error('CUDA is not available in this Python environment; select CPU or install a compatible GPU build')
    torch.set_num_threads(4)
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    network = DinkNet34()
    load_checkpoint(network,args.checkpoint)
    model = GuiCompatibleDLinkNet(network).to(device)
    optimizer = torch.optim.Adam(model.parameters(),lr=args.learning_rate)
    train_loader = DataLoader(Tiles(args.dataset,train,True),batch_size=args.batch_size,shuffle=True,num_workers=0)
    val_loader = DataLoader(Tiles(args.dataset,validation),batch_size=1,num_workers=0)
    args.output.mkdir(parents=True,exist_ok=False)
    report = {'dataset':meta['id'],'device':device,'train_tiles':len(train),'val_tiles':len(validation),'initial_checkpoint':str(args.checkpoint.resolve()),
              'label_source':'pseudo-labels-included' if any(not t['reviewed'] for t in train+validation) else 'reviewed',
              'test_set_used':False,'epochs':args.epochs,'history':[],'best_iou':-1.}
    print(json.dumps({'message':'Training started','device':device,'train_tiles':len(train),'val_tiles':len(validation),'label_source':report['label_source']}),flush=True)
    for epoch in range(1,args.epochs+1):
        model.train()
        running,total = 0.,0
        for rgb,target in train_loader:
            rgb,target = rgb.to(device),target.to(device)
            optimizer.zero_grad(set_to_none=True)
            output = model(rgb)
            loss = segmentation_loss(output,target)
            if not torch.isfinite(loss):
                raise ValueError('Training loss is not finite')
            loss.backward()
            optimizer.step()
            running += float(loss.detach())*len(rgb)
            total += len(rgb)
        metrics = {'epoch':epoch,'train_loss':running/total,**evaluate(model,val_loader,device)}
        if metrics['val_iou']>report['best_iou']:
            report['best_iou'] = metrics['val_iou']
            report['best_epoch'] = epoch
            torch.save({'state_dict':{k:v.detach().cpu() for k,v in network.state_dict().items()},'epoch':epoch,'val_iou':metrics['val_iou']},args.output/'best.th')
        report['history'].append(metrics)
        write_json(args.output/'report.json',report)
        print(json.dumps(metrics),flush=True)
    print(json.dumps({'message':'Training completed','checkpoint':str(args.output/'best.th')}),flush=True)


if __name__=='__main__':
    main()
