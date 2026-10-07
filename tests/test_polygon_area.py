import unittest
from unittest.mock import patch
import numpy as np
import polygon_area as area
import wololo
import extraction

POLYGON=[[.05,.05],[.3,.05],[.3,.7],[.7,.7],[.7,.05],[.95,.05],[.95,.95],[.05,.95]]
class PolygonTests(unittest.TestCase):
    def test_concave_clip_and_validation(self):
        polygon=area.validate(POLYGON)
        lines=area.clip([[[0.,.2],[1.,.2]]],polygon)
        self.assertEqual(len(lines),2)
        for line in lines:
            for p in line: self.assertTrue(area.inside(p,polygon))
        with self.assertRaises(ValueError): area.validate([[0,0],[1,1],[0,1],[1,0]])
    def test_wololo_cannot_shortcut_outside_concave_area(self):
        wololo.cache.clear()
        image=np.zeros((128,128,3),np.uint8)
        with patch.object(extraction,'model',object()),patch.object(extraction,'probabilities',return_value=np.ones((512,512),np.float32)):
            sections,_=wololo.trace(image,[[.15,.2],[.85,.2]],.5,'polygon-test',100000,bbox=(0,0,1000,1000),polygon=POLYGON)
        points=[p for section in sections for p in section['path']]
        self.assertTrue(all(area.inside(p,POLYGON) for p in points))
        self.assertGreater(max(p[1] for p in points),.7)
