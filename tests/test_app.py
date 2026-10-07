import unittest
from unittest.mock import patch
import cv2
import numpy as np
import requests
from app import app, detect, project, unproject


class TraceTests(unittest.TestCase):
    def setUp(self):
        preload = patch('app.ensure_local_model')
        preload.start()
        self.addCleanup(preload.stop)
        self.client = app.test_client()
        self.image = np.full((1024,1024,3), (35,100,35), np.uint8)
        cv2.polylines(self.image, [np.array([[100,800],[350,350],[850,200]],np.int32)], False, (180,185,195), 45)

    def test_curve_follows_road(self):
        points = [[100/1024,800/1024],[850/1024,200/1024]]
        path = detect(self.image, points, 15)
        self.assertEqual(path[0],points[0])
        self.assertEqual(path[-1],points[-1])
        self.assertTrue(any(np.linalg.norm(np.array(p)-np.array([350/1024,350/1024])) < .06 for p in path))
        for x,y in path:
            color = self.image[min(1023,int(y*1024)),min(1023,int(x*1024))]
            self.assertGreater(int(color[0]),100)

    def test_projection_roundtrip(self):
        np.testing.assert_allclose(unproject(*project(-4.1,40.42)),[-4.1,40.42],atol=1e-8)

    @patch('app.orthophoto')
    def test_blocked_network_explained(self, ortho):
        ortho.side_effect = requests.ConnectionError('[WinError 10013] socket blocked')
        response = self.client.post('/api/ortho',json={'lon':-4.1,'lat':40.42,'span':750})
        self.assertEqual(response.status_code,502)
        self.assertIn('WinError 10013',response.json['error'])
        self.assertIn('terminal local',response.json['error'])

    def test_invalid_requests(self):
        self.assertEqual(self.client.post('/api/ortho',json={'lon':0,'lat':0,'span':750}).status_code,400)
        self.assertEqual(self.client.post('/api/detect',json={'bbox':[0,0,1000,1000],'points':[[2,0],[0,1]]}).status_code,400)
        self.assertEqual(self.client.get('/missing').status_code,404)

    @patch('app.orthophoto')
    def test_endpoints(self, ortho):
        ortho.return_value = self.image
        with self.client.get('/') as page:
            self.assertEqual(page.status_code,200)
        self.assertTrue(self.client.get('/api/health').json['opencv'].startswith('5.'))
        loaded = self.client.post('/api/ortho',json={'lon':-4.1,'lat':40.42,'span':750})
        self.assertEqual(loaded.status_code,200)
        self.assertEqual(loaded.json['width'],self.image.shape[1])
        self.assertAlmostEqual(loaded.json['meters_per_pixel'],750/1024,places=4)
        traced = self.client.post('/api/detect',json={'bbox':loaded.json['bbox'],'points':[[100/1024,800/1024],[850/1024,200/1024]],'sensitivity':15})
        self.assertEqual(traced.status_code,200)
        self.assertGreater(traced.json['length'],0)
        self.assertEqual(traced.json['geojson']['features'][0]['geometry']['type'],'LineString')
        self.assertEqual(self.client.post('/api/detect',json={'bbox':loaded.json['bbox'],'points':[[.2,.2],[.2,.2]]}).status_code,400)


if __name__ == '__main__':
    unittest.main()
