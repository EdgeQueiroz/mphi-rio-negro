import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from experimental.adc_mphi.runner import build_report, forecast_records, load_observations, metrics, main


def sample():
    issue = '2026-10-01'
    def entry(model, val, when=issue):
        return {'forecast_id':f'{when}|{model}', 'forecast_date':when, 'created_at':f'{when}T07:55:00-04:00',
                'model_version':model, 'observed_level_at_issue':20.0,
                'projections': {'7': {'target_date':'2026-10-08','central':val}}}
    return {
        'observations':{'series':[
            {'date':'2026-10-01','level':20.0,'source':'Porto de Manaus'},
            {'date':'2026-10-08','level':19.0,'source':'Porto de Manaus'},
            {'date':'2026-10-09','level':18.8,'source':'Porto de Manaus'}]},
        'forecasts': {'entries':[entry('MPHI v1.0',19.1),entry('MPHI v1.1-shadow',19.4)]},
        'hydrologic': {'entries':[entry('MPHI v2.0-hydrologic-alpha',18.9)]},
    }


class LearningReportTest(unittest.TestCase):
    def setUp(self):
        self.data = sample()
        self.proofs = {k:{'path':k,'sha256':'0'*64} for k in self.data}
        self.today = dt.date(2026,10,9)

    def test_evaluates_three_models_and_persistence(self):
        rpt = build_report(self.data,self.proofs,self.today)
        self.assertEqual(rpt['evaluated_count'],4)
        self.assertEqual(rpt['pending_count'],0)
        self.assertEqual(rpt['forecast_count'],4)
        base = next(x for x in rpt['metrics'] if x['model']=='MPHI v1.0' and x['horizon_days']==7)
        self.assertAlmostEqual(base['mae_m'],0.1)
        self.assertFalse(rpt['baseline_modified'])

    def test_paired_comparison(self):
        rpt = build_report(self.data,self.proofs,self.today)
        pair = next(p for p in rpt['paired_comparisons'] if p['model']=='MPHI v2.0-hydrologic-alpha' and p['reference']=='MPHI v1.0' and p['horizon_days']==7)
        self.assertEqual(pair['n_paired'],1)
        self.assertAlmostEqual(pair['mae_delta_m'],0.0)

    def test_pending_not_prematurely_scored(self):
        rpt = build_report(self.data,self.proofs,dt.date(2026,10,7))
        self.assertEqual(rpt['evaluated_count'],0)
        self.assertEqual(rpt['pending_count'],4)

    def test_missing_target_stays_missing(self):
        self.data['observations']['series'] = self.data['observations']['series'][:1]
        rpt = build_report(self.data,self.proofs,self.today)
        self.assertEqual(rpt['missing_observations_count'],4)
        self.assertEqual(rpt['evaluated_count'],0)

    def test_future_observation_excluded(self):
        ob = load_observations(self.data['observations'], dt.date(2026,10,7))
        self.assertNotIn(dt.date(2026,10,8),ob)

    def test_duplicated_forecast_rejected(self):
        self.data['forecasts']['entries'].append(self.data['forecasts']['entries'][0])
        with self.assertRaisesRegex(ValueError,'duplicada'):
            forecast_records(self.data,self.today)

    def test_mismatched_horizon_rejected(self):
        self.data['forecasts']['entries'][0]['projections']['7']['target_date']='2026-10-09'
        with self.assertRaisesRegex(ValueError,'Horizonte inconsistente'):
            forecast_records(self.data,self.today)

    def test_future_dated_issuance_rejected(self):
        self.data['forecasts']['entries'][0]['created_at']='2026-10-08T07:55:00-04:00'
        with self.assertRaisesRegex(ValueError,'incompatível'):
            forecast_records(self.data,self.today)

    def test_invalid_numeric_rejected(self):
        self.data['forecasts']['entries'][0]['projections']['7']['central']=float('nan')
        with self.assertRaisesRegex(ValueError,'finito'):
            forecast_records(self.data,self.today)

    def test_no_production_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for key, path in __import__('experimental.adc_mphi.runner',fromlist=['INPUTS']).INPUTS.items():
                file=root/path;file.parent.mkdir(parents=True,exist_ok=True)
                file.write_text(json.dumps(self.data[key]),encoding='utf-8')
            snapshot={str(p):p.read_bytes() for p in (root/'docs/data').glob('*.json')}
            main(['--repo-root', str(root),'--output-dir',str(root/'out'),'--as-of','2026-10-09'])
            self.assertTrue((root/'out/report.md').exists())
            self.assertTrue((root/'out/report.json').exists())
            self.assertEqual(snapshot,{str(p):p.read_bytes() for p in (root/'docs/data').glob('*.json')})

    def test_non_porto_observation_excluded(self):
        self.data['observations']['series'][1]['source']='Outra fonte'
        rpt=build_report(self.data,self.proofs,self.today)
        self.assertEqual(rpt['evaluated_count'],0)

    def test_conflicting_observation_rejected(self):
        self.data['observations']['series'].append({'date':'2026-10-08','level':17.0,'source':'Porto de Manaus'})
        with self.assertRaisesRegex(ValueError,'contraditórias'):
            build_report(self.data,self.proofs,self.today)

    def test_empty_metrics(self):
        self.assertIsNone(metrics([])['mae_m'])

if __name__=='__main__': unittest.main()