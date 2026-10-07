import unittest
from unittest.mock import patch,Mock
import numpy as np
import app


class ResolutionTests(unittest.TestCase):
    def tearDown(self):
        app.orthophoto.cache_clear()

    def test_maximum_wms_dimensions_without_upsampling(self):
        response=Mock(content=b'image bytes')
        decoded=np.zeros((4096,4096,3),np.uint8)
        with patch('app.requests.get',return_value=response) as get,patch('app.cv2.imdecode',return_value=decoded):
            image=app.orthophoto((100,100,1100,1100))
            self.assertIs(image,decoded)
            self.assertEqual(get.call_args.kwargs['params']['WIDTH'],4096)
            self.assertEqual(get.call_args.kwargs['params']['HEIGHT'],4096)
            response.raise_for_status.assert_called_once()

    def test_server_must_not_silently_return_low_resolution(self):
        with patch('app.requests.get',return_value=Mock(content=b'image bytes')),patch('app.cv2.imdecode',return_value=np.zeros((1024,1024,3),np.uint8)):
            with self.assertRaisesRegex(ValueError,'4096'):
                app.orthophoto((100,100,1100,1100))


if __name__=='__main__':
    unittest.main()
