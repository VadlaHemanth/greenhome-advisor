import asyncio

import pytest
from greenhome.security import AuthenticatedGatewayContext


@pytest.mark.parametrize("peer,token,active,expected", [
    ("127.0.0.1", b"x"*40, True, True),
    ("::1", b"x"*40, True, True),
    ("203.0.113.1", b"x"*40, True, False),
    ("127.0.0.1", b"spoofed", True, False),
    ("127.0.0.1", b"", True, False),
    ("127.0.0.1", b"x"*40, False, False),
])
def test_only_real_loopback_and_configured_token_are_trusted(peer, token, active, expected):
    captured = []
    async def application(scope, receive, send):
        captured.append(scope["greenhome.authenticated_gateway"])
    middleware = AuthenticatedGatewayContext(application, "x"*40, active)
    scope = {"type":"http", "client":(peer,123), "headers":[
        (b"x-greenhome-gateway",token),
        (b"x-forwarded-proto", b"https"),
        (b"x-forwarded-for", b"127.0.0.1"),
    ]}
    asyncio.run(middleware(scope,None,None))
    assert captured == [expected]
