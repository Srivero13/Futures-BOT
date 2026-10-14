import builtins
import unittest
from unittest.mock import patch

import numpy as np
from engine_v1.research_mlp import fit_predict, _validate_neural_inputs, _prepare_neural_arrays


class NeuralInputTests(unittest.TestCase):
    def test_invalid_inputs_fail_before_torch_import(self):
        x = np.ones((3, 2)); y = np.ones(3); targets = [x]
        cases = [
            (x, y, targets, 'cuda', 0), (x, y, targets, 'cuda', -1),
            (x, y, targets, 'cuda', True), (x, y, targets, 'cuda', 1.5),
            (x, y, targets, 'cuda', float('nan')),
            (x, y, targets, 'other', 40),
            (np.empty((0, 2)), np.empty(0), targets, 'cuda', 40),
            (np.ones((3, 0)), y, targets, 'cuda', 40),
            (x, y[:2], targets, 'cuda', 40),
            (x, y[:, None], targets, 'cuda', 40),
            (x, y, [], 'cuda', 40),
            (x, y, [np.ones((3, 1))], 'cuda', 40),
            (x, y, [np.ones(2)], 'cuda', 40),
            (x, np.full(3, np.inf), targets, 'cuda', 40),
            (np.full((3, 2), np.nan), y, targets, 'cuda', 40),
            (x, y, [np.full((3, 2), np.inf)], 'cuda', 40),
            (x.astype(complex), y, targets, 'cuda', 40),
            (x.astype(str), y, targets, 'cuda', 40),
        ]
        original_import = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name == 'torch':
                self.fail('Invalid input reached Torch')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=guarded):
            for args in cases:
                with self.subTest(args=args[3:]), self.assertRaises(ValueError):
                    fit_predict(*args)

    def test_valid_arrays_are_preserved_and_empty_prediction_rows_allowed(self):
        x = np.arange(6.).reshape(3, 2); y = np.arange(3.)
        empty = np.empty((0, 2))
        tx, ty, targets = _validate_neural_inputs(x, y, [x, empty], 'cpu', 40)
        self.assertIs(tx, x)
        self.assertIs(ty, y)
        self.assertIs(targets[0], x)
        self.assertIs(targets[1], empty)

    def test_finite_overflow_is_rejected_before_torch_import(self):
        x = np.arange(6.).reshape(3, 2); y = np.arange(3.)
        maximum = np.finfo(float).max
        cases = [
            (np.full((3, 2), maximum), y, [x]),
            (x, np.array([-maximum, 0, maximum]), [x]),
            (x, y, [np.full((1, 2), 1e40)]),
        ]
        original_import = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name == 'torch':
                self.fail('Overflow reached Torch')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=guarded):
            for args in cases:
                with self.subTest(), self.assertRaisesRegex(ValueError, 'numeric range'):
                    fit_predict(*args)

    def test_preparation_preserves_scaling_and_uses_training_statistics(self):
        x = np.array([[1., 7.], [2., 7.], [3., 7.]])
        y = np.array([2., 4., 6.])
        target = np.array([[100., 7.]])
        nx, ny, targets, ym, ys = _prepare_neural_arrays(x, y, [target, np.empty((0, 2))])
        scale = x.std(0); scale[scale < 1e-12] = 1
        np.testing.assert_array_equal(nx, ((x-x.mean(0))/scale).astype(np.float32))
        np.testing.assert_array_equal(ny, ((y-y.mean())/y.std()).astype(np.float32))
        np.testing.assert_array_equal(targets[0], ((target-x.mean(0))/scale).astype(np.float32))
        self.assertEqual(targets[1].shape, (0, 2))
        self.assertEqual((ym, ys), (float(y.mean()), float(y.std())))
        _, constant_y, _, _, constant_scale = _prepare_neural_arrays(x, np.ones(3), [target])
        np.testing.assert_array_equal(constant_y, np.zeros(3, dtype=np.float32))
        self.assertEqual(constant_scale, 1e-12)
