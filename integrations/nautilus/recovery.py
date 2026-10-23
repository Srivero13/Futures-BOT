"""Fixed subscription interruption protocol, not a socket-disconnect simulation."""
from .observe import SYMBOLS


def fresh(snapshot):
    return all(snapshot['quote_age_ms'][s] is not None and
               0 <= snapshot['quote_age_ms'][s] <= 1000 for s in SYMBOLS)


class SubscriptionDrill:
    """Pause once at 90s, resume after 10s, allow 15s to recover both feeds."""
    def __init__(self):
        self.paused_at = None
        self.resumed_at = None
        self.recovered_at = None
        self.pre_pause_fresh = False
        self.both_stale_seen = False
        self.quiet_samples = 0
        self.quiet_counts = None
        self.pause_delivery_violations = 0
        self.resume_counts = None
        self.unexpected_stale_samples = 0
        self.events = []

    def step(self, elapsed, snapshot, observer):
        healthy = fresh(snapshot)
        if self.paused_at is None:
            if elapsed >= 90:
                self.pre_pause_fresh = healthy and all(snapshot['counts'].values())
                observer.pause_quotes()
                self.paused_at = elapsed
                self.events.append(dict(event='unsubscribe_requested', elapsed=elapsed))
            elif elapsed >= 60 and not healthy:
                self.unexpected_stale_samples += 1
            return
        if self.resumed_at is None:
            # Give subscriptions two seconds to drain any already queued updates.
            if elapsed-self.paused_at >= 2:
                counts = snapshot['counts'].copy()
                if self.quiet_counts is not None:
                    if counts != self.quiet_counts:
                        self.pause_delivery_violations += 1
                    else:
                        self.quiet_samples += 1
                self.quiet_counts = counts
                self.both_stale_seen |= all(snapshot['quote_age_ms'][s] is not None and
                                           snapshot['quote_age_ms'][s] > 1000 for s in SYMBOLS)
            if elapsed-self.paused_at >= 10:
                self.resume_counts = snapshot['counts'].copy()
                observer.resume_quotes()
                self.resumed_at = elapsed
                self.events.append(dict(event='subscribe_requested', elapsed=elapsed))
            return
        if self.recovered_at is None:
            if healthy and all(snapshot['counts'][s] > self.resume_counts[s] for s in SYMBOLS):
                self.recovered_at = elapsed
                self.events.append(dict(event='both_symbols_fresh_again', elapsed=elapsed))
            elif elapsed-self.resumed_at > 15:
                self.unexpected_stale_samples += 1
        elif not healthy:
            self.unexpected_stale_samples += 1

    def report(self, elapsed):
        recovery_seconds = (None if self.recovered_at is None else self.recovered_at-self.resumed_at)
        checks = dict(pre_pause_both_fresh=self.pre_pause_fresh,
                      subscription_pause_observed=self.quiet_samples >= 3 and self.pause_delivery_violations == 0,
                      both_symbols_became_stale=self.both_stale_seen,
                      both_symbols_recovered_within_15s=recovery_seconds is not None and recovery_seconds <= 15,
                      post_recovery_observed_30s=self.recovered_at is not None and elapsed-self.recovered_at >= 30,
                      no_unexpected_stale_samples=self.unexpected_stale_samples == 0)
        return dict(checks=checks, events=self.events,
                    recovery_seconds=recovery_seconds, quiet_samples=self.quiet_samples,
                    pause_delivery_violations=self.pause_delivery_violations,
                    unexpected_stale_samples=self.unexpected_stale_samples,
                    scope='Intentional quote unsubscription/resubscription; not transport reconnect or backfill validation.')


def assessment(observation_checks, drill_report):
    """Keep ordinary results separately; intentional gaps only belong to this protocol."""
    checks = {k: v for k, v in observation_checks.items() if k != 'no_stale_samples'}
    checks.update(drill_report['checks'])
    return checks
