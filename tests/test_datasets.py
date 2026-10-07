import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

import cv2
import numpy as np
import dataset_manager as dm
from app import app
import extraction


def specification():
    return {'name':'Prueba PNOA','gsd':.2,'threshold':.5,'areas':[
        {'bbox':[-3.7112,41.9917,-3.7111,41.9918],'split':'train'},
        {'bbox':[-3.68,41.9917,-3.6799,41.9918],'split':'val'}]}


class DatasetTests(unittest.TestCase):
    def setUp(self):
        qa = Path(__file__).resolve().parents[1]/'.qa'
        qa.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=qa)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patcher = patch.object(dm,'DATASETS',self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.image = np.zeros((512,512,3),np.uint8)
        self.image[240:272] = 220
        self.client = app.test_client()

    def generate(self):
        path = self.root/'sample'
        with patch.object(dm,'download_tile',return_value=self.image),patch.object(extraction,'probabilities',side_effect=lambda _,image:image[:,:,0]/255.):
            dm.generate(path,specification(),object(),'fixture.onnx')
        return path

    def test_training_checkpoint_catalog_and_selection(self):
        path = self.generate()
        weights = path/'runs'/'run-example'/'best.th'
        weights.parent.mkdir(parents=True)
        weights.write_bytes(b'fixture')
        checkpoint_id = weights.relative_to(dm.ROOT).as_posix()
        response = self.client.get('/api/training-checkpoints')
        self.assertIn(checkpoint_id,[item['id'] for item in response.json['checkpoints']])
        with patch.object(dm,'start_job',return_value={'id':'fixture'}) as start:
            response = self.client.post('/api/datasets/sample/train',json={'allow_automatic':True,'checkpoint':checkpoint_id})
            self.assertEqual(response.status_code,202)
            with patch.object(dm,'run_process') as run:
                start.call_args.args[2]({'cancel':threading.Event()},lambda **kwargs:None)
                command = run.call_args_list[0].args[0]
                self.assertEqual(command[command.index('--checkpoint')+1],weights)
        response = self.client.post('/api/datasets/sample/train',json={'allow_automatic':True,'checkpoint':'../outside.th'})
        self.assertEqual(response.status_code,400)

    def test_itacyl_source_is_used_and_recorded(self):
        config = {**specification(),'source':'itacyl'}
        self.assertEqual(dm.plan(config)['source_id'],'itacyl')
        with self.assertRaises(ValueError):
            dm.plan({**config,'source':'unknown'})
        path = self.root/'itacyl-sample'
        with patch.object(dm,'download_tile',return_value=self.image) as download,patch.object(extraction,'probabilities',return_value=np.zeros((512,512))):
            dm.generate(path,config,object(),'fixture.onnx')
        self.assertTrue(all(call.args[1]=='itacyl' for call in download.call_args_list))
        self.assertEqual(dm.manifest(path)['source'],'ITACyL Castilla y León')

    def test_grid_native_size_and_split_separation(self):
        result = dm.plan(specification())
        self.assertEqual(result['tile_count'],2)
        bounds = result['tiles'][0]['bbox_3857']
        latitude = sum(specification()['areas'][0]['bbox'][i] for i in (1,3))/2
        import math
        self.assertAlmostEqual((bounds[2]-bounds[0])*math.cos(math.radians(latitude))/512,.2)
        invalid = specification()
        invalid['areas'][1]['bbox'] = invalid['areas'][0]['bbox']
        with self.assertRaisesRegex(ValueError,'solapan'):
            dm.plan(invalid)
        with self.assertRaises(ValueError):
            dm.plan({'areas':[{'bbox':[-4,40,-3,41]}],'gsd':.1})

    def test_generation_archive_and_cvat_roundtrip(self):
        path = self.generate()
        meta = dm.manifest(path)
        self.assertEqual(meta['status'],'ready')
        self.assertEqual(len(meta['tiles']),2)
        tile_id = meta['tiles'][0]['id']
        mask = cv2.imread(str(path/'masks'/f'{tile_id}.png'),0)
        self.assertEqual(mask.shape,(512,512))
        self.assertEqual(set(np.unique(mask)),{0,255})
        with zipfile.ZipFile(dm.archive(path,'cvat')) as archive:
            raw = archive.read(f'SegmentationClass/{tile_id}.png')
            self.assertEqual(cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_UNCHANGED).shape,(512,512,3))
        self.assertEqual(dm.import_cvat(path,dm.archive(path,'cvat')),2)
        self.assertTrue(all(t['reviewed'] for t in dm.manifest(path)['tiles']))
        train,val = dm.training_selection(dm.manifest(path),False)
        self.assertEqual(len(train),1)
        self.assertEqual(len(val),1)
        with zipfile.ZipFile(dm.archive(path,'images')) as archive:
            self.assertIn(f'{tile_id}.png',archive.namelist())
        with zipfile.ZipFile(dm.archive(path,'bundle')) as archive:
            self.assertIn('manifest.json',archive.namelist())
            self.assertIn(f'masks/{tile_id}.png',archive.namelist())

    def test_indexed_cvat_mask_and_unknown_colours_rejected(self):
        path = self.generate()
        tile_id = dm.manifest(path)['tiles'][0]['id']
        buffer = io.BytesIO()
        image = np.zeros((512,512),np.uint8)
        image[250:260] = 1
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('labelmap.txt','background:0,0,0::\nroad:128,0,0::\n')
            archive.writestr(f'SegmentationClass/{tile_id}.png',cv2.imencode('.png',image)[1].tobytes())
        buffer.seek(0)
        self.assertEqual(dm.import_cvat(path,buffer),1)
        imported = cv2.imread(str(path/'masks'/f'{tile_id}.png'),0)
        self.assertTrue(np.array_equal(imported,np.uint8(image>0)*255))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr(f'SegmentationClass/{tile_id}.png',cv2.imencode('.png',np.full((512,512,3),42,np.uint8))[1].tobytes())
        buffer.seek(0)
        with self.assertRaisesRegex(ValueError,'colores'):
            dm.import_cvat(path,buffer)

    def test_review_api_and_training_requires_review(self):
        path = self.generate()
        tile_id = dm.manifest(path)['tiles'][0]['id']
        with self.assertRaises(ValueError):
            dm.training_selection(dm.manifest(path),False)
        self.assertEqual(len(dm.training_selection(dm.manifest(path),True)[0]),1)
        mask = np.zeros((512,512),np.uint8)
        payload = 'data:image/png;base64,'+base64.b64encode(cv2.imencode('.png',mask)[1]).decode()
        response = self.client.put(f'/api/datasets/sample/tiles/{tile_id}',json={'mask':payload,'reviewed':True})
        self.assertEqual(response.status_code,200)
        self.assertTrue(dm.manifest(path)['tiles'][0]['reviewed'])
        self.assertEqual(self.client.get('/api/datasets/sample').status_code,200)
        self.assertEqual(self.client.get('/api/datasets/sample/export/cvat').status_code,200)
        self.assertEqual(self.client.get('/api/datasets/sample/tiles/unknown/image').status_code,400)
        with self.assertRaises(ValueError):
            dm.checked_id('../elsewhere')

    def test_background_generation_job(self):
        with patch.dict(dm.jobs,{},clear=True),patch.object(dm,'ensure_model',lambda:None),patch.object(extraction,'model',object()),patch.object(extraction,'model_name','fixture.onnx'),patch.object(dm,'download_tile',return_value=self.image),patch.object(extraction,'probabilities',side_effect=lambda _,image:image[:,:,0]/255.):
            response = self.client.post('/api/datasets',json=specification())
            self.assertEqual(response.status_code,202)
            job_id = response.json['id']
            deadline = time.monotonic()+5
            while time.monotonic()<deadline:
                job = self.client.get(f'/api/dataset-jobs/{job_id}').json
                if job['status']!='running':
                    break
                time.sleep(.01)
            self.assertEqual(job['status'],'done',job)
            dataset = self.client.get(f'/api/datasets/{job["dataset_id"]}').json
            self.assertEqual(len(dataset['tiles']),2)
            self.assertNotIn('cancel',job)

    def test_cancel_preserves_partial_dataset_and_stops_inference(self):
        started,release = threading.Event(),threading.Event()
        def download(bbox):
            started.set()
            release.wait(3)
            return self.image
        with patch.dict(dm.jobs,{},clear=True),patch.object(dm,'ensure_model',lambda:None),patch.object(extraction,'model',object()),patch.object(dm,'download_tile',side_effect=download),patch.object(extraction,'probabilities') as inference:
            response = self.client.post('/api/datasets',json=specification())
            job_id = response.json['id']
            self.assertTrue(started.wait(3))
            self.assertEqual(self.client.post('/api/datasets',json=specification()).status_code,400)
            self.assertEqual(self.client.post(f'/api/dataset-jobs/{job_id}/cancel').status_code,200)
            release.set()
            deadline = time.monotonic()+3
            while time.monotonic()<deadline:
                job = self.client.get(f'/api/dataset-jobs/{job_id}').json
                if job['status']!='running':
                    break
                time.sleep(.01)
            self.assertEqual(job['status'],'cancelled')
            meta = self.client.get(f'/api/datasets/{job["dataset_id"]}').json
            self.assertEqual(meta['status'],'cancelled')
            self.assertEqual(meta['tiles'],[])
            inference.assert_not_called()

    def test_training_process_can_be_cancelled(self):
        with patch.dict(dm.jobs,{},clear=True):
            job = dm.start_job('train','fixture',lambda state,progress:
                dm.run_process(['-c','import time; print("ready",flush=True); time.sleep(30)'],state,progress))
            job_id = job['id']
            deadline = time.monotonic()+3
            while time.monotonic()<deadline and 'process' not in dm.jobs[job_id]:
                time.sleep(.01)
            self.assertIn('process',dm.jobs[job_id])
            self.assertEqual(self.client.post(f'/api/dataset-jobs/{job_id}/cancel').status_code,200)
            deadline = time.monotonic()+3
            while time.monotonic()<deadline:
                result = self.client.get(f'/api/dataset-jobs/{job_id}').json
                if result['status']!='running':
                    break
                time.sleep(.01)
            self.assertEqual(result['status'],'cancelled')
            self.assertNotIn('process',result)


if __name__=='__main__':
    unittest.main()
