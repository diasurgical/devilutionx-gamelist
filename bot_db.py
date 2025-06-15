import aiosqlite
from ipaddress import IPv6Address
from datetime import date, datetime, timedelta, UTC
from typing import Any, List, Self

def adapt_datetime_iso(val: datetime) -> str:
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return val.replace(tzinfo=None).isoformat(sep=' ', timespec='seconds')

aiosqlite.register_adapter(datetime, adapt_datetime_iso)

table_definitions = [
"""\
CREATE TABLE IF NOT EXISTS MemberSighting
(
    ZeroTierMemberID TEXT,
    PlayerName TEXT,
    Timestamp DATETIME
)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_MemberSighting_Search
ON MemberSighting(PlayerName COLLATE NOCASE, Timestamp DESC)
""",
"""\
CREATE TABLE IF NOT EXISTS PlayerSighting
(
    PlayerName TEXT,
    GameName TEXT,
    First DATETIME,
    Last DATETIME
)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_PlayerSighting_SearchFirst
ON PlayerSighting(PlayerName COLLATE NOCASE, First DESC)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_PlayerSighting_SearchLast
ON PlayerSighting(PlayerName COLLATE NOCASE, Last DESC)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_PlayerSighting_GameSearchFirst
ON PlayerSighting(GameName COLLATE NOCASE, First DESC)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_PlayerSighting_GameSearchLast
ON PlayerSighting(GameName COLLATE NOCASE, Last DESC)
""",
"""\
CREATE TABLE IF NOT EXISTS ZeroTierMember
(
    ID TEXT PRIMARY KEY,
    PhysicalAddress TEXT,
    LastSeen DATETIME,
    Status TEXT
)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_ZeroTierMember_PhysicalAddress
ON ZeroTierMember(PhysicalAddress)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_ZeroTierMember_LastSeen
ON ZeroTierMember(LastSeen DESC)
""",
"""\
CREATE TABLE IF NOT EXISTS IPBan
(
    IPAddress TEXT PRIMARY KEY,
    Expiration DATETIME
)
"""
]

