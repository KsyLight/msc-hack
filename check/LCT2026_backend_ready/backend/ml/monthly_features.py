from pathlib import Path
import gc
import hashlib
import json
import time
import numpy as np
import pandas as pd
import duckdb
from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve
from sklearn.metrics import precision_score, recall_score, f1_score, brier_score_loss, log_loss
from sklearn.linear_model import LogisticRegression

FEATURE_VERSION = 'episodes-past-v2'
TARGET = 'target_monthly'
EPISODE_WINDOWS = [1, 7, 30, 90, 365]
FORBIDDEN = {'last_seen', 'target_fault_0_24h', TARGET, 'channel_followup_48h',
             'global_complete_24_48h', 'target_start', 'target_end', 'sample_weight',
             'sampling_probability', 'sensor_type_current', 'object_id_current',
             'system_type_current', 'channel_id', 'prediction_time'}

def sql_path(path):
    return "'" + str(path).replace('\\', '/').replace("'", "''") + "'"

def episode_tables(con, path):
    con.execute(f"""CREATE OR REPLACE TEMP TABLE starts_prefix AS
    WITH daily AS (
      SELECT channel_id, CAST(start_ts AS DATE) AS day, count(*) AS n,
             max(start_ts) AS last_start
      FROM read_parquet({sql_path(path)}) WHERE observed_start
      GROUP BY channel_id, CAST(start_ts AS DATE)
    ) SELECT *, sum(n) OVER(PARTITION BY channel_id ORDER BY day) AS cumulative,
        count(*) OVER(PARTITION BY channel_id ORDER BY day) AS cumulative_days
      FROM daily ORDER BY channel_id, day""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE closes_prefix AS
    WITH daily AS (
      SELECT channel_id, CAST(end_ts AS DATE) AS day, count(*) AS n,
        count(*) FILTER(WHERE duration_hours <= 1.0/60) AS short_n,
        sum(ln(1+duration_hours)) AS log_duration_sum, max(end_ts) AS last_close
      FROM read_parquet({sql_path(path)})
      WHERE observed_start AND end_ts IS NOT NULL AND duration_hours >= 0
      GROUP BY channel_id, CAST(end_ts AS DATE)
    ) SELECT *, sum(n) OVER w AS cumulative,
        sum(short_n) OVER w AS short_cumulative,
        sum(log_duration_sum) OVER w AS duration_cumulative
      FROM daily WINDOW w AS (PARTITION BY channel_id ORDER BY day)
      ORDER BY channel_id, day""")

def episode_select(source):
    fields = ["r.*", "epoch(r.prediction_time-s0.last_start)/3600 AS hours_since_fault_start",
              "epoch(r.prediction_time-c0.last_close)/3600 AS hours_since_fault_end",
              "greatest(s0.last_start,c0.last_close) AS episode_feature_max_ts"]
    joins = ["ASOF LEFT JOIN starts_prefix s0 ON r.channel_id=s0.channel_id AND r.prediction_time>s0.day",
             "ASOF LEFT JOIN closes_prefix c0 ON r.channel_id=c0.channel_id AND r.prediction_time>c0.day"]
    for days in EPISODE_WINDOWS:
        fields.append(f"coalesce(s0.cumulative,0)-coalesce(s{days}.cumulative,0) AS fault_starts_{days}d")
        fields.append(f"coalesce(s0.cumulative_days,0)-coalesce(s{days}.cumulative_days,0) AS fault_start_days_{days}d")
        joins.append(f"ASOF LEFT JOIN starts_prefix s{days} ON r.channel_id=s{days}.channel_id AND r.prediction_time-INTERVAL {days} DAY>s{days}.day")
    for days in [6, 13, 20, 27]:
        fields.append(f"CASE WHEN w{days}.n IS NULL THEN 0 ELSE 1 END AS fault_day_lag_{days}")
        joins.append(f"LEFT JOIN starts_prefix w{days} ON r.channel_id=w{days}.channel_id AND CAST(r.prediction_time-INTERVAL {days} DAY AS DATE)=w{days}.day")
    for days in [30, 90]:
        fields += [f"coalesce(c0.cumulative,0)-coalesce(c{days}.cumulative,0) AS fault_closes_{days}d",
                   f"coalesce(c0.short_cumulative,0)-coalesce(c{days}.short_cumulative,0) AS short_fault_closes_{days}d",
                   f"(coalesce(c0.duration_cumulative,0)-coalesce(c{days}.duration_cumulative,0))/nullif(coalesce(c0.cumulative,0)-coalesce(c{days}.cumulative,0),0) AS past_log_duration_mean_{days}d"]
        joins.append(f"ASOF LEFT JOIN closes_prefix c{days} ON r.channel_id=c{days}.channel_id AND r.prediction_time-INTERVAL {days} DAY>c{days}.day")
    return 'SELECT ' + ', '.join(fields) + ' FROM ' + source + ' r ' + ' '.join(joins)

