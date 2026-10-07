import unittest
from unittest.mock import patch
import numpy as np
import extraction
import wololo
from app import app, downloaded_images


class WololoTests(unittest.TestCase):
    def setUp(self):
        wololo.cache.clear()
        self.addCleanup(wololo.cache.clear)

    def test_route_prefers_road_over_direct_shortcut(self):
        probability = np.zeros((64,64),np.float32)
        probability[10:13,5:56] = .99
        probability[10:51,5:8] = .99
        probability[10:51,53:56] = .99
        path = wololo.route(probability,(6,49),(54,49))
        self.assertEqual(path[0],(6,49))
        self.assertEqual(path[-1],(54,49))
        self.assertLess(min(y for _,y in path),14)

    def test_configured_limit_can_stop_or_allow_same_route(self):
        probability = np.zeros((64,64),np.float32)
        with self.assertRaisesRegex(ValueError,'límite de 10'):
            wololo.route(probability,(0,0),(63,63),search_limit=10)
        path = wololo.route(probability,(0,0),(63,63),search_limit=4096)
        self.assertEqual(path[-1],(63,63))

    def test_centering_moves_route_away_from_high_probability_edge(self):
        probability = np.zeros((96,96),np.float32)
        probability[35:56,:] = .8
        probability[35,:] = .99
        centering = wololo.center_penalty(probability,.5)
        path = wololo.route(probability,(6,35),(89,35),centering=centering)
        middle = [y for x,y in path if 28<=x<=65]
        self.assertLessEqual(abs(float(np.median(middle))-45),1)
        self.assertEqual(path[0],(6,35))
        self.assertEqual(path[-1],(89,35))

    def test_simplification_in_metres_preserves_curve_and_endpoints(self):
        points = [[.1,.5],[.2,.5005],[.3,.5],[.4,.6],[.5,.6005],[.6,.6]]
        result = wololo.simplify_path(points,1.,(0.,0.,1000.,1000.))
        self.assertLess(len(result),len(points))
        self.assertEqual(result[0],points[0])
        self.assertEqual(result[-1],points[-1])
        self.assertIn(points[3],result)

    def test_trace_keeps_intermediate_anchor_exact(self):
        image = np.zeros((128,128,3),np.uint8)
        image[53:76] = 230
        anchors = [[.1,.5],[.4,.502],[.9,.5]]
        with patch.object(extraction,'model',object()),patch.object(extraction,'probabilities',side_effect=lambda _,tile:tile[:,:,0]/255.):
            sections,info = wololo.trace(image,anchors,.5,'anchor-fixture',tolerance_m=2.,bbox=(0.,0.,1000.,1000.))
        self.assertEqual(sections[0]['path'][-1],anchors[1])
        self.assertEqual(sections[1]['path'][0],anchors[1])
        self.assertTrue(info['centered'])
        self.assertLess(info['simplified_nodes'],info['raw_nodes'])

    def test_native_tiles_reused_and_uncertainty_exposed(self):
        image = np.full((128,128,3),25,np.uint8)
        anchors = [[.1,.5],[.8,.5]]
        with patch.object(extraction,'model',object()), patch.object(extraction,'probabilities',side_effect=lambda _,tile:tile[:,:,0]/255.) as inference:
            sections,info = wololo.trace(image,anchors,.5,'fixture')
            self.assertEqual(inference.call_args.args[1].shape,(512,512,3))
            self.assertEqual(sections[0]['path'][0],anchors[0])
            self.assertEqual(sections[-1]['path'][-1],anchors[-1])
            self.assertTrue(sections[0]['uncertain'])
            self.assertEqual(info['computed_tiles'],1)
            _,info = wololo.trace(image,anchors,.5,'fixture')
            self.assertEqual(info['computed_tiles'],0)
            self.assertEqual(inference.call_count,1)

    def test_api_never_downloads_and_validates_markers(self):
        client = app.test_client()
        bbox = (0.,0.,1000.,1000.)
        with patch.dict(downloaded_images,{},clear=True), patch('app.orthophoto') as wms:
            response = client.post('/api/wololo',json={'bbox':bbox,'points':[[.1,.5],[.8,.5]]})
            self.assertEqual(response.status_code,400)
            wms.assert_not_called()
            downloaded_images[bbox] = np.full((128,128,3),25,np.uint8)
            response = client.post('/api/wololo',json={'bbox':bbox,'points':[[float('nan'),.5],[.8,.5]]})
            self.assertEqual(response.status_code,400)
            with patch('app.ensure_local_model'),patch.object(extraction,'model',object()),patch.object(extraction,'probabilities',return_value=np.full((512,512),.1,np.float32)):
                response = client.post('/api/wololo',json={'bbox':bbox,'points':[[.1,.5],[.8,.5]]})
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.json['sections'][0]['uncertain'])
            wms.assert_not_called()

    def test_api_validates_and_forwards_search_limit(self):
        bbox = (0.,0.,1000.,1000.)
        body = {'bbox':bbox,'points':[[.1,.1],[.9,.9]]}
        with patch.dict(downloaded_images,{bbox:np.zeros((128,128,3),np.uint8)},clear=True),patch('app.ensure_local_model'),patch('wololo.trace',return_value=([],{})) as trace:
            client = app.test_client()
            for limit in (0,3000001,True,1200000.5,'1200000',None):
                response = client.post('/api/wololo',json={**body,'search_limit':limit})
                self.assertEqual(response.status_code,400)
            trace.assert_not_called()
            response = client.post('/api/wololo',json={**body,'search_limit':1500000})
            self.assertEqual(response.status_code,200)
            self.assertEqual(trace.call_args.args[-1],1500000)
            self.assertEqual(trace.call_args.kwargs['tolerance_m'],.5)
            response = client.post('/api/wololo',json={**body,'tolerance_m':5})
            self.assertEqual(response.status_code,200)
            self.assertEqual(trace.call_args.kwargs['tolerance_m'],5.)
            for tolerance in (-1,0,float('nan'),100):
                response = client.post('/api/wololo',json={**body,'tolerance_m':tolerance})
                self.assertEqual(response.status_code,400)


if __name__ == '__main__':
    unittest.main()
