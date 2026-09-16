import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import test_v15 as fixtures
from engine_v1.nonlinear import expand, PolynomialModel, load_model
from engine_v1.training import fit_stream
from engine_v1.operations import process_lock
from train_v16 import run_training


class V16Tests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.V15Tests()
        fixture.setUp()
        self.addCleanup(fixture.temp.cleanup)
        self.path, self.root = fixture.path, fixture.root
        self.args = ([self.path], 'fixture', 'BTCUSDT', self.root/'runs', 400*60000, 600*60000, 700*60000)

    def run_job(self, **kwargs):
        return run_training(*self.args, verbose=False, chunk_size=32, **kwargs)

    def test_polynomial_fit_save_load_and_forecast(self):
        directory, report = self.run_job()
        model = load_model(directory/'model.json')
        self.assertIsInstance(model, PolynomialModel)
        self.assertEqual(len(model.coef), 27)
        self.assertEqual(report['feature_count'], 27)
        self.assertFalse(model.approved)
        x = np.array(model.mean[:6])
        self.assertAlmostEqual(model.predict(x), model.batch(x[None,:])[0])
        self.assertIsNone(model.predict([1,2]))
        self.assertIsNone(model.predict([float('nan')]*6))

    def test_nonlinear_capacity_on_known_synthetic_interaction(self):
        rng = np.random.default_rng(16)
        x = rng.normal(0, .1, (1000, 6))
        y = 100*x[:,0]*x[:,1] + rng.normal(0, .01, 1000)
        times = np.arange(1, 1001)*60000
        data = np.column_stack((times, times+180000, x, y))
        factory = lambda: iter(np.array_split(data, 10))
        nonlinear, _ = fit_stream(factory, 'BTCUSDT', 3, 600*60000, 900*60000, model_kind='polynomial')
        linear, _ = fit_stream(factory, 'BTCUSDT', 3, 600*60000, 900*60000)
        p = nonlinear.batch(x[900:])
        q = np.array([linear.predict(row) for row in x[900:]], dtype=float)
        mask = np.isfinite(p) & np.isfinite(q)
        self.assertGreater(mask.sum(), 90)
        self.assertLess(np.mean((p[mask]-y[900:][mask])**2), np.mean((q[mask]-y[900:][mask])**2)*.1)

    def test_completed_run_is_reused_without_refitting(self):
        directory, first = self.run_job()
        with patch('engine_v1.training.fit_stream', side_effect=AssertionError('Unexpected refit')):
            other, second = self.run_job()
        self.assertEqual(directory, other)
        self.assertEqual(first, second)

    def test_failed_evaluation_resumes_completed_fit(self):
        with patch('engine_v1.training.evaluate_stream', side_effect=OSError('injected failure')):
            with self.assertRaises(OSError): self.run_job()
        directory = next((self.root/'runs').iterdir())
        self.assertTrue((directory/'fit-complete.json').exists())
        self.assertFalse((directory/'complete.json').exists())
        self.assertEqual(json.loads((directory/'status.json').read_text())['state'], 'failed')
        with patch('engine_v1.training.fit_stream', side_effect=AssertionError('Unexpected refit')):
            self.run_job()
        self.assertTrue((directory/'complete.json').exists())

    def test_interruption_before_fit_does_not_publish_completion(self):
        with patch('engine_v1.training.fit_stream', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.run_job()
        directory = next((self.root/'runs').iterdir())
        self.assertEqual(json.loads((directory/'status.json').read_text())['state'], 'interrupted')
        self.assertFalse((directory/'complete.json').exists())
        self.run_job()
        self.assertTrue((directory/'complete.json').exists())

    def test_low_disk_fails_before_fit(self):
        with patch('train_v16.shutil.disk_usage', return_value=type('Usage', (), {'free':0})()):
            with self.assertRaisesRegex(OSError, 'GiB'): self.run_job()
        self.assertFalse(any((self.root/'runs').rglob('model.json')))

    def test_same_run_lock_prevents_concurrent_mutation(self):
        directory, _ = self.run_job()
        before = (directory/'status.json').read_text()
        with process_lock(directory/'run.lock'):
            with self.assertRaises(RuntimeError): self.run_job()
        self.assertEqual((directory/'status.json').read_text(), before)

    def test_tampered_completion_is_rejected(self):
        directory, _ = self.run_job()
        (directory/'evaluation.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'integrity'): self.run_job()

    def test_different_parameters_create_separate_runs(self):
        first, _ = self.run_job()
        second, _ = self.run_job(alpha=100.)
        self.assertNotEqual(first, second)
        self.assertTrue((first/'complete.json').exists())

    def test_input_mutation_prevents_fit_checkpoint(self):
        real_fit = fit_stream
        def mutate(*args, **kwargs):
            result = real_fit(*args, **kwargs)
            with self.path.open('a') as handle: handle.write('\n')
            return result
        with patch('engine_v1.training.fit_stream', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'Input changed'): self.run_job()
        self.assertFalse(any((self.root/'runs').rglob('fit-complete.json')))

    def test_bad_dates_data_and_options_fail_before_training(self):
        with self.assertRaises(ValueError): self.run_job(horizon=2)
        with self.assertRaises(ValueError): self.run_job(alpha=float('nan'))
        with self.assertRaises(ValueError): run_training(*self.args[:4], 650*60000, 680*60000, 700*60000, verbose=False)
        with self.assertRaises(ValueError): run_training([self.root/'missing.csv'], *self.args[1:], verbose=False)

    def test_doctor_reports_missing_dependency_without_crashing(self):
        import doctor
        original = doctor.importlib.import_module
        def missing(name):
            if name == 'websocket': raise ImportError('injected missing dependency')
            return original(name)
        with patch('doctor.importlib.import_module', side_effect=missing):
            result = doctor.check(Path(__file__).resolve().parents[1], self.root/'doctor')
        self.assertFalse(result['ready'])
        self.assertFalse(next(c for c in result['checks'] if c['check']=='websocket-client')['ok'])

    def test_polynomial_expansion_dimensions_and_products(self):
        x = np.array([[1,2,3,4,5,6.]])
        y = expand(x)
        self.assertEqual(y.shape, (1,27))
        self.assertEqual(y[0,6], 1)
        self.assertEqual(y[0,-1], 36)

    def test_atomic_model_failure_preserves_old_model(self):
        directory, _ = self.run_job()
        path = directory/'model.json'
        original = path.read_bytes()
        model = load_model(path)
        with patch('engine_v1.operations.os.replace', side_effect=OSError('injected write failure')):
            with self.assertRaises(OSError): model.save(path)
        self.assertEqual(original, path.read_bytes())

    def test_fit_cannot_see_future_changed_labels(self):
        rng = np.random.default_rng(16)
        x = rng.normal(0,.1,(1000,6)); t = np.arange(1,1001)*60000
        a = np.column_stack((t,t+180000,x,rng.normal(size=1000)))
        b = a.copy();b[900:,2:] *= 100
        first, _ = fit_stream(lambda: iter([a]), 'BTCUSDT',3,600*60000,900*60000,model_kind='polynomial')
        second, _ = fit_stream(lambda: iter([b]), 'BTCUSDT',3,600*60000,900*60000,model_kind='polynomial')
        self.assertEqual(first,second)

    def test_exchange_rules_retry_transient_failure(self):
        import io
        from engine_v1.stream import fetch_rules
        response = io.StringIO(json.dumps({'symbols':[{'symbol':'BTCUSDT'}]}))
        with patch('engine_v1.stream.urlopen', side_effect=[OSError('network'), response]) as request, patch('engine_v1.stream.time.sleep'), patch('engine_v1.stream.rules_from_exchange', return_value='rules'):
            result = fetch_rules({'BTCUSDT'}, lambda: 30, lambda: None)
        self.assertEqual(result, {'BTCUSDT':'rules'})
        self.assertEqual(request.call_count, 2)

    def test_exchange_rules_stop_after_bounded_failures(self):
        from engine_v1.stream import fetch_rules
        with patch('engine_v1.stream.urlopen', side_effect=OSError('network')) as request, patch('engine_v1.stream.time.sleep'):
            with self.assertRaises(OSError): fetch_rules({'BTCUSDT'}, lambda: 30, lambda: None)
        self.assertEqual(request.call_count, 3)

    def test_launcher_missing_dependency_returns_actionable_exit(self):
        import start_bot
        with patch('doctor.check', return_value={'ready':False,'checks':[{'detail':'Install dependencies'}]}), patch('start_bot.sys.stderr'):
            self.assertEqual(start_bot.main(), 2)

    def test_launcher_does_not_hide_runtime_failure(self):
        import start_bot
        with patch('doctor.check', return_value={'ready':True}), patch('engine_v1.stream.main', side_effect=OSError('network unavailable')), patch('start_bot.sys.stderr'):
            self.assertEqual(start_bot.main(), 2)

    def test_fit_checkpoint_tampering_is_rejected(self):
        with patch('engine_v1.training.evaluate_stream', side_effect=OSError('injected failure')):
            with self.assertRaises(OSError): self.run_job()
        directory = next((self.root/'runs').iterdir())
        (directory/'model.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'checkpoint integrity'): self.run_job()

    def test_ledger_closes_even_if_shutdown_health_write_fails(self):
        from engine_v1.stream import stream
        from unittest.mock import Mock
        root = Path(__file__).resolve().parents[1]
        cfg = json.loads((root/'configs/v11-paper.json').read_text())
        cfg['database'] = str(self.root/'paper.sqlite3')
        cfg['model_directory'] = str(root/'models')
        config = self.root/'paper.json'; config.write_text(json.dumps(cfg))
        engine = Mock()
        profile = {'endpoints':{'quote':{'quote_deadline_ms':1000,'minimum_decision_spacing_ms':1000}}}
        with patch('engine_v1.stream.load_profile', return_value=profile), patch('engine_v1.stream.Portfolio', return_value=engine), patch('engine_v1.stream.fetch_rules', side_effect=OSError('network')), patch('engine_v1.stream.atomic_json', side_effect=OSError('disk')):
            with self.assertRaises(OSError): stream(1,'ignored',False,config,self.root/'health.json')
        engine.close.assert_called_once()

    def test_comparison_uses_common_accepted_rows(self):
        from compare_v16 import compare
        from engine_v1.model import RidgeModel
        _, _ = self.run_job()
        first, _ = self.run_job(model_kind='linear')
        second, _ = self.run_job()
        result = compare([self.path],load_model(first/'model.json'),load_model(second/'model.json'),600*60000,700*60000)
        self.assertGreater(result['common_accepted_examples'],0)
        self.assertFalse(result['approved'])