def add_episode_file(con, source, destination):
    source_sql = f'read_parquet({sql_path(source)})'
    keys_sql = f'(SELECT channel_id,prediction_time FROM {source_sql})'
    query = f'WITH augmented AS ({episode_select(keys_sql)}) SELECT r.*, a.* EXCLUDE(channel_id,prediction_time) FROM {source_sql} r JOIN augmented a USING(channel_id,prediction_time)'
    temporary = Path(destination).with_suffix('.partial.parquet')
    con.execute(f'COPY ({query}) TO {sql_path(temporary)} (FORMAT PARQUET, COMPRESSION ZSTD)')
    temporary.replace(destination)
    bad = con.execute(f"SELECT count(*) FROM read_parquet({sql_path(destination)}) WHERE episode_feature_max_ts>=prediction_time").fetchone()[0]
    if bad:
        raise ValueError('Обнаружена будущая информация в признаках эпизодов')

def augmented_feature_names(base_features):
    episode = ['hours_since_fault_start', 'hours_since_fault_end']
    episode += [f'fault_starts_{d}d' for d in EPISODE_WINDOWS]
    episode += [f'fault_start_days_{d}d' for d in EPISODE_WINDOWS]
    episode += [f'fault_day_lag_{d}' for d in [6, 13, 20, 27]]
    episode += [f'{stem}_{d}d' for d in [30, 90]
                for stem in ['fault_closes', 'short_fault_closes', 'past_log_duration_mean']]
    ratios = ['hours_since_explicit_state', 'alarm_share_1d', 'fault_share_7d',
              'undefined_share_7d', 'night_share_7d', 'numeric_share_7d',
              'events_per_active_day_7d', 'events_per_active_day_30d',
              'numeric_range_7d', 'numeric_range_30d', 'short_fault_share_90d',
              'fault_start_ratio_7d_30d', 'fault_day_rate_30d', 'fault_day_rate_90d',
              'fault_day_rate_365d', 'starts_per_fault_day_30d', 'fault_weekly_repeats']
    result = list(dict.fromkeys(list(base_features) + episode + ratios))
    if set(result) & FORBIDDEN:
        raise ValueError('Служебное поле попало в признаки')
    return result

def feature_matrix(frame, names):
    d = frame.copy(deep=False)
    d = d.assign(hours_since_explicit_state=(pd.to_datetime(d['prediction_time'])-pd.to_datetime(d['last_state_ts'])).dt.total_seconds()/3600)
    ratios = {'alarm_share_1d':('alarms_1d','events_1d'),
              'fault_share_7d':('fault_messages_7d','events_7d'),
              'undefined_share_7d':('undefined_messages_7d','events_7d'),
              'night_share_7d':('night_events_7d','events_7d'),
              'numeric_share_7d':('numeric_n_7d','events_7d'),
              'events_per_active_day_7d':('events_7d','active_days_7d'),
              'events_per_active_day_30d':('events_30d','active_days_30d'),
              'starts_per_fault_day_30d':('fault_starts_30d','fault_start_days_30d'),
              'short_fault_share_90d':('short_fault_closes_90d','fault_closes_90d')}
    for name, (a,b) in ratios.items():
        d[name] = d[a] / d[b].replace(0,np.nan)
    for days in [7,30]:
        d[f'numeric_range_{days}d'] = d[f'numeric_max_{days}d']-d[f'numeric_min_{days}d']
    d['fault_start_ratio_7d_30d'] = (d['fault_starts_7d']/7)/(d['fault_starts_30d']/30).replace(0,np.nan)
    for days in [30, 90, 365]:
        d[f'fault_day_rate_{days}d'] = d[f'fault_start_days_{days}d']/days
    d['fault_weekly_repeats'] = d[[f'fault_day_lag_{days}' for days in [6, 13, 20, 27]]].sum(axis=1)
    x = d.loc[:,names].replace([np.inf,-np.inf],np.nan).astype('float32')
    if set(x) & FORBIDDEN:
        raise ValueError('Запрещённый признак')
    return x

def load_frame(path, con, where=None):
    q = f'SELECT * FROM read_parquet({sql_path(path)})'
    if where:
        q += ' WHERE ' + where
    frame = con.execute(q).fetchdf()
    for c in frame:
        if frame[c].dtype == 'float64':
            frame[c] = frame[c].astype('float32')
    for c in ['sensor_type_current','object_id_current','system_type_current','last_explicit_state']:
        if c in frame:
            frame[c] = frame[c].astype('category')
    return frame

