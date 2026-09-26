"""P4-06/07 persistence, approval and historical evaluation contracts."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sqlite3

import pytest

from asset_copilot.application.policy_config import parse_portfolio_policy_config
from asset_copilot.application.policy_history import (
    ApprovalEvidence, PolicyApprovalAuthority, PolicyApprovalError, PolicyConflict,
    PolicyEvaluator, PolicyOperator, PolicyReader, PolicyUnavailable,
)
from asset_copilot.domain.policy import ETFClassification, ETFGroup
from test_us_portfolio_policy import NOW, complete_analysis, complete_classifications

KEY = b"synthetic-test-approval-key-32-bytes!!"
SOURCE = (Path(__file__).resolve().parents[1] / "config/us_portfolio_policy.toml").read_bytes()


class Clock:
    def __init__(self, instant):
        self.instant = instant

    def __call__(self):
        return self.instant


def setup(tmp_path):
    clock = Clock(NOW - timedelta(days=1))
    path = tmp_path / "policy.sqlite"
    operator = PolicyOperator(path, KEY, clock)
    authority = PolicyApprovalAuthority(KEY, clock)
    return path, clock, operator, authority


def first(operator, authority):
    revision = operator.propose(SOURCE, scope="account", reason="synthetic initial",
                                request_id="initial", expected_revision_id=None)
    effective = NOW - timedelta(hours=1)
    evidence = authority.approve(revision, scope="account", effective_at=effective)
    operator.apply(evidence)
    return revision, evidence


def changed_source(version="followup-v2"):
    return SOURCE.replace(b'policy_version = "initial-v1"',
                          f'policy_version = "{version}"'.encode()).replace(
        b'individual_position_max = 15', b'individual_position_max = 14')


def test_source_config_decimal_time_round_trip_and_idempotence(tmp_path):
    path, clock, operator, authority = setup(tmp_path)
    revision, evidence = first(operator, authority)
    assert revision.source == SOURCE
    assert revision.config == parse_portfolio_policy_config(SOURCE)
    assert str(revision.config.individual_stock_breach_ratio) == "0.15"
    assert operator.propose(SOURCE, scope="account", reason="synthetic initial",
                            request_id="initial", expected_revision_id=None) == revision
    assert operator.apply(evidence) == revision
    with pytest.raises(PolicyConflict):
        operator.propose(changed_source(), scope="account", reason="synthetic initial",
                         request_id="initial", expected_revision_id=None)
    with pytest.raises(PolicyConflict):
        operator.propose(changed_source("initial-v1"), scope="account", reason="changed",
                         request_id="same-version", expected_revision_id=revision.revision_id)
    operator.close()
    with PolicyReader(path) as reader:
        assert reader.get_revision(revision.revision_id) == revision
        assert reader.selected("account", NOW - timedelta(hours=1)) == revision
        with pytest.raises(PolicyUnavailable):
            reader.selected("account", NOW - timedelta(hours=1, microseconds=1))
    assert evidence.approved_at == revision.recorded_at


def test_stale_concurrent_changes_and_failed_transaction(tmp_path):
    path, clock, first_writer, authority = setup(tmp_path)
    initial, _ = first(first_writer, authority)
    second_writer = PolicyOperator(path, KEY, clock)
    successor = first_writer.propose(changed_source(), scope="account", reason="change",
                                     request_id="second", expected_revision_id=initial.revision_id)
    with pytest.raises(PolicyConflict):
        second_writer.propose(changed_source("third-v3"), scope="account", reason="stale",
                              request_id="third", expected_revision_id=initial.revision_id)
    with pytest.raises(PolicyConflict):
        first_writer.propose(changed_source("initial-v1"), scope="account", reason="overwrite",
                             request_id="overwrite", expected_revision_id=successor.revision_id)
    # A database-side failure must roll back the entire proposal.
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER fail_revision BEFORE INSERT ON policy_revisions
                            WHEN NEW.request_id='fail' BEGIN SELECT RAISE(ABORT, 'injected'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        first_writer.propose(changed_source("failed-v3"), scope="account", reason="failure",
                             request_id="fail", expected_revision_id=successor.revision_id)
    assert first_writer.get_revision(successor.revision_id) == successor
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM policy_revisions").fetchone()[0] == 2
    first_writer.close()
    second_writer.close()


def test_approval_forgery_reuse_tamper_and_atomic_failure(tmp_path):
    path, clock, operator, authority = setup(tmp_path)
    initial, proof = first(operator, authority)
    next_revision = operator.propose(changed_source(), scope="account", reason="change",
                                     request_id="second", expected_revision_id=initial.revision_id)
    with pytest.raises(PolicyApprovalError):
        operator.apply(replace(proof, revision_id=next_revision.revision_id,
                               content_id=next_revision.content_id))
    with pytest.raises(PolicyApprovalError):
        operator.apply(replace(proof, scope="another-account"))
    with pytest.raises(PolicyApprovalError):
        operator.apply(replace(proof, effective_at=proof.effective_at + timedelta(seconds=1)))
    with pytest.raises(PolicyApprovalError):
        operator.apply(ApprovalEvidence(next_revision.revision_id, next_revision.content_id,
                                        "account", NOW, NOW, "fake"))
    wrong_key_proof = PolicyApprovalAuthority(
        b"different-synthetic-key-32-bytes!!", clock).approve(
            next_revision, scope="account", effective_at=NOW)
    with pytest.raises(PolicyApprovalError):
        operator.apply(wrong_key_proof)
    with pytest.raises(PolicyApprovalError):
        PolicyApprovalAuthority(b"different-synthetic-key-32-bytes!!", clock).approve(
            next_revision, scope="other", effective_at=NOW)
    next_proof = authority.approve(next_revision, scope="account", effective_at=NOW)
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER fail_approval BEFORE INSERT ON policy_approvals
                            WHEN NEW.revision_id='%s' BEGIN SELECT RAISE(ABORT, 'injected'); END"""
                           % next_revision.revision_id)
    with pytest.raises(sqlite3.IntegrityError):
        operator.apply(next_proof)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM policy_approvals").fetchone()[0] == 1
    operator.close()


