import unittest
from unittest.mock import patch
import numpy as np
import extraction
import app as application


class PreloadTests(unittest.TestCase):
    def test_imported_app_loads_model_without_upload_once(self):
        class Net:
            def setInput(self,blob): pass
            def forward(self): return np.zeros((1,1,512,512),np.float32)
        with patch.object(extraction,'model',None), patch.object(extraction,'model_name',None), \
             patch.object(application,'local_model_checked',False), \
             patch('app.Path.is_file',return_value=True), \
             patch('app.cv2.dnn.readNetFromONNX',return_value=Net()) as load:
            client=application.app.test_client()
            self.assertEqual(client.get('/api/health').json['model'],'model.onnx')
            self.assertEqual(client.get('/api/health').json['model'],'model.onnx')
            self.assertEqual(load.call_count,1)


if __name__=='__main__':
    unittest.main()
