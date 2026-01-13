from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiohttp import ClientSession, ClientTimeout


@dataclass(frozen=True)
class EmfApi:
    session: ClientSession
    base_url: str

    async def submit_energy_data(self, payload: dict[str, Any]) -> tuple[int, str]:
        """Submit payload and return (http_status, response_text).

        Note: We intentionally do NOT raise on non-2xx responses because the caller
        needs to distinguish between transient failures (retry) and permanent ones
        (e.g. HTTP 422 -> drop queued record).
        Network/transport errors will still raise aiohttp exceptions.
        """
        url = self.base_url
        timeout = ClientTimeout(total=60)

        async with self.session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        ) as resp:
            text = await resp.text()
            return resp.status, (text or "")[:300]