def test_effective_boundaries_no_backdating_and_missing_policy(tmp_path):
    path, clock, operator, authority = setup(tmp_path)
    with PolicyReader(path) as reader:
        with pytest.raises(PolicyUnavailable):
            reader.selected("account", NOW)
    clock.instant = NOW
    with PolicyEvaluator(path, clock) as evaluator:
        with pytest.raises(PolicyUnavailable):
            evaluator.evaluate(complete_analysis(),
                               classifications=complete_classifications(complete_analysis()))
    clock.instant = NOW - timedelta(days=1)
    initial, _ = first(operator, authority)
    successor = operator.propose(changed_source(), scope="account", reason="later",
                                 request_id="second", expected_revision_id=initial.revision_id)
    clock.instant = NOW
    with pytest.raises(PolicyApprovalError):
        authority.approve(successor, scope="account", effective_at=NOW - timedelta(seconds=1))
    boundary = NOW + timedelta(seconds=1)
    proof = authority.approve(successor, scope="account", effective_at=boundary)
    operator.apply(proof)
    with PolicyReader(path) as reader:
        assert reader.selected("account", boundary - timedelta(microseconds=1)) == initial
        assert reader.selected("account", boundary) == successor
        assert reader.selected("account", boundary + timedelta(microseconds=1)) == successor
    clock.instant = boundary + timedelta(seconds=1)
    with pytest.raises(PolicyApprovalError):
        operator.apply(replace(proof, revision_id="forged"))
    operator.close()


def test_evaluation_reopen_and_reader_cannot_write(tmp_path):
    path, clock, operator, authority = setup(tmp_path)
    initial, _ = first(operator, authority)
    data = complete_analysis()
    classifications = complete_classifications(data)
    clock.instant = NOW
    with PolicyEvaluator(path, clock) as evaluator:
        record = evaluator.evaluate(data, classifications=classifications)
        assert record.revision_id == initial.revision_id
        assert record.analysis == data
        with pytest.raises(sqlite3.DatabaseError):
            evaluator._connection.execute("INSERT INTO policy_approvals VALUES ('x','x','x','x','x','x')")
        with pytest.raises(sqlite3.DatabaseError):
            evaluator._connection.execute("DROP TABLE policy_approvals")
    successor = operator.propose(changed_source(), scope="account", reason="later",
                                 request_id="second", expected_revision_id=initial.revision_id)
    clock.instant = NOW + timedelta(seconds=1)
    proof = authority.approve(successor, scope="account", effective_at=NOW + timedelta(seconds=2))
    operator.apply(proof)
    operator.close()
    with PolicyEvaluator(path, clock) as reopened:
        assert reopened.replay(record.evaluation_id) == record
        assert reopened.get_revision(initial.revision_id).source == SOURCE
        clock.instant = NOW + timedelta(seconds=3)
        new_analysis = replace(data, evaluated_at=clock.instant)
        changed_classification = (ETFClassification("core", ETFGroup.GROWTH),
                                  ETFClassification("growth", ETFGroup.CORE))
        newer = reopened.evaluate(new_analysis, classifications=changed_classification)
        assert newer.revision_id == successor.revision_id
        assert newer.report != record.report
        assert reopened.replay(record.evaluation_id) == record
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO policy_revisions(revision_id) VALUES ('forged')")
    assert classifications == (ETFClassification("core", ETFGroup.CORE),
                               ETFClassification("growth", ETFGroup.GROWTH))


def test_evaluation_insert_failure_leaves_no_record(tmp_path):
    path, clock, operator, authority = setup(tmp_path)
    first(operator, authority)
    clock.instant = NOW
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER fail_evaluation BEFORE INSERT ON policy_evaluations
                            BEGIN SELECT RAISE(ABORT, 'injected'); END""")
    data = complete_analysis()
    with PolicyEvaluator(path, clock) as evaluator:
        with pytest.raises(sqlite3.IntegrityError):
            evaluator.evaluate(data, classifications=complete_classifications(data))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM policy_evaluations").fetchone()[0] == 0
    operator.close()
