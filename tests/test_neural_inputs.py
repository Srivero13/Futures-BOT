import builtins
import unittest
from unittest.mock import patch

import numpy as np
from engine_v1.research_mlp import fit_predict, _validate_neural_inputs


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