class BotDatabase:
    def __init__(self, dbPath: str = './bot_data.db') -> None:
        self._dbPath = dbPath

    async def find_player_by_name(self, name: str) -> List[str]:
        query = '\n'.join((
            "SELECT Timestamp, GameName, ZeroTierMemberID",
            "FROM",
            "(",
            "    SELECT Timestamp, PlayerName, NULL GameName, ZeroTierMemberID",
            "    FROM MemberSighting",
            "    UNION",
            "    SELECT First Timestamp, PlayerName, GameName, NULL ZeroTierMemberID",
            "    FROM PlayerSighting",
            "    UNION",
            "    SELECT Last Timestamp, PlayerName, GameName, NULL ZeroTierMemberID",
            "    FROM PlayerSighting",
            ") Sighting",
            "WHERE PlayerName = ? COLLATE NOCASE",
            "ORDER BY Timestamp DESC",
            "LIMIT 50",
        ))

        sightings = []
        async with self._db.execute(query, (name,)) as cursor:
            async for row in cursor:
                timestamp = row[0]
                gameName = row[1]
                ztid = row[2]
                if gameName: sightings.append(f'[{timestamp}] Player {name} spotted in game {gameName}')
                if ztid: sightings.append(f'[{timestamp}] Member {ztid} spotted playing {name}')
        return sightings

    async def find_game_by_name(self, name: str) -> List[str]:
        query = '\n'.join((
            "SELECT Timestamp, PlayerName",
            "FROM",
            "(",
            "    SELECT First Timestamp, PlayerName, GameName",
            "    FROM PlayerSighting",
            "    UNION",
            "    SELECT Last Timestamp, PlayerName, GameName",
            "    FROM PlayerSighting",
            ") Sighting",
            "WHERE GameName = ? COLLATE NOCASE",
            "ORDER BY Timestamp DESC",
            "LIMIT 50",
        ))

        sightings = []
        async with self._db.execute(query, (name,)) as cursor:
            async for row in cursor:
                timestamp = row[0]
                playerName = row[1]
                sightings.append(f'[{timestamp}] Player {playerName} spotted in game {name}')
        return sightings

    async def find_zt_member_by_id(self, ztid: str) -> str:
        query = '\n'.join((
            "SELECT",
            "    ID,",
            "    PhysicalAddress,",
            "    LastSeen,",
            "    Status",
            "FROM ZeroTierMember",
            "WHERE ID = ?",
        ))

        async with self._db.execute(query, (ztid,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return ''
            id = row[0]
            ip = row[1]
            lastSeen = row[2]
            status = row[3]
            if ip != '':
                return f'[{id}] ({status}) {ip}, Seen: {lastSeen}'
            else:
                return f'[{id}] ({status}) Seen: {lastSeen}'

    async def list_zt_members(self) -> List[str]:
        query = '\n'.join((
            "SELECT",
            "    ID,",
            "    PhysicalAddress,",
            "    LastSeen,",
            "    Status",
            "FROM ZeroTierMember",
            "ORDER BY LastSeen DESC",
            "LIMIT 50",
        ))

        members = []
        async with self._db.execute(query) as cursor:
            async for row in cursor:
                id = row[0]
                ip = row[1]
                lastSeen = row[2]
                status = row[3]
                if ip != '':
                    members.append(f'[{id}] ({status}) {ip}, Last seen: {lastSeen}')
                else:
                    members.append(f'[{id}] ({status}) Last seen: {lastSeen}')
        return members

    async def find_members_to_block(self) -> List[str]:
        # Limit query to 15 members to avoid ZeroTier rate limit of 20 requests per second
        query = '\n'.join((
            "SELECT ZeroTierMember.ID",
            "FROM",
            "    IPBan JOIN",
            "    ZeroTierMember ON IPBan.IPAddress = ZeroTierMember.PhysicalAddress",
            "WHERE ZeroTierMember.Status <> 'blocked'",
            "ORDER BY ZeroTierMember.LastSeen DESC",
            "LIMIT 15",
        ))

        memberIds = []
        async with self._db.execute(query) as cursor:
            async for row in cursor:
                memberIds.append(row[0])
        return memberIds

    async def list_bans(self) -> List[str]:
        query = '\n'.join((
            "SELECT",
            "    IPAddress,",
            "    Expiration",
            "FROM IPBan",
            "ORDER BY Expiration DESC",
            "LIMIT 50",
        ))

        bans = []
        async with self._db.execute(query) as cursor:
            async for row in cursor:
                ip = row[0]
                expiration = row[1]
                bans.append(f'{ip} expires {expiration}')
        return bans

    async def save_member_sighting(self, ipv6: IPv6Address, playerName: str, at: datetime) -> None:
        query = '\n'.join((
            "INSERT INTO MemberSighting",
            "SELECT",
            "    :memberId ZeroTierMemberID,",
            "    :playerName PlayerName,",
            "    :at Timestamp",
            "WHERE NOT EXISTS",
            "(",
            "    SELECT *",
            "    FROM MemberSighting",
            "    WHERE",
            "        ZeroTierMemberID = :memberId AND",
            "        PlayerName = :playerName AND",
            "        Timestamp = :at",
            ")",
        ))

        queryParameters = {
            'memberId': ipv6.packed[-5:].hex(),
            'playerName': playerName,
            'at': at
        }

        async with self._db.cursor() as cursor:
            await cursor.execute(query, queryParameters)
        await self._db.commit()

    async def save_player_sighting(self, playerName: str, gameName: str, at: datetime) -> None:
        updateQuery = '\n'.join((
            "UPDATE PlayerSighting",
            "SET Last = ?",
            "WHERE",
            # Only update the most recent sighting
            "    NOT EXISTS"
            "    (",
            "        SELECT *",
            "        FROM PlayerSighting Next",
            "        WHERE",
            "            Last > PlayerSighting.Last AND",
            "            PlayerName = PlayerSighting.PlayerName AND",
            "            GameName = PlayerSighting.GameName",
            "    ) AND",
            "    PlayerName = ? AND",
            "    GameName = ?",
        ))

        async with self._db.cursor() as cursor:
            await cursor.execute(updateQuery, (at, playerName, gameName))
            if cursor.rowcount == 0:
                await cursor.execute("INSERT INTO PlayerSighting VALUES(?, ?, ?, ?)", (playerName, gameName, at, at))
        await self._db.commit()

    async def save_zt_member(self, id: str, physicalAddress: str, lastSeen: datetime, status: str) -> None:
        memberThreshold = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
        if lastSeen.replace(tzinfo=None) < memberThreshold:
            return

        query = '\n'.join((
            "INSERT INTO ZeroTierMember(ID, PhysicalAddress, LastSeen, Status)",
            "VALUES(:id, :physicalAddress, :lastSeen, :status)",
            "ON CONFLICT DO UPDATE SET",
            "    PhysicalAddress = :physicalAddress," if physicalAddress != '' else '',
            "    LastSeen = :lastSeen,",
            "    Status = :status",
        ))

        queryParameters = {
            'id': id,
            'physicalAddress': physicalAddress,
            'lastSeen': lastSeen,
            'status': status
        }

        async with self._db.cursor() as cursor:
            await cursor.execute(query, queryParameters)
        await self._db.commit()

    async def ban(self, physicalAddress: str) -> None:
        expiration = datetime.now(UTC) + timedelta(days=30)
        async with self._db.cursor() as cursor:
            await cursor.execute("INSERT OR REPLACE INTO IPBan VALUES(?, ?)", (physicalAddress, expiration))
        await self._db.commit()

    async def remove_ban(self, physicalAddress: str) -> None:
        async with self._db.cursor() as cursor:
            await cursor.execute("DELETE FROM IPBan WHERE IPAddress = ?", (physicalAddress,))
        await self._db.commit()

    async def clean_up(self) -> None:
        async with self._db.cursor() as cursor:
            now = datetime.now(UTC)
            sightingThreshold = now - timedelta(days=14)
            memberThreshold = now - timedelta(days=30)
            await cursor.execute("DELETE FROM MemberSighting WHERE Timestamp < ?", (sightingThreshold,))
            await cursor.execute("DELETE FROM PlayerSighting WHERE Last < ?", (sightingThreshold,))
            await cursor.execute("DELETE FROM ZeroTierMember WHERE LastSeen < ?", (memberThreshold,))
            await cursor.execute("DELETE FROM IPBan WHERE Expiration < ?", (now,))
        await self._db.commit()

    async def __aenter__(self) -> Self:
        self._db = await aiosqlite.connect(self._dbPath)
        async with self._db.cursor() as cursor:
            for table_definition in table_definitions:
                await cursor.execute(table_definition)
        await self._db.commit()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._db.close()
