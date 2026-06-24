"""Pinterest API v5 integration for creating pins."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class PinResult:
    """Result from creating a Pinterest pin."""

    success: bool
    pin_id: str | None = None
    pin_url: str | None = None
    error: str | None = None


class PinterestClient:
    """Client for Pinterest API v5."""

    BASE_URL = "https://api.pinterest.com/v5"

    def __init__(self, access_token: str):
        self._access_token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def get_boards(self) -> list[dict]:
        """Get all boards for the authenticated user."""
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.get(f"{self.BASE_URL}/boards", timeout=30)
            resp.raise_for_status()
            data = resp.json()
        return data.get("items", [])

    async def create_pin(
        self,
        board_id: str,
        title: str,
        description: str,
        link: str,
        image_url: str,
        alt_text: str = "",
    ) -> PinResult:
        """Create a pin on Pinterest.

        Args:
            board_id: The board to pin to.
            title: Pin title (max 100 chars).
            description: Pin description (max 500 chars).
            link: Destination URL (the affiliate link).
            image_url: Publicly accessible image URL.
            alt_text: Alt text for the image.

        Returns:
            PinResult with success status and pin details.
        """
        payload = {
            "board_id": board_id,
            "title": title[:100],
            "description": description[:500],
            "link": link,
            "media_source": {
                "source_type": "image_url",
                "url": image_url,
            },
        }

        if alt_text:
            payload["alt_text"] = alt_text[:500]

        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.post(
                f"{self.BASE_URL}/pins",
                json=payload,
                timeout=30,
            )

        if resp.status_code in (200, 201):
            data = resp.json()
            pin_id = data.get("id", "")
            return PinResult(
                success=True,
                pin_id=pin_id,
                pin_url=f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else None,
            )
        else:
            content_type = resp.headers.get("content-type", "")
            error_data = resp.json() if content_type.startswith("application/json") else {}
            return PinResult(
                success=False,
                error=f"HTTP {resp.status_code}: {error_data.get('message', resp.text[:200])}",
            )

    async def verify_token(self) -> bool:
        """Verify the access token is valid."""
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.get(f"{self.BASE_URL}/user_account", timeout=15)
        return resp.status_code == 200
