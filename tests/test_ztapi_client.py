import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer
from collections.abc import Callable, Coroutine
from typing import Any
from ztapi_client import ZeroTierApiClient


class TestZeroTierApiClient:
    @pytest_asyncio.fixture
    async def mock_server(  # type: ignore[misc]
        self, aiohttp_server: Callable[[web.Application], Coroutine[Any, Any, TestServer]]
    ) -> TestServer:
        app = web.Application()
        app.router.add_get("/api/v1/network/{network_id}", self.handle_get_network)
        app.router.add_get("/api/v1/network/{network_id}/member", self.handle_get_members)
        app.router.add_get("/api/v1/network/{network_id}/member/{member_id}", self.handle_get_member)
        app.router.add_post("/api/v1/network/{network_id}/member/{member_id}", self.handle_tag_member)
        server = await aiohttp_server(app)
        return server

    async def handle_get_network(self, request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization")
        if auth != "token test-token":
            return web.Response(status=401)
        return web.json_response({
            "id": "abc123",
            "tagsByName": {
                "status": {
                    "id": 1,
                    "default": 0,
                    "enums": {"allowed": 0, "blocked": 1}
                }
            }
        })

    async def handle_get_members(self, request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization")
        if auth != "token test-token":
            return web.Response(status=401)
        return web.json_response([
            {
                "config": {"id": "member1", "tags": [[1, 0]]},
                "physicalAddress": "192.168.1.1",
                "lastSeen": 1700000000000
            },
            {
                "config": {"id": "member2", "tags": [[1, 1]]},
                "physicalAddress": "192.168.1.2",
                "lastSeen": 1700000001000
            }
        ])

    async def handle_get_member(self, request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization")
        if auth != "token test-token":
            return web.Response(status=401)
        member_id = request.match_info["member_id"]
        if member_id == "notfound":
            return web.Response(status=404)
        return web.json_response({
            "config": {"id": member_id, "tags": [[1, 0]]},
            "physicalAddress": "192.168.1.1",
            "lastSeen": 1700000000000
        })

    async def handle_tag_member(self, request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization")
        if auth != "token test-token":
            return web.Response(status=401)
        return web.json_response({"status": "ok"})

    @pytest.mark.asyncio
    async def test_get_network_success(self, mock_server: TestServer) -> None:
        async with ZeroTierApiClient("test-token") as client:
            client._baseUrl = f"http://{mock_server.host}:{mock_server.port}/api/v1"
            network = await client.get_network("abc123")
            assert network is not None
            assert network["id"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_network_unauthorized(self, mock_server: TestServer) -> None:
        async with ZeroTierApiClient("wrong-token") as client:
            client._baseUrl = f"http://{mock_server.host}:{mock_server.port}/api/v1"
            network = await client.get_network("abc123")
            assert network is None

    @pytest.mark.asyncio
    async def test_get_members_success(self, mock_server: TestServer) -> None:
        async with ZeroTierApiClient("test-token") as client:
            client._baseUrl = f"http://{mock_server.host}:{mock_server.port}/api/v1"
            members = await client.get_members("abc123")
            assert members is not None
            assert len(members) == 2

    @pytest.mark.asyncio
    async def test_get_member_success(self, mock_server: TestServer) -> None:
        async with ZeroTierApiClient("test-token") as client:
            client._baseUrl = f"http://{mock_server.host}:{mock_server.port}/api/v1"
            member = await client.get_member("abc123", "member1")
            assert member is not None
            assert member["config"]["id"] == "member1"

    @pytest.mark.asyncio
    async def test_get_member_not_found(self, mock_server: TestServer) -> None:
        async with ZeroTierApiClient("test-token") as client:
            client._baseUrl = f"http://{mock_server.host}:{mock_server.port}/api/v1"
            member = await client.get_member("abc123", "notfound")
            assert member is None

    @pytest.mark.asyncio
    async def test_tag_member(self, mock_server: TestServer) -> None:
        async with ZeroTierApiClient("test-token") as client:
            client._baseUrl = f"http://{mock_server.host}:{mock_server.port}/api/v1"
            network = {
                "id": "abc123",
                "tagsByName": {
                    "status": {"id": 1, "enums": {"allowed": 0, "blocked": 1}}
                }
            }
            member = {"config": {"id": "member1", "tags": [[1, 0]]}}
            # Should not raise
            await client.tag_member(network, member, "status", "blocked")
