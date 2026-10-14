import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from check_cuda_training import check


class CudaCheckTests(unittest.TestCase):
    def torch(self, available=True):
        return SimpleNamespace(cuda=SimpleNamespace(
            is_available=lambda: available, synchronize=Mock(),
            get_device_name=lambda index: 'test GPU'),
            __version__='test', version=SimpleNamespace(cuda='test'))

    def test_missing_cuda_never_trains(self):
        with patch.dict('sys.modules', torch=self.torch(False)), patch(
                'engine_v1.research_mlp.fit_predict') as train:
            with self.assertRaisesRegex(RuntimeError, 'never falls back'):
                check()
            train.assert_not_called()

    def test_real_backend_is_requested_with_fixed_control(self):
        gpu = self.torch()
        def predict(x, y, targets, **kwargs):
            self.assertEqual(kwargs, dict(device='cuda', epochs=40))
            self.assertEqual(x.shape, (1500, 3))
            np.testing.assert_allclose(y, 3*x[:, 0]-2*x[:, 1])
            return [3*targets[0][:, 0]-2*targets[0][:, 1]]
        with patch.dict('sys.modules', torch=gpu), patch(
                'engine_v1.research_mlp.fit_predict', side_effect=predict):
            result = check()
        self.assertTrue(result['cuda_training_check_passed'])
        self.assertFalse(result['approved'])
        self.assertEqual(result['mse'], 0)
        self.assertEqual(gpu.cuda.synchronize.call_count, 2)

    def test_bad_predictions_fail(self):
        for output in (np.zeros(500), np.full(500, np.nan), np.zeros((500, 1))):
            with self.subTest(shape=output.shape), patch.dict('sys.modules', torch=self.torch()), patch(
                    'engine_v1.research_mlp.fit_predict', return_value=[output]):
                with self.assertRaises(ValueError):
                    check()
