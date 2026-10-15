"""Public release metadata never exposes environment values or credentials."""
import pytest


def test_release_metadata_is_explicit_about_missing_revision():
    from greenhome.release_metadata import release_metadata
    result = release_metadata({})
    assert result == {
        "name": "GreenHome Advisor",
        "version": "2026.10",
        "revision": None,
        "environment": "local",
    }


def test_release_metadata_reports_valid_deployment_revision_only():
    from greenhome.release_metadata import release_metadata
    sha = "a" * 40
    assert release_metadata({"VERCEL": "1", "VERCEL_GIT_COMMIT_SHA": sha}) == {
        "name": "GreenHome Advisor", "version": "2026.10",
        "revision": sha, "environment": "hosted",
    }


@pytest.mark.parametrize("invalid", ["private-token-value", "a" * 41, "https://user:secret@example.com"])
def test_release_metadata_does_not_echo_untrusted_revision(invalid):
    from greenhome.release_metadata import release_metadata
    result = release_metadata({"VERCEL_GIT_COMMIT_SHA": invalid, "DATABASE_URL": "DO-NOT-ECHO"})
    assert result["revision"] is None
    assert invalid not in str(result)
    assert "DO-NOT-ECHO" not in str(result)
