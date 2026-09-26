"""Synthetic P4-06/07 operator -> evaluator -> replay path. No real approval.

Run with ``.venv/bin/python examples/p4_policy_history_offline.py``.
The fixed key, account and policy changes are test fixtures only.
"""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from p4_allocation_offline import NOW, POLICY_FILE, synthetic_analysis
from asset_copilot.application.policy_history import (
    PolicyApprovalAuthority, PolicyApprovalError, PolicyEvaluator,
    PolicyOperator, PolicyReader,
)
from asset_copilot.domain.policy import ETFClassification, ETFGroup


class DemoClock:
    def __init__(self, instant):
        self.instant = instant

    def __call__(self):
        return self.instant


def run_example(directory: Path):
    policy_db = directory / "policy.sqlite"
    analysis = synthetic_analysis(directory / "portfolio.sqlite")
    source = POLICY_FILE.read_bytes()
    clock = DemoClock(NOW - timedelta(days=1))
    key = b"offline-synthetic-approval-key-32-bytes"
    authority = PolicyApprovalAuthority(key, clock)
    with PolicyOperator(policy_db, key, clock) as operator:
        initial = operator.propose(source, scope=analysis.account_id,
                                   reason="offline fixture", request_id="initial",
                                   expected_revision_id=None)
        with PolicyReader(policy_db) as reader:
            try:
                reader.selected(analysis.account_id, NOW)
            except ValueError:
                print("unapproved initial revision: unavailable")
        approval = authority.approve(initial, scope=analysis.account_id,
                                     effective_at=NOW - timedelta(hours=1))
        try:
            operator.apply(replace(approval, content_id="tampered"))
        except PolicyApprovalError:
            print("altered approval target: rejected")
        operator.apply(approval)
        clock.instant = NOW
        with PolicyEvaluator(policy_db, clock) as evaluator:
            recorded = evaluator.evaluate(analysis, classifications=(
                ETFClassification("core", ETFGroup.CORE),
                ETFClassification("growth", ETFGroup.GROWTH),
            ))
        updated = source.replace(b'policy_version = "initial-v1"',
                                 b'policy_version = "offline-v2"').replace(
            b'individual_position_max = 15', b'individual_position_max = 14')
        clock.instant = NOW + timedelta(minutes=1)
        successor = operator.propose(updated, scope=analysis.account_id,
                                     reason="offline fixture change", request_id="second",
                                     expected_revision_id=initial.revision_id)
        with PolicyReader(policy_db) as reader:
            assert reader.selected(analysis.account_id, clock.instant) == initial
            print("unapproved change: old approved revision remains effective")
        second_approval = authority.approve(successor, scope=analysis.account_id,
                                            effective_at=NOW + timedelta(minutes=2))
        operator.apply(second_approval)
    with PolicyEvaluator(policy_db, clock) as reopened:
        reproduced = reopened.replay(recorded.evaluation_id)
        assert reproduced == recorded
        assert reopened.get_revision(initial.revision_id).source == source
        print(f"reopened replay: {reproduced.report.policy_version}, "
              f"revision={reproduced.revision_id}, identical={reproduced == recorded}")


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        run_example(Path(directory))
