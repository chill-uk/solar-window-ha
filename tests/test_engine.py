import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone

root = Path(__file__).resolve().parents[1] / 'custom_components' / 'solar_window'
def load(name):
    spec = importlib.util.spec_from_file_location(name, root / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
Engine = load('engine').SolarEngine
backfill = load('backfill')

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine('Europe/Amsterdam', 20, 10, 120, 120)
        self.now = datetime(2026, 10, 4, 5, 50, tzinfo=timezone.utc)
    def sample(self, power, minutes=1):
        self.engine.sample(self.now, power)
        self.now += timedelta(minutes=minutes)
    def test_debounce_hysteresis_and_cloud_recovery(self):
        self.sample(0)
        self.sample(30); self.sample(30); self.sample(30)
        row = self.engine.days['2026-10-04']
        self.assertEqual(row['start'],'2026-10-04T05:51:00+00:00')
        self.sample(15); self.assertTrue(self.engine.active)
        self.sample(0); self.sample(30); self.assertIsNone(row['finish'])
        self.sample(0); self.sample(0); self.sample(0)
        self.assertEqual(row['finish'],'2026-10-04T05:57:00+00:00')
        self.sample(30); self.sample(30); self.sample(30)
        self.assertIsNone(row['finish']); self.assertEqual(len(row['intervals']),2)
        self.assertIn('interrupted',row['flags'])
    def test_invalid_state_interrupts_confirmation(self):
        self.sample(0); self.sample(30); self.sample(None); self.sample(30); self.sample(30)
        self.assertFalse(self.engine.active)
        self.sample(30); self.assertTrue(self.engine.active)
        self.assertIn('start_unobserved',self.engine.days['2026-10-04']['flags'])
    def test_restart_never_bridges_unknown_gap(self):
        self.sample(30);self.sample(30);self.sample(30)
        self.engine=Engine('Europe/Amsterdam',20,10,120,120,self.engine.export())
        self.now+=timedelta(hours=4)
        self.sample(0)
        row=self.engine.days['2026-10-04']
        self.assertIn('recording_gap',row['flags'])
        self.assertEqual(row['finish'],'2026-10-04T05:52:00+00:00')
    def test_import_atomic_and_preserves_quality(self):
        good={'date':'2026-10-03','start':'2026-10-03T06:00Z','finish':'2026-10-03T17:00Z'}
        bad={**good,'date':'2026-10-02'}
        with self.assertRaises(ValueError): self.engine.merge([good,bad])
        self.assertEqual(self.engine.days,{})
        self.assertEqual(self.engine.merge([good]),1)
        self.assertEqual(self.engine.merge([{**good,'source':'statistics'}]),0)
    def test_local_midnight_splits_interval(self):
        self.engine=Engine('Europe/Amsterdam',20,10,0,0)
        self.now=datetime(2026,10,4,21,59,tzinfo=timezone.utc)
        self.sample(30);self.sample(30)
        self.assertEqual(self.engine.days['2026-10-04']['finish'],'2026-10-04T22:00:00+00:00')
        self.assertEqual(self.engine.days['2026-10-05']['start'],'2026-10-04T22:00:00+00:00')
    def test_month_ranges_respect_dst(self):
        ranges=list(backfill.month_ranges(2026,'Europe/Amsterdam'))
        self.assertEqual(ranges[9][0].hour,22)
        self.assertEqual(ranges[9][1].hour,23)
    def test_backfill_uses_bin_boundaries_not_fake_precision(self):
        ts=datetime(2026,10,4,6,tzinfo=timezone.utc).timestamp()
        records=backfill.bins_to_days([{'start':ts,'change':0.1},{'start':ts+3600,'change':0}, {'start':ts+7200,'change':0.5}], 'Europe/Amsterdam')
        self.assertEqual(records[0]['start'],'2026-10-04T06:00:00+00:00')
        self.assertEqual(records[0]['finish'],'2026-10-04T09:00:00+00:00')
        self.assertIn('approximate',records[0]['flags'])

if __name__=='__main__': unittest.main()

class RegressionTests(unittest.TestCase):
    def test_brief_startup_spike_does_not_create_empty_day(self):
        engine=Engine('Europe/Amsterdam',20,10,180,600)
        now=datetime(2026,10,4,6,tzinfo=timezone.utc)
        engine.sample(now,30);engine.sample(now+timedelta(minutes=1),0)
        self.assertEqual(engine.days,{})
    def test_restart_does_not_close_imported_unknown_finish(self):
        engine=Engine('Europe/Amsterdam')
        engine.merge([{'date':'2026-10-03','start':'2026-10-03T06:00Z','finish':None}])
        engine.sample(datetime(2026,10,4,6,tzinfo=timezone.utc),0)
        self.assertIsNone(engine.days['2026-10-03']['finish'])
    def test_export_import_preserves_intervals(self):
        source=Engine('Europe/Amsterdam',20,10,0,0)
        now=datetime(2026,10,4,6,tzinfo=timezone.utc)
        for i,power in enumerate([0,30,0,30,0]):source.sample(now+timedelta(minutes=i),power)
        target=Engine('Europe/Amsterdam')
        row={**source.days['2026-10-04'],'source':'import'}
        target.merge([row])
        self.assertEqual(len(target.days['2026-10-04']['intervals']),2)
