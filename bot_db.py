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
CREATE TABLE IF NOT EXISTS PlayerSighting
(
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    ZeroTierMemberID TEXT,
    First DATETIME,
    Last DATETIME,
    GameName TEXT,
    PlayerCount INTEGER
)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_PlayerSighting_Last
ON PlayerSighting(Last DESC)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_PlayerSighting_Search
ON PlayerSighting(ZeroTierMemberID, GameName, Last DESC)
""",
"""\
CREATE TABLE IF NOT EXISTS Player
(
    SightingID INTEGER REFERENCES PlayerSighting(ID),
    Name TEXT
)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_Player_SightingID
ON Player(SightingID)
""",
"""\
CREATE INDEX IF NOT EXISTS IX_Player_Name
ON Player(Name COLLATE NOCASE)
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
ON ZeroTierMember(PhysicalAddress DESC)
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
            "SELECT",
            "    PlayerSighting.ZeroTierMemberID,",
            "    PlayerSighting.First,",
            "    PlayerSighting.Last,",
            "    PlayerSighting.GameName,",
            "    PlayerList.PlayerNames",
            "FROM",
            "    PlayerSighting JOIN",
            "    Player ON Player.SightingID = PlayerSighting.ID JOIN",
            # Group teammates by sighting into a single comma-separated field
            "    (",
            "        SELECT",
            "            SightingID,",
            "            group_concat(Name ORDER BY Name) PlayerNames",
            "        FROM Player",
            "        GROUP BY Player.SightingID",
            "    ) PlayerList ON PlayerList.SightingID = PlayerSighting.ID",
            "WHERE Player.Name = ? COLLATE NOCASE",
            "ORDER BY",
            "    PlayerSighting.ZeroTierMemberID,",
            "    PlayerSighting.Last DESC",
            "LIMIT 50",
        ))

        sightings = []
        async with self._db.execute(query, (name,)) as cursor:
            async for row in cursor:
                ztid = row[0]
                first = row[1]
                last = row[2]
                gameName = row[3]
                playerNames = row[4]
                sightings.append(f'[{first}] Game: {gameName}, Players: {playerNames}, ztid: {ztid}')
                if first != last: sightings.append(f'[{last}] Game: {gameName}, Players: {playerNames}, ztid: {ztid}')
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
            if row == None:
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

    async def save_player_sighting(self, at: datetime, ipv6: IPv6Address, gameName: str, playerNames: List[str]) -> None:
        if len(playerNames) == 0:
            return

        updateQuery = '\n'.join((
            "UPDATE PlayerSighting",
            "SET Last = :at",
            "WHERE",
            # Only update the most recent sighting
            "    NOT EXISTS"
            "    (",
            "        SELECT *",
            "        FROM PlayerSighting Next",
            "        WHERE",
            "            Last > PlayerSighting.Last AND",
            "            ZeroTierMemberID = PlayerSighting.ZeroTierMemberID",
            "    ) AND",
            "    ZeroTierMemberID = :ztid AND",
            "    GameName = :gameName AND",
            "    PlayerCount = :playerCount AND",
            "    PlayerCount =",
            "    (",
            "        SELECT COUNT(*)",
            "        FROM Player",
            "        WHERE",
            "            SightingID = PlayerSighting.ID AND",
            "            Name IN (:player1, :player2, :player3, :player4)",
            "    )",
        ))

        queryParameters = {
            'at': at,
            'ztid': ipv6.packed[-5:].hex(),
            'gameName': gameName,
            'playerCount': len(playerNames),
            'player1': playerNames[0],
            'player2': playerNames[1] if len(playerNames) >= 2 else '',
            'player3': playerNames[2] if len(playerNames) >= 3 else '',
            'player4': playerNames[3] if len(playerNames) >= 4 else ''
        }

        async with self._db.cursor() as cursor:
            await cursor.execute(updateQuery, queryParameters)
            if cursor.rowcount == 0:
                insertSighting = '\n'.join((
                    "INSERT INTO PlayerSighting(ZeroTierMemberID, First, Last, GameName, PlayerCount)",
                    "VALUES(:ztid, :at, :at, :gameName, :playerCount)",
                ))
                await cursor.execute(insertSighting, queryParameters)
                sightingId = cursor.lastrowid

                insertPlayer = "INSERT INTO Player VALUES(?, ?)"
                for playerName in playerNames:
                    await cursor.execute(insertPlayer, (sightingId, playerName))

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
            "    Status = status",
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
        async with self._db.cursor() as cursor:
            expiration = datetime.now(UTC) + timedelta(days=30)
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
            await cursor.execute("DELETE FROM Player WHERE SightingID IN (SELECT ID FROM PlayerSighting WHERE Last < ?)", (sightingThreshold,))
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
