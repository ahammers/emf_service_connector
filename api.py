from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .const import SUBMIT_PATH


@dataclass(frozen=True)
class EmfApi:
    session: ClientSession
    base_url: str

    async def submit_energy_data(self, payload: dict[str, Any]) -> tuple[int, str]:
        url = self.base_url
        timeout = ClientTimeout(total=60)

        async with self.session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        ) as resp:
            text = await resp.text()
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"EMF submit failed: HTTP {resp.status}: {text[:300]}")
            return resp.status, text[:300]
