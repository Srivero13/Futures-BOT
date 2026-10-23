import unittest
from unittest.mock import Mock

from integrations.nautilus.observe import Health, SYMBOLS
from integrations.nautilus.recovery import SubscriptionDrill, assessment


def exercise(*, ignore_pause=False, missing_after_resume=None, resume_delay=0, extra_gap=False):
    health = Health(0, 1000)
    drill = SubscriptionDrill()
    actor = Mock()
    actor.enabled = True
    actor.pause_quotes.side_effect = lambda: setattr(actor, 'enabled', False)
    actor.resume_quotes.side_effect = lambda: setattr(actor, 'enabled', True)
    for sec in range(181):
        for symbol in SYMBOLS:
            deliver = actor.enabled or ignore_pause
            if drill.resumed_at is not None:
                deliver &= sec-drill.resumed_at > resume_delay
                deliver &= symbol != missing_after_resume
            if extra_gap and 140 <= sec <= 145:
                deliver = False
            if deliver:
                health.quote(symbol, sec, 100, 101, 1, 1)
        snapshot = health.sample(sec, 1000+sec)
        drill.step(sec, snapshot, actor)
    return drill.report(180), snapshot, actor


class RecoveryTests(unittest.TestCase):
    def test_pause_stale_and_both_feeds_recovered(self):
        report, health, actor = exercise()
        self.assertTrue(all(report['checks'].values()))
        self.assertGreater(health['stale_samples_after_warmup'], 0)
        actor.pause_quotes.assert_called_once()
        actor.resume_quotes.assert_called_once()
        self.assertEqual(report['recovery_seconds'], 1)

    def test_ignored_unsubscription_cannot_pass(self):
        report, _, _ = exercise(ignore_pause=True)
        self.assertFalse(report['checks']['subscription_pause_observed'])
        self.assertFalse(report['checks']['both_symbols_became_stale'])

    def test_one_recovered_symbol_is_insufficient(self):
        report, _, _ = exercise(missing_after_resume='ETHUSDT')
        self.assertFalse(report['checks']['both_symbols_recovered_within_15s'])

    def test_late_recovery_fails_even_if_final_feed_fresh(self):
        report, health, _ = exercise(resume_delay=20)
        self.assertTrue(all(age == 0 for age in health['quote_age_ms'].values()))
        self.assertFalse(report['checks']['both_symbols_recovered_within_15s'])

    def test_unrelated_staleness_is_not_excused(self):
        report, _, _ = exercise(extra_gap=True)
        self.assertFalse(report['checks']['no_unexpected_stale_samples'])

    def test_clock_and_order_checks_are_preserved(self):
        report, _, _ = exercise()
        ordinary = dict(no_stale_samples=False, clock_stable=False, no_orders=False)
        result = assessment(ordinary, report)
        self.assertFalse(result['clock_stable'])
        self.assertFalse(result['no_orders'])
        self.assertFalse(ordinary['no_stale_samples'])
        self.assertNotIn('no_stale_samples', result)


if __name__ == '__main__':
    unittest.main()
