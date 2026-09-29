"""Экспорт общей месячной модели в два направления существующего API."""
from pathlib import Path
import argparse
import hashlib
import json
import joblib
import duckdb
import numpy as np
import pandas as pd
from backend.ml.monthly_adapter import MonthlyModel
from backend.ml.contracts import SENSOR_PATTERN, INFRASTRUCTURE_PATTERN, validate_features
from backend.ml import monthly_features as mf


def export(handoff, planning, destination):
    handoff, planning, destination = map(Path, (handoff, planning, destination))
    config = json.loads((planning/'bundle/model_config.json').read_text(encoding='utf-8'))
    report = json.loads((planning/'training_report.json').read_text(encoding='utf-8'))
    assert config['target'] == 'target_monthly' and config['window_hours'] == [24, 744]
    assert config['calibration']['coef'] == 1 and config['calibration']['intercept'] == 0
    features = config['features']
    validate_features(features)
    model_text = (planning/'bundle/model.txt').read_text(encoding='utf-8')
    adapter = MonthlyModel(model_text, features)
    signature = hashlib.sha256((model_text + json.dumps(config, sort_keys=True)).encode()).hexdigest()[:12]
    raw = pd.read_parquet(handoff/'ml_ready/scoring_latest.parquet')
    expected = mf.predict_batch(raw, handoff/'episodes/fault_episodes.parquet', planning/'bundle')
    con = duckdb.connect()
    con.execute("SET threads=4")
    mf.episode_tables(con, handoff/'episodes/fault_episodes.parquet')
    selected = raw[config['base_features'] + ['channel_id','prediction_time','last_state_ts']].copy()
    selected['__order'] = np.arange(len(selected))
    con.register('snapshot_rows', selected)
    enriched = con.execute(mf.episode_select('snapshot_rows') + ' ORDER BY r.__order').fetchdf()
    con.close()
    x = mf.feature_matrix(enriched, features)
    data = x.copy()
    data['entity_id'] = raw.channel_id.astype(str).to_numpy()
    data['object_id'] = raw.object_id_current.astype('Int64').astype('string').fillna('unknown').to_numpy()
    data['sensor_type'] = raw.sensor_type_current.fillna('unknown').to_numpy()
    data['system_type'] = raw.system_type_current.fillna('').to_numpy()
    data['sensor_name'] = ''
    data['system_tag'] = ''
    data['prediction_time'] = raw.prediction_time.to_numpy()
    data['last_explicit_state'] = raw.last_explicit_state.fillna('unknown').to_numpy()
    data['eligible'] = raw.at_risk_with_history.eq(True).to_numpy()
    eligible = data.eligible
    np.testing.assert_allclose(adapter.predict_proba(x.loc[eligible])[:,1], expected.loc[eligible,'risk_probability'], rtol=1e-6, atol=1e-7)
    test = pd.read_parquet(planning/'reports/test_predictions.parquet')
    metadata = pd.read_parquet(handoff/'channel_metadata.parquet')[['channel_id','sensor_type_current']]
    test = test.merge(metadata, on='channel_id', validate='many_to_one')
    patterns = {'sensor': SENSOR_PATTERN, 'infrastructure': INFRASTRUCTURE_PATTERN}
    destination.mkdir(parents=True, exist_ok=True)
    (destination/'models').mkdir(exist_ok=True)
    panels = []
    for direction, pattern in patterns.items():
        part = data.loc[data.sensor_type.str.contains(pattern, case=False, regex=True, na=False)].copy()
        part['direction'] = direction
        panels.append(part)
        subset = test.loc[test.sensor_type_current.str.contains(pattern, case=False, regex=True, na=False)]
        measured = mf.score_metrics(subset.target_monthly, subset.probability, config['threshold'])
        measured['pr_auc'] = measured['average_precision']
        meta = {'direction': direction, 'algorithm': 'LightGBM shared monthly model',
                'version': f'monthly-{signature}-{direction}', 'provenance': 'notebook_handoff',
                'features': features, 'target': 'target_monthly', 'threshold': config['threshold'],
                'horizon': {'min_hours':24, 'max_hours':744}, 'test': measured,
                'global_test': report['test_metrics'], 'meets_case_metrics': measured['precision']>.7 and measured['recall']>.5,
                'validation_candidates': [], 'split_ranges': {}, 'training_seconds': None,
                'shared_model_id': signature, 'evaluation_status': report['evaluation_status'],
                'limitations': ['Одна общая модель, два фильтра по оборудованию; отдельного обучения направлений нет.',
                    'Месячный прогноз записи Неисправен, не подтверждённая физическая поломка.',
                    '2026 год уже использовался при разработке. Оценка ретроспективная.',
                    'Качество по типам неоднородно; газовые датчики не имеют верных предупреждений.',
                    'Повторное обучение с нуля может отличаться от сохранённого варианта.',
                    'Низкий балл не подтверждает исправность. Пересекающиеся окна не являются уникальными авариями.']}
        joblib.dump({'model': adapter, 'metadata': meta}, destination/'models'/f'{direction}.joblib', compress=3)
        (destination/'models'/f'{direction}.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    scored = pd.concat(panels, ignore_index=True)
    scored.to_parquet(destination/'scoring.parquet', index=False)
    objects_path = destination/'objects.json'
    objects = json.loads(objects_path.read_text(encoding='utf-8')) if objects_path.exists() else []
    known = {o['id'] for o in objects}
    for oid in sorted(set(scored.object_id)-known):
        objects.append({'id':oid,'name':f'Объект {oid}','district':'Не указан','latitude':None,'longitude':None,'coordinate_source':'unavailable'})
    objects_path.write_text(json.dumps(objects, ensure_ascii=False), encoding='utf-8')
    dataset = {'mode':'real','provenance':'notebook_handoff','target':'target_monthly',
        'features':features,'rows':len(scored),'source_snapshot_channels':len(raw),
        'excluded_snapshot_channels':len(raw)-len(scored),'notice':
        'Исторический срез. Месячный риск нового сообщения Неисправен: от +24 часов до +31 дня. Низкий балл не подтверждает исправность.'}
    (destination/'dataset.json').write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'rows':len(scored),'eligible':int(scored.eligible.sum()),'snapshot':str(scored.prediction_time.max()),'probability_parity':True}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--handoff', required=True, type=Path)
    p.add_argument('--planning', required=True, type=Path)
    p.add_argument('--destination', default='runtime/real', type=Path)
    a = p.parse_args()
    export(a.handoff, a.planning, a.destination)
