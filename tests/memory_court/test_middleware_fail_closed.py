"""Memory Court middleware fail-closed vectors (day-2 scaffold).

Co-authored in the three-brain holding-hands session (Kimi session-14).
ROADMAP: these encode the fail-closed contract of
docs/memory-court/MEMORY_COURT_DAY2.md before the middleware exists.
Idiom: pytest.mark.skip (unexecutable ROADMAP skeletons, not executed
known-failure tests); the decorator is removed when the middleware and the
day2 harness land, and unskipping is the gate that fail-closed was
implemented rather than asserted.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="ROADMAP: day-2 middleware and day2 harness are not implemented; "
    "unskip per docs/memory-court/MEMORY_COURT_DAY2.md"
)


@pytest.fixture
def day2():
    raise NotImplementedError("day-2 harness not implemented (ROADMAP)")


def test_unauthenticated_caller(day2):
    outcome = day2.invoke("unauthenticated_caller")
    assert outcome.status == 401
    assert outcome.receipt_kind is None
    assert outcome.dependent_writes == []


def test_wrong_tenant(day2):
    outcome = day2.invoke("wrong_tenant")
    assert outcome.status == 403
    assert outcome.receipt_kind is None
    assert outcome.dependent_writes == []


def test_unknown_signer_key(day2):
    outcome = day2.invoke("unknown_signer_key")
    assert outcome.status == 503
    assert outcome.receipt_kind is None
    assert outcome.dependent_writes == []


def test_trust_root_version_unknown(day2):
    outcome = day2.invoke("trust_root_version_unknown")
    assert outcome.status == 503
    assert outcome.receipt_kind is None
    assert outcome.dependent_writes == []


def test_dirty_or_unknown_build(day2):
    outcome = day2.invoke("dirty_or_unknown_build")
    assert outcome.status == 503
    assert outcome.receipt_kind is None
    assert outcome.dependent_writes == []


def test_adjudication_abstain(day2):
    outcome = day2.invoke("adjudication_abstain")
    assert outcome.status == 200
    assert outcome.receipt_kind == "abstention"
    assert outcome.committed_receipt is not None
    assert outcome.dependent_writes == []


def test_khipu_write_failure(day2):
    outcome = day2.invoke("khipu_write_failure")
    assert outcome.status == 503
    assert outcome.receipt_kind == "signed-uncommitted"
    assert outcome.committed_receipt is None
    assert outcome.dependent_writes == []


def test_signer_unavailable(day2):
    outcome = day2.invoke("signer_unavailable")
    assert outcome.status == 503
    assert outcome.receipt_kind is None
    assert outcome.dependent_writes == []
