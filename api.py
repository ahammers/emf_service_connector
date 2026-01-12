from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .const import SUBMIT_PATH


@dataclass(frozen=True)
class EmfApi:
    session: ClientSession
    base_url: str

    async def submit_energy_data(self, payload: dict[str, Any]) -> None:
        url = f"{self.base_url.rstrip('/')}{SUBMIT_PATH}"
        timeout = ClientTimeout(total=20)

        async with self.session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        ) as resp:
            # API ist "quick and dirty" – wir behandeln Nicht-2xx als Fehler
            if resp.status < 200 or resp.status >= 300:
                text = await resp.text()
                raise RuntimeError(f"EMF submit failed: HTTP {resp.status}: {text[:300]}")
