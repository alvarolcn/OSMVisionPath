import io
import unittest
from unittest.mock import patch
import cv2
import numpy as np
import extraction
from app import app


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        preload = patch('app.ensure_local_model')
        preload.start()
        self.addCleanup(preload.stop)
        self.image = np.full((1024,1024,3),(35,100,35),np.uint8)
        cv2.polylines(self.image,[np.array([[100,800],[350,350],[850,200]],np.int32)],False,(180,185,195),35)
        self.client = app.test_client()

    def test_automatic_without_points(self):
        mask = extraction.candidate_mask(self.image,'automatic',.5)
        lines = extraction.centerlines(mask)
        self.assertTrue(lines)
        self.assertTrue(any(any(np.linalg.norm(np.array(p)-[350/1024,350/1024])<.08 for p in line) for line in lines))
        for line in lines:
            self.assertGreaterEqual(len(line),2)
            self.assertTrue(all(0<=x<=1 and 0<=y<=1 for x,y in line))

    def test_empty_and_branching_masks(self):
        self.assertEqual(extraction.centerlines(np.zeros((100,100),np.uint8)),[])
        mask = np.zeros((100,100),np.uint8)
        cv2.line(mask,(10,50),(90,50),255,7)
        cv2.line(mask,(50,50),(50,10),255,7)
        self.assertGreaterEqual(len(extraction.centerlines(mask)),3)

    @patch('app.orthophoto')
    def test_api_export_and_validation(self,ortho):
        ortho.return_value = self.image
        data = {'bbox':[0,0,1000,1000],'mode':'automatic','threshold':.5}
        result = self.client.post('/api/extract',json=data)
        self.assertEqual(result.status_code,200)
        self.assertGreater(len(result.json['paths']),0)
        self.assertEqual(len(result.json['paths']),len(result.json['geojson']['features']))
        data['mode']='unknown'
        self.assertEqual(self.client.post('/api/extract',json=data).status_code,400)
        data['mode']='segmentation'
        with patch.object(extraction,'model',None):
            response = self.client.post('/api/extract',json=data)
            self.assertEqual(response.status_code,400)
            self.assertIn('ONNX',response.json['error'])

    def test_incompatible_model_does_not_replace_existing(self):
        original = extraction.model
        response = self.client.post('/api/model',data={'model':(io.BytesIO(b'not onnx'),'broken.onnx')})
        self.assertEqual(response.status_code,400)
        self.assertIs(extraction.model,original)

    def test_probability_contract_and_preprocessing(self):
        class Net:
            def setInput(self,blob): self.blob=blob
            def forward(self): return np.full((1,1,64,64),.8,np.float32)
        net=Net()
        output=extraction.probabilities(net,self.image)
        self.assertEqual(net.blob.shape,(1,3,512,512))
        self.assertEqual(output.shape,(512,512))
        self.assertLessEqual(net.blob.max(),1)
        np.testing.assert_allclose(net.blob[0,:,0,0],np.array([35,100,35])/255,atol=1e-6)
        with patch.object(net,'forward',return_value=np.ones((1,2,64,64))):
            with self.assertRaises(ValueError): extraction.probabilities(net,self.image)
        with patch.object(net,'forward',return_value=np.full((1,1,64,64),2)):
            with self.assertRaises(ValueError): extraction.probabilities(net,self.image)


    def test_tiling_preserves_raster_and_coordinates(self):
        class IdentityChannel:
            def setInput(self,blob): self.blob=blob
            def forward(self): return self.blob[:,0:1]
        y,x = np.mgrid[:700,:900]
        image = np.stack([x%256,y%256,(x+y)%256],axis=-1).astype(np.uint8)
        actual,tiles = extraction.tiled_probabilities(IdentityChannel(),image)
        self.assertEqual(actual.shape,(700,900))
        self.assertGreater(tiles,1)
        np.testing.assert_allclose(actual,image[:,:,2]/255,atol=1e-6)
        tiny = image[:200,:300]
        actual,tiles = extraction.tiled_probabilities(IdentityChannel(),tiny)
        self.assertEqual(tiles,1)
        np.testing.assert_allclose(actual,tiny[:,:,2]/255,atol=1e-6)


if __name__ == '__main__':
    unittest.main()
