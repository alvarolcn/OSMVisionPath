import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch,Mock
import cv2
import numpy as np
import requests
import ortho_mosaic as mosaic

class MosaicTests(unittest.TestCase):
    def test_tiles_cache_retries_and_seam_coordinates(self):
        boxes=[]
        def response(url,params,**kwargs):
            boxes.append([float(v) for v in params['BBOX'].split(',')])
            image=np.full((params['HEIGHT'],params['WIDTH'],3),len(boxes),np.uint8)
            return Mock(content=cv2.imencode('.png',image)[1].tobytes())
        with tempfile.TemporaryDirectory() as directory,patch.object(mosaic,'ROOT',Path(directory)),patch.object(mosaic.requests,'get',side_effect=response) as get:
            image,count=mosaic.download((0,0,2300,1100),'pnoa',1,'fixture')
            self.assertIsInstance(image,np.memmap)
            self.assertEqual(image.shape,(1100,2300,3))
            self.assertEqual(count,6)
            self.assertEqual(get.call_count,6)
            self.assertEqual(boxes[0][2],boxes[1][0])
            self.assertEqual(boxes[0][1],boxes[3][3])
            self.assertEqual(int(image[0,1023,0]),1)
            self.assertEqual(int(image[0,1024,0]),2)
            again,_=mosaic.download((0,0,2300,1100),'pnoa',1,'fixture')
            self.assertEqual(get.call_count,6)
            self.assertTrue(mosaic.progress['fixture']['cached'])
            np.testing.assert_array_equal(image,again)
            del image,again
            mosaic.download((0,0,2300,1100),'itacyl',1,'other')
            self.assertEqual(get.call_count,12)
    def test_retry_and_size_guard(self):
        good=Mock(content=cv2.imencode('.png',np.zeros((100,100,3),np.uint8))[1].tobytes())
        with tempfile.TemporaryDirectory() as directory,patch.object(mosaic,'ROOT',Path(directory)),patch.object(mosaic.requests,'get',side_effect=[requests.Timeout(),requests.Timeout(),good]) as get:
            image,_=mosaic.download((0,0,100,100),'pnoa',1,'retry')
            self.assertEqual(get.call_count,3)
            del image
            with patch.object(mosaic,'MAX_PIXELS',32_000_000),self.assertRaises(ValueError): mosaic.download((0,0,50000,50000),'pnoa',.2)

    def test_explicit_limit_checked_before_allocation(self):
        with patch.object(mosaic,'MAX_PIXELS',None),patch.object(mosaic.requests,'get') as get:
            with self.assertRaises(ValueError): mosaic.download((0,0,1000,1000),'pnoa',1,max_pixels=500_000)
            get.assert_not_called()
