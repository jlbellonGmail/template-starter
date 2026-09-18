from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_f14_parallel_lifecycle_governance_and_safe_cleanup_contract():
    schema = (ROOT / ".agentic" / "schemas" / "unit-identity.schema.json").read_text()
    lifecycle = (ROOT / "scripts" / "unit-lifecycle.ps1").read_text()
    cleanup = (ROOT / "scripts" / "cleanup-work-unit.ps1").read_text()
    gate = (ROOT / "scripts" / "complete-approved-pr.ps1").read_text()
    for field in ("unitId", "canonicalSlug", "baseCommit", "currentHead"):
        assert field in schema
    for action in ("inspect", "reconcile", "cleanup", "retry-cleanup"):
        assert action in lifecycle
    assert "staleEvidence" in lifecycle
    assert "scoped-authorization" in lifecycle
    assert "git merge --no-edit origin/develop" in lifecycle
    assert "ours" not in lifecycle.lower() and "theirs" not in lifecycle.lower()
    assert "B_RESIDUAL_WINDOWS_EMPTY" in cleanup
    assert "C_RESIDUAL_WINDOWS_CONTENT" in cleanup
    assert "prune" in cleanup.lower()
    assert "no se borra contenido" in cleanup.lower()
    for field in ("SingleMaintainer", "MultiMaintainer", "IndependentReviewPath", "IntegrityEvidencePath"):
        assert field in gate
    assert "no se fabrica self-review" in gate
