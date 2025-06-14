import aiohttp
import logging
from typing import Any, Self

logger = logging.getLogger(__name__)

class ZeroTierApiClient:
    def __init__(self, token: str) -> None:
        self._baseUrl = 'https://api.zerotier.com/api/v1'
        self._session = aiohttp.ClientSession(headers={'Authorization': f'token {token}'})

    async def get_network(self, networkId: str) -> Any:
        url = f'{self._baseUrl}/network/{networkId}'
        async with self._session.get(url) as response:
            if response.status == 200:
                return await response.json()
            self._log_error(response.status, 'Failed to retrieve ZeroTier network')
            return None

    async def get_members(self, networkId: str) -> Any:
        url = f'{self._baseUrl}/network/{networkId}/member'
        async with self._session.get(url) as response:
            if response.status == 200:
                return await response.json()
            self._log_error(response.status, 'Failed to retrieve ZeroTier member list')
            return None

    async def get_member(self, networkId: str, memberId: str) -> Any:
        url = f'{self._baseUrl}/network/{networkId}/member/{memberId}'
        async with self._session.get(url) as response:
            if response.status == 200:
                return await response.json()
            self._log_error(response.status, 'Failed to retrieve ZeroTier member')
            return None

    async def tag_member(self, network: Any, member: Any, tag: str, tagValue: str) -> None:
        tagId = network['tagsByName'][tag]['id']
        tagValueId = network['tagsByName'][tag]['enums'][tagValue]
        tags = [tag for tag in member['config']['tags'] if tag[0] != tagId]
        tags.append([tagId, tagValueId])

        networkId = network['id']
        memberId = member['config']['id']
        url = f'{self._baseUrl}/network/{networkId}/member/{memberId}'
        payload = {'config': {'tags': tags}}
        async with self._session.post(url, json=payload) as response:
            if response.status == 200: return
            self._log_error(response.status, 'Failed to update ZeroTier member tag')

    def _log_error(self, status: int, message: str) -> None:
        message += f': {status}'
        match status:
            case 401: message += ' Authorization required'
            case 403: message += ' Access denied'
            case 404: message += ' Item not found'
        logger.error(message)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._session.close()