def threshold_table(y, p):
    precision, recall, thresholds = precision_recall_curve(y,p)
    out = pd.DataFrame({'threshold':thresholds,'precision':precision[:-1],'recall':recall[:-1]})
    out['f1'] = 2*out.precision*out.recall/(out.precision+out.recall).replace(0,np.nan)
    out['f1'] = out['f1'].fillna(0)
    return out

def select_threshold(y,p):
    t = threshold_table(y,p)
    feasible = t.loc[(t.precision>0.7)&(t.recall>0.5)]
    reason = 'precision>0.7 and recall>0.5' if len(feasible) else 'max F1; joint requirement unattainable on this validation block'
    chosen = (feasible if len(feasible) else t).sort_values(['f1','precision','recall'],ascending=False).iloc[0]
    return float(chosen.threshold),reason

def score_metrics(y,p,threshold):
    y = np.asarray(y,dtype=int); p=np.asarray(p,dtype=float)
    positive = p>=threshold
    tp=int(np.sum(positive & (y==1))); fp=int(np.sum(positive & (y==0)))
    fn=int(np.sum(~positive & (y==1))); tn=int(np.sum(~positive & (y==0)))
    return {'rows':len(y),'positives':int(y.sum()),'prevalence':float(y.mean()),
            'average_precision':float(average_precision_score(y,p)) if y.sum() else None,
            'roc_auc':float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None,
            'precision':float(precision_score(y,positive,zero_division=0)),
            'recall':float(recall_score(y,positive,zero_division=0)),
            'f1':float(f1_score(y,positive,zero_division=0)),
            'alerts':int(positive.sum()),'tp':tp,'fp':fp,'fn':fn,'tn':tn,
            'threshold':float(threshold)}

def probability_metrics(y,p):
    p=np.clip(np.asarray(p,dtype=float),1e-8,1-1e-8)
    return {'brier':float(brier_score_loss(y,p)), 'log_loss':float(log_loss(y,p,labels=[0,1]))}

def candidate_summary(y,p):
    t=threshold_table(y,p)
    at_p=t.loc[t.precision>0.7]
    at_r=t.loc[t.recall>0.5]
    return {'average_precision':float(average_precision_score(y,p)),
            'recall_at_precision_gt_07':float(at_p.recall.max()) if len(at_p) else 0.,
            'precision_at_recall_gt_05':float(at_r.precision.max()) if len(at_r) else 0.,
            'feasible':bool(((t.precision>0.7)&(t.recall>0.5)).any()),
            'max_f1':float(t.f1.max())}

def apply_calibration(p, calibration):
    p=np.clip(np.asarray(p,dtype=float),1e-8,1-1e-8)
    z=np.log(p/(1-p))*calibration['coef']+calibration['intercept']
    return 1/(1+np.exp(-np.clip(z,-50,50)))

def fit_calibration(y,p):
    clipped=np.clip(p,1e-8,1-1e-8)
    z=np.log(clipped/(1-clipped)).reshape(-1,1)
    model=LogisticRegression(C=10,max_iter=200,solver='lbfgs').fit(z,y)
    coefficient=float(model.coef_[0,0])
    if coefficient<=0:
        return {'coef':1.,'intercept':0.,'method':'identity; fitted slope nonpositive'}
    return {'coef':coefficient,'intercept':float(model.intercept_[0]),'method':'sigmoid logit, chronological calibration block'}

def predict_probability(model, x, features, kind):
    if kind=='lightgbm_native':
        return np.asarray(model.predict(x[features],num_threads=8),dtype='float32')
    if kind=='catboost':
        return np.asarray(model.predict_proba(x[features],thread_count=8)[:,1],dtype='float32')
    return np.asarray(model.predict_proba(x[features])[:,1],dtype='float32')

def cluster_intervals(frame, p, threshold, repeats=400, seed=2026):
    pred=np.asarray(p)>=threshold; y=frame[TARGET].to_numpy()
    counts=pd.DataFrame({'channel_id':frame.channel_id.astype(str),'tp':pred&(y==1),
                         'fp':pred&(y==0),'fn':~pred&(y==1)})
    groups=counts.groupby('channel_id')[['tp','fp','fn']].sum().to_numpy(dtype=float)
    rng=np.random.default_rng(seed); values=[]
    for _ in range(repeats):
        a,b,c=groups[rng.integers(0,len(groups),len(groups))].sum(axis=0)
        precision=a/(a+b) if a+b else np.nan
        recall=a/(a+c) if a+c else np.nan
        values.append([precision,recall,2*a/(2*a+b+c) if 2*a+b+c else np.nan])
    limits=np.nanquantile(values,[.025,.975],axis=0)
    return pd.DataFrame({'metric':['precision','recall','f1'],'low_95':limits[0],'high_95':limits[1]})

