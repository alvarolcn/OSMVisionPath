"""Optional online smoke check: python tests/check_wms.py from project root."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app

with app.test_client() as client:
    response = client.post('/api/ortho', json={'lat':40.42,'lon':-4.1,'span':750})
    if response.status_code != 200:
        raise SystemExit(f'WMS failed: {response.status_code} {response.json}')
    assert (response.json['width'],response.json['height']) == (4096,4096)
    print('WMS OK: real PNOA image, 4096 x 4096; bbox:',response.json['bbox'])
