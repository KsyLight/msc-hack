"""Проверка экспорта и API в отдельной временной базе."""
from pathlib import Path
import json
import shutil
import tempfile
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app


def check():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        shutil.copytree(root/'runtime/real', runtime/'real', ignore=shutil.ignore_patterns('*.sqlite3*'))
        with TestClient(create_app(Settings(runtime=runtime, mode='real'))) as client:
            assert client.get('/api/health').json()['mode'] == 'real'
            models = client.get('/api/models').json()
            assert len(models) == 2
            assert all(m['target']=='target_monthly' and m['horizon']=={'min_hours':24,'max_hours':744} for m in models)
            service = client.app.state.service
            results = service.predictions()
            assert len(results) == len(service.data) == 6145
            lookup = {(r['direction'],r['entity_id']):r for r in results}
            for row in results:
                t = pd.Timestamp(row['prediction_time'])
                assert pd.Timestamp(row['target_start'])-t == pd.Timedelta(hours=24)
                assert pd.Timestamp(row['target_end'])-t == pd.Timedelta(hours=744)
            for direction in ('sensor','infrastructure'):
                meta = service.models[direction]['metadata']
                frame = service.data.loc[service.data.direction.eq(direction) & service.data.eligible].head(3)
                rows=[]
                for _, r in frame.iterrows():
                    rows.append({'entity_id':r.entity_id,'object_id':r.object_id,'sensor_type':r.sensor_type,
                        'prediction_time':r.prediction_time.isoformat(),'eligible':True,'last_explicit_state':r.last_explicit_state,
                        'features':{f:None if pd.isna(r[f]) else float(r[f]) for f in meta['features']}})
                response=client.post(f'/api/predict/{direction}',json={'rows':rows})
                assert response.status_code==200,response.text
                for got in response.json()['items']:
                    assert got['score']==lookup[(direction,got['entity_id'])]['score']
                rows[0]['eligible']=False
                response=client.post(f'/api/predict/{direction}',json={'rows':[rows[0]]})
                assert response.json()['items'][0]['score'] is None
                rows[0]['features'].pop(meta['features'][0])
                assert client.post(f'/api/predict/{direction}',json={'rows':[rows[0]]}).status_code==422
            before=client.get('/api/predictions').json()['total']
            assert client.post('/api/predictions/run').status_code==200
            assert client.get('/api/predictions').json()['total']==before
            assert client.get('/api/dashboard').status_code==200
            assert client.get('/api/objects').status_code==200
            assert client.get('/api/data-quality').status_code==200
            assert client.get('/api/predictions/export.csv').status_code==200
            result={'api_passed':True,'rows':len(results),'eligible':int(service.data.eligible.sum()),
                'window_hours':[24,744],'directions':[m['direction'] for m in models],
                'test_metrics':{m['direction']:m['test'] for m in models}}
    (root/'reports').mkdir(exist_ok=True)
    (root/'reports/monthly_integration_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':
    check()
