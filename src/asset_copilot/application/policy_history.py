"""Append-only policy revisions, scoped approval and recorded official evaluations.

The trusted local operator process alone receives the signing key and PolicyOperator.
Evaluation/AI code receives PolicyEvaluator only. SQLite file ACLs must separate
those processes in deployment; same-OS-identity arbitrary Python is outside this
candidate's authority boundary.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
from pathlib import Path
import sqlite3
from uuid import uuid4

from asset_copilot.application.policy_config import parse_portfolio_policy_config
from asset_copilot.application.policy_history_codec import dumps, loads
from asset_copilot.application.us_portfolio_analytics import PortfolioAnalysis
from asset_copilot.application.us_portfolio_policy import PortfolioPolicyEngine
from asset_copilot.domain.policy import ETFClassification, PortfolioPolicyConfig, PortfolioPolicyReport


class PolicyConflict(ValueError):
    """Stale head, duplicate version, or conflicting request."""


class PolicyUnavailable(ValueError):
    """No single approved revision applies at the requested time."""


class PolicyApprovalError(ValueError):
    """Approval evidence is absent, altered, stale, or out of scope."""


@dataclass(frozen=True, slots=True)
class PolicyRevision:
    revision_id: str
    scope: str
    content_id: str
    source_sha256: str
    policy_version: str
    previous_revision_id: str | None
    reason: str
    recorded_at: datetime
    source: bytes
    config: PortfolioPolicyConfig


@dataclass(frozen=True, slots=True)
class ApprovalEvidence:
    revision_id: str
    content_id: str
    scope: str
    effective_at: datetime
    approved_at: datetime
    signature: str


@dataclass(frozen=True, slots=True)
class RecordedEvaluation:
    evaluation_id: str
    revision_id: str
    content_id: str
    scope: str
    evaluated_at: datetime
    recorded_at: datetime
    implementation_id: str
    analysis: PortfolioAnalysis
    classifications: tuple[ETFClassification, ...]
    report: PortfolioPolicyReport


def _instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _hash(value: bytes) -> str:
    return sha256(value).hexdigest()


def _content_id(source: bytes, config_json: str) -> str:
    return _hash(source + b"\0" + config_json.encode("utf-8"))


def _approval_message(revision_id: str, content_id: str, scope: str,
                      effective_at: datetime, approved_at: datetime) -> bytes:
    return dumps((revision_id, content_id, scope, effective_at, approved_at)).encode()


def _db(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.row_factory = sqlite3.Row
    return connection


_SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_revisions (
    revision_id TEXT PRIMARY KEY, scope TEXT NOT NULL, content_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL, policy_version TEXT NOT NULL,
    previous_revision_id TEXT REFERENCES policy_revisions(revision_id),
    reason TEXT NOT NULL, recorded_at TEXT NOT NULL, source BLOB NOT NULL,
    config_json TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE,
    request_sha256 TEXT NOT NULL, UNIQUE(scope, policy_version)
);
CREATE TABLE IF NOT EXISTS policy_approvals (
    revision_id TEXT PRIMARY KEY REFERENCES policy_revisions(revision_id),
    scope TEXT NOT NULL, content_id TEXT NOT NULL, effective_at TEXT NOT NULL,
    approved_at TEXT NOT NULL, signature TEXT NOT NULL,
    UNIQUE(scope, effective_at)
);
CREATE TABLE IF NOT EXISTS policy_evaluations (
    evaluation_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES policy_approvals(revision_id),
    content_id TEXT NOT NULL, scope TEXT NOT NULL, evaluated_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL, implementation_id TEXT NOT NULL,
    analysis_json TEXT NOT NULL, classifications_json TEXT NOT NULL,
    report_json TEXT NOT NULL, evidence_sha256 TEXT NOT NULL
);
""" + "\n".join(
    f"CREATE TRIGGER IF NOT EXISTS {table}_{action.lower()}_blocked "
    f"BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable policy evidence'); END;"
    for table in ("policy_revisions", "policy_approvals", "policy_evaluations")
    for action in ("UPDATE", "DELETE")
)


