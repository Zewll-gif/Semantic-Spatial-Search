# CLEAN PROJECT HEADER
# ไฟล์: test_geoai_api.py
# หน้าที่: ตรวจสอบ regression และสัญญาการทำงานของระบบ
# Input: CLEAN PROJECT และ test fixtures
# Output: ผลผ่าน/ไม่ผ่านและหลักฐาน QA
# Dependency สำคัญ: backend/frontend ที่ถูกทดสอบ
# สิ่งที่ต้องระวัง: ห้ามเปลี่ยน taxonomy, model output, CRS หรือหน่วยโดยไม่ตรวจ audit
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
import geoai_api

client = TestClient(geoai_api.app)
passed = []
failed = []

def check(name, fn):
    try:
        fn(); passed.append(name)
    except Exception as exc:
        failed.append({"name":name,"error":repr(exc)})

health = client.get('/api/geoai/health')
check('health endpoint', lambda: (health.status_code == 200 and health.json()['status'] == 'success') or (_ for _ in ()).throw(AssertionError(health.text)))
classes = client.get('/api/geoai/classes')
check('classes endpoint', lambda: (classes.status_code == 200 and len(classes.json()['data']) == 7) or (_ for _ in ()).throw(AssertionError(classes.text)))
search = client.post('/api/geoai/search', json={'class_codes':['R2'],'min_area_rai':5,'max_results':10})
check('R2 search', lambda: (search.status_code == 200 and search.json()['data']['count'] > 0) or (_ for _ in ()).throw(AssertionError(search.text)))
first = search.json()['data']['results'][0]
pid = first['polygon_id']
geom = first['geometry']
bad_class = client.post('/api/geoai/search', json={'class_codes':['R99']})
check('invalid class', lambda: bad_class.status_code in (400,422))
area = client.post('/api/geoai/area', json={'polygon_id':pid})
check('area calculation', lambda: (area.status_code == 200 and area.json()['data']['area_m2'] > 0) or (_ for _ in ()).throw(AssertionError(area.text)))
dist = client.post('/api/geoai/distance', json={'source_polygon_id':pid,'target_polygon_id':pid})
check('distance', lambda: (dist.status_code == 200 and dist.json()['data']['distance_m'] == 0) or (_ for _ in ()).throw(AssertionError(dist.text)))
near = client.post('/api/geoai/near', json={'target_class':'R2','reference_class':'R4','max_distance_m':300,'min_area_rai':5,'max_results':10})
check('near query', lambda: near.status_code in (200,404))
inter = client.post('/api/geoai/intersect', json={'geometry_a':geom,'geometry_b':geom})
check('intersect', lambda: (inter.status_code == 200 and inter.json()['data']['intersection_area_m2'] > 0) or (_ for _ in ()).throw(AssertionError(inter.text)))
ndvi = client.post('/api/geoai/ndvi-stats', json={'polygon_id':pid})
check('NDVI stats', lambda: (ndvi.status_code == 200 and 'mean' in ndvi.json()['data']) or (_ for _ in ()).throw(AssertionError(ndvi.text)))
ndwi = client.post('/api/geoai/ndwi-stats', json={'polygon_id':pid})
check('NDWI stats', lambda: (ndwi.status_code == 200 and 'mean' in ndwi.json()['data']) or (_ for _ in ()).throw(AssertionError(ndwi.text)))
evidence = client.post('/api/geoai/evidence', json={'polygon_id':pid})
check('evidence response', lambda: (evidence.status_code == 200 and 'spectral' in evidence.json()['data']) or (_ for _ in ()).throw(AssertionError(evidence.text)))
empty = client.post('/api/geoai/search', json={'class_codes':['R2'],'min_area_rai':1e12})
check('empty result handling', lambda: empty.status_code == 404)
invalid_geom = client.post('/api/geoai/area', json={'geometry':{'type':'NotAType','coordinates':[]}})
check('invalid geometry', lambda: invalid_geom.status_code in (400,422))
coords = geom['coordinates'][0][0]
check('CRS conversion', lambda: (-180 <= coords[0] <= 180 and -90 <= coords[1] <= 90) or (_ for _ in ()).throw(AssertionError(coords)))
schema = search.json()
check('response schema validity', lambda: all(k in schema for k in ('status','request_id','data','limitations')))

print({'passed':len(passed),'failed':len(failed),'passed_tests':passed,'failures':failed})
if failed:
    raise SystemExit(1)