def reliability_table(y,p,bins=10):
    df=pd.DataFrame({'y':np.asarray(y),'p':np.asarray(p)})
    df['bin']=pd.qcut(df.p,q=bins,duplicates='drop')
    return df.groupby('bin',observed=True).agg(rows=('y','size'),mean_probability=('p','mean'),event_rate=('y','mean')).reset_index()

def score_subgroups(frame,p,threshold,column):
    data=frame[[column,TARGET]].copy()
    data['p']=p
    rows=[]
    for group,part in data.groupby(column,observed=True,dropna=False):
        rows.append({'group':str(group),**score_metrics(part[TARGET],part.p,threshold)})
    return pd.DataFrame(rows)

def load_bundle(directory):
    directory=Path(directory)
    config=json.loads((directory/'model_config.json').read_text(encoding='utf-8'))
    if config.get('target') != TARGET:
        raise ValueError('Модель предназначена для другого таргета')
    if config['feature_version'] != FEATURE_VERSION:
        raise ValueError('Версия обработки признаков не совпадает с версией модели')
    if config['kind']=='lightgbm':
        import lightgbm as lgb
        model=lgb.Booster(model_str=(directory/'model.txt').read_text(encoding='utf-8'))
        kind='lightgbm_native'
    elif config['kind']=='catboost':
        from catboost import CatBoostClassifier
        model=CatBoostClassifier();model.load_model(str(directory/'model.cbm'))
        kind='catboost'
    else:
        import joblib
        model=joblib.load(directory/'model.joblib');kind='logistic'
    return model,config,kind

def predict_batch(frame, episodes_path, model_directory):
    model,config,kind=load_bundle(model_directory)
    required=set(config['base_features'])|{'channel_id','prediction_time','last_state_ts','at_risk_with_history'}
    missing=required-set(frame.columns)
    if missing:
        raise ValueError('Отсутствуют обязательные поля: '+', '.join(sorted(missing)))
    data=frame.copy()
    data['prediction_time']=pd.to_datetime(data.prediction_time)
    data['last_state_ts']=pd.to_datetime(data.last_state_ts)
    if data.channel_id.isna().any():
        raise ValueError('Идентификатор канала не должен быть пустым')
    if data.prediction_time.isna().any() or not (data.prediction_time==data.prediction_time.dt.normalize()).all():
        raise ValueError('Нужен момент прогноза в полночь локального времени источника')
    if data.duplicated(['channel_id','prediction_time']).any():
        raise ValueError('Повторные ключи канал и момент прогноза')
    eligible=data.at_risk_with_history.eq(True)
    if data.loc[eligible,'last_state_ts'].isna().any():
        raise ValueError('Для применимого канала нужно время последнего явного состояния')
    if (data.loc[eligible,'last_state_ts']>=data.loc[eligible,'prediction_time']).any():
        raise ValueError('Время состояния должно быть строго раньше прогноза')
    if 'feature_max_ts' in data:
        if (pd.to_datetime(data.loc[eligible,'feature_max_ts'])>=data.loc[eligible,'prediction_time']).any():
            raise ValueError('Признаки содержат события после границы прогноза')
    answer=data[['channel_id','prediction_time']].copy()
    answer['risk_probability']=np.nan
    answer['alert']=pd.Series(pd.NA,index=answer.index,dtype='boolean')
    answer['status']=np.where(eligible,'scored','not_eligible')
    answer['model_version']=config['model_version']
    answer['target_start']=answer.prediction_time+pd.Timedelta(hours=config['window_hours'][0])
    answer['target_end']=answer.prediction_time+pd.Timedelta(hours=config['window_hours'][1])
    if eligible.any():
        con=duckdb.connect()
        con.execute("SET memory_limit='2GB'");con.execute('SET threads=4')
        episode_tables(con,episodes_path)
        selected=data.loc[eligible,list(config['base_features'])+['channel_id','prediction_time','last_state_ts']].reset_index(drop=True)
        selected['__order']=np.arange(len(selected))
        con.register('request_rows',selected)
        enriched=con.execute(episode_select('request_rows')+' ORDER BY r.__order').fetchdf()
        x=feature_matrix(enriched,config['features'])
        raw=predict_probability(model,x,config['features'],kind)
        p=apply_calibration(raw,config['calibration'])
        answer.loc[eligible,'risk_probability']=p
        answer.loc[eligible,'alert']=p>=config['threshold']
        con.close()
    return answer

FORBIDDEN |= {'target_fault_24_48h','target_fault_24_192h','target_monthly','next_start_after_24h','monthly_weight'}