def _revision(row: sqlite3.Row) -> PolicyRevision:
    raw = bytes(row["source"])
    config = parse_portfolio_policy_config(raw)
    if _hash(raw) != row["source_sha256"] or dumps(config) != row["config_json"] \
            or _content_id(raw, row["config_json"]) != row["content_id"]:
        raise ValueError("stored policy revision has changed")
    return PolicyRevision(row["revision_id"], row["scope"], row["content_id"],
                          row["source_sha256"], row["policy_version"],
                          row["previous_revision_id"], row["reason"],
                          datetime.fromisoformat(row["recorded_at"]), raw, config)


class PolicyReader:
    """Read-only policy view. Opens SQLite in mode=ro and exposes no write method."""

    def __init__(self, path: str | Path) -> None:
        self._connection = _db(Path(path), readonly=True)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def get_revision(self, revision_id: str) -> PolicyRevision:
        row = self._connection.execute(
            "SELECT * FROM policy_revisions WHERE revision_id=?", (revision_id,)).fetchone()
        if row is None:
            raise PolicyUnavailable("policy revision is absent")
        return _revision(row)

    def selected(self, scope: str, as_of: datetime) -> PolicyRevision:
        _required(scope, "scope")
        point = _instant(as_of).isoformat()
        rows = self._connection.execute("""
            SELECT r.* FROM policy_revisions r JOIN policy_approvals a
            ON a.revision_id=r.revision_id WHERE a.scope=? AND a.effective_at<=?
            AND a.approved_at<=? ORDER BY a.effective_at DESC LIMIT 2
        """, (scope, point, point)).fetchall()
        if not rows:
            raise PolicyUnavailable("no approved policy applies at this time")
        if len(rows) > 1:
            times = self._connection.execute("""
                SELECT effective_at FROM policy_approvals WHERE revision_id IN (?, ?)
            """, (rows[0]["revision_id"], rows[1]["revision_id"])).fetchall()
            if times[0][0] == times[1][0]:
                raise PolicyUnavailable("ambiguous approved policy")
        return _revision(rows[0])


class PolicyApprovalAuthority:
    """Trusted operator entry point; possession of the external key is required."""

    def __init__(self, signing_key: bytes, clock) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("approval key needs at least 32 bytes")
        self._key = signing_key
        self._clock = clock

    def approve(self, revision: PolicyRevision, *, scope: str,
                effective_at: datetime) -> ApprovalEvidence:
        if not isinstance(revision, PolicyRevision) or revision.scope != scope:
            raise PolicyApprovalError("approval scope differs from revision")
        approved_at = _instant(self._clock())
        effective_at = _instant(effective_at)
        if effective_at < approved_at or approved_at < revision.recorded_at:
            raise PolicyApprovalError("approval cannot apply retrospectively")
        message = _approval_message(revision.revision_id, revision.content_id,
                                    scope, effective_at, approved_at)
        signature = hmac.digest(self._key, message, "sha256").hex()
        return ApprovalEvidence(revision.revision_id, revision.content_id, scope,
                                effective_at, approved_at, signature)


