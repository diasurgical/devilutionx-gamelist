import pathlib
import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, UTC
from ipaddress import IPv6Address
from bot_db import BotDatabase, adapt_datetime_iso


class TestAdaptDatetimeIso:
    def test_converts_datetime_to_iso_string(self) -> None:
        dt = datetime(2024, 1, 15, 10, 30, 45, tzinfo=UTC)
        result = adapt_datetime_iso(dt)
        assert result == "2024-01-15 10:30:45"

    def test_strips_timezone_info(self) -> None:
        dt = datetime(2024, 6, 20, 14, 0, 0, tzinfo=UTC)
        result = adapt_datetime_iso(dt)
        assert "+" not in result
        assert "Z" not in result


class TestBotDatabase:
    @pytest_asyncio.fixture
    async def db(self, tmp_path: pathlib.Path) -> AsyncGenerator[BotDatabase, None]:
        db_path = str(tmp_path / "test.db")
        async with BotDatabase(db_path) as db:
            yield db

    @pytest.mark.asyncio
    async def test_save_and_find_player_by_name(self, db: BotDatabase) -> None:
        ipv6 = IPv6Address("fd00::abcd:1234:5678")
        now = datetime.now(UTC).replace(tzinfo=None)
        await db.save_member_sighting(ipv6, "TestPlayer", now)

        results = await db.find_player_by_name("TestPlayer")
        assert len(results) == 1
        assert "TestPlayer" in results[0]

    @pytest.mark.asyncio
    async def test_find_player_case_insensitive(self, db: BotDatabase) -> None:
        ipv6 = IPv6Address("fd00::abcd:1234:5678")
        now = datetime.now(UTC).replace(tzinfo=None)
        await db.save_member_sighting(ipv6, "TestPlayer", now)

        results = await db.find_player_by_name("testplayer")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_find_player_not_found(self, db: BotDatabase) -> None:
        results = await db.find_player_by_name("NonExistent")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_save_and_find_game_by_name(self, db: BotDatabase) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await db.save_player_sighting("PlayerOne", "TestGame", now)

        results = await db.find_game_by_name("TestGame")
        assert len(results) == 1
        assert "PlayerOne" in results[0]

    @pytest.mark.asyncio
    async def test_player_sighting_updates_last_time(self, db: BotDatabase) -> None:
        first = datetime.now(UTC).replace(tzinfo=None)
        await db.save_player_sighting("Player", "Game", first)

        second = first + timedelta(minutes=5)
        await db.save_player_sighting("Player", "Game", second)

        results = await db.find_game_by_name("Game")
        # Should have 2 results (first and last timestamps)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_save_and_find_zt_member(self, db: BotDatabase) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await db.save_zt_member("abc123", "192.168.1.1", now, "allowed")

        result = await db.find_zt_member_by_id("abc123")
        assert "abc123" in result
        assert "192.168.1.1" in result
        assert "allowed" in result

    @pytest.mark.asyncio
    async def test_find_zt_member_not_found(self, db: BotDatabase) -> None:
        result = await db.find_zt_member_by_id("nonexistent")
        assert result == ""

    @pytest.mark.asyncio
    async def test_zt_member_without_ip(self, db: BotDatabase) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await db.save_zt_member("abc123", "", now, "allowed")

        result = await db.find_zt_member_by_id("abc123")
        assert "abc123" in result
        assert "192.168" not in result

    @pytest.mark.asyncio
    async def test_list_zt_members(self, db: BotDatabase) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await db.save_zt_member("member1", "10.0.0.1", now, "allowed")
        await db.save_zt_member("member2", "10.0.0.2", now, "blocked")

        members = await db.list_zt_members()
        assert len(members) == 2

    @pytest.mark.asyncio
    async def test_old_zt_member_not_saved(self, db: BotDatabase) -> None:
        old_date = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=31)
        await db.save_zt_member("oldmember", "10.0.0.1", old_date, "allowed")

        result = await db.find_zt_member_by_id("oldmember")
        assert result == ""

    @pytest.mark.asyncio
    async def test_ban_and_list_bans(self, db: BotDatabase) -> None:
        await db.ban("192.168.1.100")

        bans = await db.list_bans()
        assert len(bans) == 1
        assert "192.168.1.100" in bans[0]

    @pytest.mark.asyncio
    async def test_remove_ban(self, db: BotDatabase) -> None:
        await db.ban("192.168.1.100")
        await db.remove_ban("192.168.1.100")

        bans = await db.list_bans()
        assert len(bans) == 0

    @pytest.mark.asyncio
    async def test_find_members_to_block(self, db: BotDatabase) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await db.save_zt_member("member1", "192.168.1.100", now, "allowed")
        await db.ban("192.168.1.100")

        to_block = await db.find_members_to_block()
        assert "member1" in to_block

    @pytest.mark.asyncio
    async def test_already_blocked_not_in_find_members_to_block(self, db: BotDatabase) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        await db.save_zt_member("member1", "192.168.1.100", now, "blocked")
        await db.ban("192.168.1.100")

        to_block = await db.find_members_to_block()
        assert "member1" not in to_block

    @pytest.mark.asyncio
    async def test_clean_up_removes_old_sightings(self, db: BotDatabase) -> None:
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=15)
        ipv6 = IPv6Address("fd00::abcd:1234:5678")
        await db.save_member_sighting(ipv6, "OldPlayer", old)

        await db.clean_up()

        results = await db.find_player_by_name("OldPlayer")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_clean_up_keeps_recent_sightings(self, db: BotDatabase) -> None:
        recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        ipv6 = IPv6Address("fd00::abcd:1234:5678")
        await db.save_member_sighting(ipv6, "RecentPlayer", recent)

        await db.clean_up()

        results = await db.find_player_by_name("RecentPlayer")
        assert len(results) == 1
