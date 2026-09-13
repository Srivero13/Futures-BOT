import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bot

BASE = json.loads((bot.ROOT / 'configs/two-paper.json').read_text())['bots'][0]

class PaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = copy.deepcopy(BASE)
        self.path = Path(self.tmp.name) / 'book.sqlite3'
        self.book = bot.Ledger(self.path, self.c)

    def tearDown(self):
        self.book.db.close()
        self.tmp.cleanup()

    def test_costs_and_no_double_buy(self):
        self.book.tick(100, 100, 'BUY')
        before = self.book.state()
        self.book.tick(100, 100, 'BUY')
        self.assertEqual(before[:2], self.book.state()[:2])
        self.book.tick(100, 100, 'SELL')
        cash, qty, _, _ = self.book.state()
        self.assertLess(cash, self.c['initial_cash'])
        self.assertEqual(qty, 0)
        self.assertGreaterEqual(cash, 0)

    def test_history_survives_restart(self):
        self.book.tick(100, 100, 'HOLD')
        self.book.tick(101, 101, 'HOLD')
        self.book.db.close()
        self.book = bot.Ledger(self.path, self.c)
        self.assertEqual(self.book.db.execute('SELECT mid FROM samples ORDER BY id').fetchall(), [(100.,), (101.,)])

    def test_restart_retains_position(self):
        self.book.tick(100, 100, 'BUY')
        expected = self.book.state()
        self.book.db.close()
        self.book = bot.Ledger(self.path, self.c)
        self.assertEqual(self.book.state(), expected)

    def test_accounts_isolated(self):
        other = bot.Ledger(Path(self.tmp.name) / 'other.sqlite3', self.c)
        try:
            self.book.tick(100, 100, 'BUY')
            self.assertEqual(other.state()[1], 0)
            self.assertEqual(other.state()[0], self.c['initial_cash'])
        finally:
            other.db.close()

    def test_loss_halts_and_closes(self):
        self.book.tick(100, 100, 'BUY')
        result = self.book.tick(1, 1, 'BUY')
        self.assertEqual(result['event'], 'STOP')
        self.assertTrue(result['halted'])
        self.assertEqual(self.book.state()[1], 0)
        self.book.tick(100, 100, 'BUY')
        self.assertEqual(self.book.state()[1], 0)

    def test_bad_prices_do_not_mutate(self):
        initial = self.book.state()
        for bid, ask in [(float('nan'), 100), (100, 99), (0, 0), (1, float('inf'))]:
            with self.assertRaises(ValueError):
                self.book.tick(bid, ask, 'BUY')
        self.assertEqual(initial, self.book.state())

    def test_spread_blocks_entry(self):
        self.book.tick(90, 110, 'BUY')
        self.assertEqual(self.book.state()[1], 0)

    def test_live_rejected(self):
        with self.assertRaises(ValueError):
            bot.validate({**self.c, 'mode': 'live'})

    def test_config_change_rejected(self):
        with self.assertRaises(ValueError):
            bot.Ledger(self.path, {**self.c, 'symbol': 'ETHUSDT'})

    def test_binance_parser(self):
        with patch('bot.http_json', return_value=({'bidPrice': '100', 'askPrice': '101'}, {})):
            self.assertEqual(bot.binance_quote('BTCUSDT'), (100., 101.))

    def test_capital_demo_only_and_no_order(self):
        env = {'CAPITAL_API_KEY': 'fake', 'CAPITAL_IDENTIFIER': 'fake', 'CAPITAL_API_PASSWORD': 'fake'}
        responses = [({}, {'CST': 'fake', 'X-SECURITY-TOKEN': 'fake'}), ({'accounts': []}, {})]
        with patch.dict('os.environ', env), patch('bot.http_json', side_effect=responses) as http:
            bot.capital_probe()
        self.assertEqual(http.call_count, 2)
        self.assertTrue(all(call.args[0].startswith('https://demo-api-capital.') for call in http.call_args_list))
        self.assertTrue(http.call_args_list[1].args[0].endswith('/accounts'))

if __name__ == '__main__':
    unittest.main()