class PolicyOperator(PolicyReader):
    """Trusted local write path; optimistic head checks and SQLite transactions."""

    def __init__(self, path: str | Path, verification_key: bytes, clock) -> None:
        if not isinstance(verification_key, bytes) or len(verification_key) < 32:
            raise ValueError("approval key needs at least 32 bytes")
        self._path = Path(path)
        self._connection = _db(self._path)
        self._connection.executescript(_SCHEMA)
        self._key = verification_key
        self._clock = clock

    def propose(self, source: bytes, *, scope: str, reason: str, request_id: str,
                expected_revision_id: str | None) -> PolicyRevision:
        _required(scope, "scope")
        _required(reason, "reason")
        _required(request_id, "request_id")
        config = parse_portfolio_policy_config(source)
        config_json = dumps(config)
        fingerprint = _hash(dumps((scope, source.hex(), reason,
                                   expected_revision_id)).encode())
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            repeated = connection.execute("SELECT * FROM policy_revisions WHERE request_id=?",
                                          (request_id,)).fetchone()
            if repeated is not None:
                if repeated["request_sha256"] != fingerprint:
                    raise PolicyConflict("request_id was reused with different contents")
                result = _revision(repeated)
            else:
                previous = connection.execute(
                    "SELECT revision_id FROM policy_revisions WHERE scope=? ORDER BY rowid DESC LIMIT 1",
                    (scope,)).fetchone()
                head = previous[0] if previous else None
                if head != expected_revision_id:
                    raise PolicyConflict("policy head changed since proposal")
                revision_id = uuid4().hex
                recorded_at = _instant(self._clock())
                try:
                    connection.execute("""INSERT INTO policy_revisions VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (revision_id, scope, _content_id(source, config_json), _hash(source),
                         config.policy_version, head, reason, recorded_at.isoformat(),
                         source, config_json, request_id, fingerprint))
                except sqlite3.IntegrityError as error:
                    if error.sqlite_errorname in ("SQLITE_CONSTRAINT_UNIQUE", "SQLITE_CONSTRAINT_PRIMARYKEY"):
                        raise PolicyConflict("policy version or request conflicts") from error
                    raise
                result = self.get_revision(revision_id)
            connection.execute("COMMIT")
            return result
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def apply(self, evidence: ApprovalEvidence) -> PolicyRevision:
        if not isinstance(evidence, ApprovalEvidence):
            raise PolicyApprovalError("signed approval evidence is required")
        try:
            revision = self.get_revision(evidence.revision_id)
        except PolicyUnavailable as error:
            raise PolicyApprovalError("approval revision is absent") from error
        if evidence.scope != revision.scope or evidence.content_id != revision.content_id:
            raise PolicyApprovalError("approval target differs from stored revision")
        approved_at, effective_at = _instant(evidence.approved_at), _instant(evidence.effective_at)
        message = _approval_message(revision.revision_id, revision.content_id,
                                    revision.scope, effective_at, approved_at)
        if not hmac.compare_digest(hmac.digest(self._key, message, "sha256").hex(),
                                   evidence.signature):
            raise PolicyApprovalError("approval signature is invalid")
        now = _instant(self._clock())
        if approved_at < revision.recorded_at or approved_at > now:
            raise PolicyApprovalError("approval cannot apply retrospectively")
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute("SELECT * FROM policy_approvals WHERE revision_id=?",
                                          (revision.revision_id,)).fetchone()
            if existing:
                if (existing["scope"], existing["content_id"], existing["effective_at"],
                    existing["approved_at"], existing["signature"]) != (
                        evidence.scope, evidence.content_id, effective_at.isoformat(),
                        approved_at.isoformat(), evidence.signature):
                    raise PolicyConflict("revision already has different approval")
            else:
                if effective_at < now:
                    raise PolicyApprovalError("approval cannot apply retrospectively")
                latest = connection.execute(
                    "SELECT revision_id FROM policy_revisions WHERE scope=? ORDER BY rowid DESC LIMIT 1",
                    (revision.scope,)).fetchone()
                if latest is None or latest[0] != revision.revision_id:
                    raise PolicyConflict("cannot apply a superseded revision")
                last = connection.execute(
                    "SELECT effective_at FROM policy_approvals WHERE scope=? ORDER BY effective_at DESC LIMIT 1",
                    (revision.scope,)).fetchone()
                if last and effective_at.isoformat() <= last[0]:
                    raise PolicyConflict("effective time must follow prior application")
                try:
                    connection.execute("INSERT INTO policy_approvals VALUES (?, ?, ?, ?, ?, ?)",
                                       (revision.revision_id, revision.scope, revision.content_id,
                                        effective_at.isoformat(), approved_at.isoformat(),
                                        evidence.signature))
                except sqlite3.IntegrityError as error:
                    if error.sqlite_errorname in ("SQLITE_CONSTRAINT_UNIQUE", "SQLITE_CONSTRAINT_PRIMARYKEY"):
                        raise PolicyConflict("approval conflicts with existing application") from error
                    raise
            connection.execute("COMMIT")
            return revision
        except BaseException:
            connection.execute("ROLLBACK")
            raise


def _implementation_id() -> str:
    from asset_copilot.application import policy_config, us_portfolio_policy
    from asset_copilot.domain import policy
    from asset_copilot.portfolio import calculator
    import sys
    modules = (policy_config, us_portfolio_policy, policy, calculator)
    contents = b"".join(module.__name__.encode() + b"\0" +
                        Path(module.__file__).read_bytes() for module in modules)
    return f"py{sys.version_info.major}.{sys.version_info.minor}:sha256:{_hash(contents)}"


class PolicyEvaluator(PolicyReader):
    """Evaluation path can append evidence, but its SQL authorizer denies policy writes."""

    def __init__(self, path: str | Path, clock) -> None:
        self._connection = _db(Path(path))
        self._clock = clock

        def authorize(action, table, _column, _database, _source):
            if action == sqlite3.SQLITE_INSERT and table == "policy_evaluations":
                return sqlite3.SQLITE_OK
            if action in (sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT,
                          sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_TRANSACTION):
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        self._connection.set_authorizer(authorize)

    def evaluate(self, analysis: PortfolioAnalysis, *,
                 classifications: tuple[ETFClassification, ...] = ()) -> RecordedEvaluation:
        if not isinstance(analysis, PortfolioAnalysis):
            raise TypeError("analysis must be PortfolioAnalysis")
        if not isinstance(classifications, tuple):
            raise TypeError("classifications must be a tuple")
        now = _instant(self._clock())
        if now < _instant(analysis.evaluated_at):
            raise ValueError("evaluation cannot be recorded before its reference time")
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            # Keep selection and recording on one SQLite write snapshot. Another
            # operator cannot apply a policy at this boundary between the two.
            revision = self.selected(analysis.account_id, analysis.evaluated_at)
            report = PortfolioPolicyEngine(revision.config).evaluate(
                analysis, etf_classifications=classifications)
            record = RecordedEvaluation(uuid4().hex, revision.revision_id,
                                        revision.content_id, revision.scope,
                                        _instant(analysis.evaluated_at), now,
                                        _implementation_id(), analysis, classifications, report)
            parts = (dumps(analysis), dumps(classifications), dumps(report))
            digest = _hash(dumps((record.evaluation_id, revision.revision_id,
                                  revision.content_id, record.scope, record.evaluated_at,
                                  record.recorded_at, record.implementation_id, parts)).encode())
            connection.execute("""INSERT INTO policy_evaluations VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.evaluation_id, record.revision_id, record.content_id, record.scope,
                 record.evaluated_at.isoformat(), record.recorded_at.isoformat(),
                 record.implementation_id, *parts, digest))
            connection.execute("COMMIT")
            return record
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def replay(self, evaluation_id: str) -> RecordedEvaluation:
        row = self._connection.execute("SELECT * FROM policy_evaluations WHERE evaluation_id=?",
                                       (evaluation_id,)).fetchone()
        if row is None:
            raise PolicyUnavailable("evaluation record is absent")
        parts = (row["analysis_json"], row["classifications_json"], row["report_json"])
        digest = _hash(dumps((row["evaluation_id"], row["revision_id"], row["content_id"],
                              row["scope"], datetime.fromisoformat(row["evaluated_at"]),
                              datetime.fromisoformat(row["recorded_at"]),
                              row["implementation_id"], parts)).encode())
        if digest != row["evidence_sha256"]:
            raise ValueError("stored evaluation evidence has changed")
        revision = self.get_revision(row["revision_id"])
        if revision.content_id != row["content_id"] or revision.scope != row["scope"]:
            raise ValueError("evaluation refers to different policy content")
        if row["implementation_id"] != _implementation_id():
            raise PolicyUnavailable("evaluator implementation differs from recorded version")
        analysis, classifications, report = map(loads, parts)
        if analysis.account_id != row["scope"] or _instant(analysis.evaluated_at) != \
                datetime.fromisoformat(row["evaluated_at"]) or \
                report.account_id != row["scope"] or \
                _instant(report.evaluated_at) != datetime.fromisoformat(row["evaluated_at"]) or \
                self.selected(row["scope"], analysis.evaluated_at).revision_id != revision.revision_id:
            raise ValueError("evaluation identity or applied policy differs")
        reproduced = PortfolioPolicyEngine(revision.config).evaluate(
            analysis, etf_classifications=classifications)
        if reproduced != report:
            raise ValueError("recorded evaluation cannot be reproduced")
        return RecordedEvaluation(row["evaluation_id"], row["revision_id"],
                                  row["content_id"], row["scope"],
                                  datetime.fromisoformat(row["evaluated_at"]),
                                  datetime.fromisoformat(row["recorded_at"]),
                                  row["implementation_id"], analysis,
                                  classifications, report)
