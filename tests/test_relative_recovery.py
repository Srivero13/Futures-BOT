import unittest
import numpy as np
from research_relative_recovery import signal_details,build_signals,evaluate,WINDOW,MINUTE
from train_v15 import timestamp


def prices():
    x=np.arange(24)
    b=np.r_[.001+.001*np.sin(x),.001]
    e=np.r_[1.5*b[:-1]+.0001*np.cos(x),-.015]
    grid=np.arange(WINDOW)
    btc=100*np.exp(np.interp(grid,np.arange(26)*60,np.r_[0,np.cumsum(b)]))
    eth=100*np.exp(np.interp(grid,np.arange(26)*60,np.r_[0,np.cumsum(e)]))
    eth[-6]=eth[-1]*np.exp(-.001)
    return eth,btc


def rows(start,values):
    return [dict(timestamp=start+i*MINUTE,open=str(v),close=str(v),
                 high=str(v*1.001),low=str(v*.999),volume='100') for i,v in enumerate(values)]


class RelativeRecoveryTests(unittest.TestCase):
    def test_fixed_rule_requires_recovery_and_nonfalling_btc(self):
        eth,btc=prices()
        result=signal_details(eth,btc)
        self.assertTrue(result['enter'])
        self.assertLess(result['residual_z'],-2)
        self.assertLess(result['residual_log_bps'],-52)
        falling=btc.copy();falling[-1]=falling[-61]*np.exp(-.001)
        self.assertFalse(signal_details(eth,falling)['enter'])
        no_recovery=eth.copy();no_recovery[-6]=no_recovery[-1]*1.001
        self.assertFalse(signal_details(no_recovery,btc)['enter'])
        self.assertFalse(signal_details(eth,np.ones(WINDOW)*100)['enter'])

    def test_current_and_future_candles_cannot_change_prior_signal(self):
        start=timestamp('2026-03-01');end=start+120*MINUTE
        e,b=prices()
        erows=rows(start-WINDOW*MINUTE,np.r_[e,np.repeat(e[-1],120)])
        brows=rows(start-WINDOW*MINUTE,np.r_[b,np.repeat(b[-1],120)])
        before=build_signals(erows,brows,start,end)
        self.assertTrue(before[start]['enter'])
        for r in erows:
            if r['timestamp']>=start:r['close']=str(float(r['close'])*1.7)
        after=build_signals(erows,brows,start,end)
        self.assertEqual(before[start],after[start])
        with self.assertRaises(ValueError):build_signals(erows,brows[:-1],start,end)

    def test_simulation_delay_hold_nonoverlap_and_cost_stress(self):
        start=timestamp('2026-03-01');end=start+240*MINUTE
        data=rows(start-21*MINUTE,np.repeat(100.,261))
        signals={start+i*60*MINUTE:{'enter':True} for i in range(4)}
        result=evaluate(data,signals,start,end)
        trades=result['trades']
        self.assertEqual(len(trades),2) # The next hourly decision falls before the current exit.
        self.assertEqual([t['decision_ms'] for t in trades],[start,start+120*MINUTE])
        for t in trades:
            self.assertEqual(t['entry_ms']-t['decision_ms'],MINUTE)
            self.assertEqual(t['exit_ms']-t['entry_ms'],60*MINUTE)
            self.assertLess(float(t['net_pnl']),0)
        stress=result['summary']['fixed_quantity_extra_slippage_bps_per_side']
        self.assertAlmostEqual(float(stress['0']),float(result['summary']['net_pnl']))
        self.assertLess(float(stress['1']),float(stress['0']))
        self.assertFalse(result['approved'])

    def test_grid_warmup_and_reserve_are_required(self):
        start=timestamp('2026-03-01');end=start+120*MINUTE
        e,b=prices()
        erows=rows(start-WINDOW*MINUTE,np.r_[e,np.repeat(e[-1],120)])
        brows=rows(start-WINDOW*MINUTE,np.r_[b,np.repeat(b[-1],120)])
        with self.assertRaises(ValueError):build_signals(erows[1:],brows[1:],start,end)
        with self.assertRaises(ValueError):build_signals(erows,brows,start,end-MINUTE)
