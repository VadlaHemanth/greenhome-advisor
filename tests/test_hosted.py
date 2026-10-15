"""Hosted configuration requires durable storage and explicit trusted origins."""
import pytest


def test_hosted_configuration_is_noop_for_local_development():
    from greenhome.hosted import hosted_environment
    assert hosted_environment({}) == {}


def test_hosted_configuration_refuses_ephemeral_or_missing_database():
    from greenhome.hosted import hosted_environment
    for database in (None, "sqlite:////tmp/unsafe.db", "http://example.com"):
        env = {"VERCEL": "1", "VERCEL_URL": "greenhome-preview.vercel.app"}
        if database:
            env["DATABASE_URL"] = database
        with pytest.raises(RuntimeError, match="persistent PostgreSQL"):
            hosted_environment(env)


def test_hosted_configuration_pins_domains_and_defaults_local_explanation():
    from greenhome.hosted import hosted_environment
    result = hosted_environment({
        "VERCEL": "1", "VERCEL_URL": "greenhome-preview.vercel.app",
        "VERCEL_PROJECT_PRODUCTION_URL": "greenhome-advisor.vercel.app",
        "DATABASE_URL": "postgresql://user:private@db.example/db?sslmode=require",
    })
    assert result["GREENHOME_PUBLIC_MODE"] == "true"
    assert result["GREENHOME_LIVE_LLM"] == "false"
    assert result["GREENHOME_WORKSPACE_DATABASE_URL"].startswith("postgresql+psycopg://")
    assert result["GREENHOME_PROVIDER_BUDGET_DATABASE_URL"] == result["GREENHOME_WORKSPACE_DATABASE_URL"]
    assert set(result["GREENHOME_ALLOWED_HOSTS"].split(",")) == {
        "greenhome-preview.vercel.app", "greenhome-advisor.vercel.app"
    }
    assert set(result["GREENHOME_ALLOWED_ORIGINS"].split(",")) == {
        "https://greenhome-preview.vercel.app", "https://greenhome-advisor.vercel.app"
    }


@pytest.mark.parametrize("domain", ["*", "https://bad.example/path", "good.example,evil.example", "user@host.example", "localhost"])
def test_hosted_configuration_rejects_untrusted_host_shapes(domain):
    from greenhome.hosted import hosted_environment
    with pytest.raises(RuntimeError, match="hostname"):
        hosted_environment({"VERCEL": "1", "VERCEL_URL": domain,
                            "DATABASE_URL": "postgresql://u:p@db.example/db"})


def test_hosted_error_never_echoes_database_credentials():
    from greenhome.hosted import hosted_environment
    with pytest.raises(RuntimeError) as caught:
        hosted_environment({"VERCEL": "1", "VERCEL_URL": "valid.vercel.app",
                            "DATABASE_URL": "https://user:DO-NOT-ECHO@invalid/db"})
    assert "DO-NOT-ECHO" not in str(caught.value)


@pytest.mark.parametrize("scheme", ["POSTGRESQL", "Postgres", "POSTGRESQL+PSYCOPG"])
def test_hosted_normalizes_driver_without_altering_credentials(scheme):
    from greenhome.hosted import hosted_environment
    result = hosted_environment({
        "VERCEL": "1", "VERCEL_URL": "valid.vercel.app",
        "DATABASE_URL": f"{scheme}://User:CaseSensitive@db.example/Database?sslmode=require",
    })
    assert result["GREENHOME_WORKSPACE_DATABASE_URL"] == "postgresql+psycopg://User:CaseSensitive@db.example/Database?sslmode=require"
