"""AliExpress Affiliate Portal API integration.

Fetches trending/recommended products and generates affiliate promotion links.
Supports both individual cookie values and full raw cookie strings from browser DevTools.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class Product:
    """Parsed AliExpress product from the API response."""

    item_id: str
    main_item_id: str
    title: str
    image_url: str
    all_images: list[str]
    original_price: str
    discount_price: str
    discount_rate: str
    sales_30day: int
    comment_score: str
    commission_rate: str
    item_url: str
    promo_url: str | None = None


def parse_cookie_string(raw_cookie: str) -> dict[str, str]:
    """Parse a raw cookie header string into a dict of cookie name→value pairs."""
    cookies: dict[str, str] = {}
    for part in raw_cookie.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies


class AliExpressClient:
    """Client for AliExpress Affiliate Portal API."""

    BASE_URL = "https://portals.aliexpress.com"

    def __init__(
        self,
        xman_us_t: str = "",
        xman_us_f: str = "",
        tracking_id: str = "default",
        raw_cookie: str = "",
    ):
        self._tracking_id = tracking_id

        if raw_cookie:
            self._cookies = parse_cookie_string(raw_cookie)
        else:
            self._cookies = {
                "xman_us_t": xman_us_t,
                "xman_us_f": xman_us_f,
            }

        self._headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://portals.aliexpress.com/affiportals/web/ad_center.htm",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
            ),
        }

    async def fetch_recommended_products(
        self,
        page_num: int = 1,
        page_size: int = 12,
        ship_to: str = "US",
        currency: str = "USD",
        language: str = "en",
        recommend_type: int = 1,
    ) -> list[Product]:
        """Fetch recommended/trending products from AliExpress affiliate portal."""
        params = {
            "requireCouponCode": "",
            "freeShipping": "",
            "shipTo": ship_to,
            "currency": currency,
            "language": language,
            "pageSize": page_size,
            "pageNum": page_num,
            "type": recommend_type,
        }

        async with httpx.AsyncClient(cookies=self._cookies, headers=self._headers) as client:
            resp = await client.get(
                f"{self.BASE_URL}/material/productRecommend.do",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != "00" or not data.get("data", {}).get("results"):
            return []

        products = []
        for item in data["data"]["results"]:
            all_images = item.get("itemPics", "").split(",") if item.get("itemPics") else []
            products.append(
                Product(
                    item_id=str(item.get("subItemId", item.get("itemId", ""))),
                    main_item_id=str(item.get("mainItemId", "")),
                    title=item.get("itemTitle", ""),
                    image_url=item.get("itemMainPic", ""),
                    all_images=[img for img in all_images if img],
                    original_price=item.get("itemOriginPriceMin", ""),
                    discount_price=item.get("itemPriceDiscountMin", ""),
                    discount_rate=item.get("itemDiscountRate", ""),
                    sales_30day=item.get("sales30Day", 0),
                    comment_score=item.get("commentScore", ""),
                    commission_rate=item.get("directCommissionRate", ""),
                    item_url=item.get("itemUrl", ""),
                )
            )

        return products

    async def get_promo_link(
        self,
        product_id: str,
        ship_to: str = "US",
        currency: str = "USD",
        language: str = "en_US",
    ) -> str | None:
        """Generate affiliate promotion link for a product."""
        params = {
            "productId": product_id,
            "trackingId": self._tracking_id,
            "language": language,
            "shipTo": ship_to,
            "currency": currency,
            "subChannel": "hco",
        }

        async with httpx.AsyncClient(cookies=self._cookies, headers=self._headers) as client:
            resp = await client.get(
                f"{self.BASE_URL}/promote/promoteNow.do",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") == "00" and data.get("data"):
            return data["data"].get("promoteUrl")
        return None

    async def get_promo_details(
        self,
        product_id: str,
        ship_to: str = "US",
        currency: str = "USD",
        language: str = "en_US",
    ) -> dict | None:
        """Get full promote details including promo URL and all images."""
        params = {
            "productId": product_id,
            "trackingId": self._tracking_id,
            "language": language,
            "shipTo": ship_to,
            "currency": currency,
            "subChannel": "hco",
        }

        async with httpx.AsyncClient(cookies=self._cookies, headers=self._headers) as client:
            resp = await client.get(
                f"{self.BASE_URL}/promote/promoteNow.do",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") == "00" and data.get("data"):
            return data["data"]
        return None

    async def fetch_products_with_promo_links(
        self,
        page_num: int = 1,
        page_size: int = 12,
        ship_to: str = "US",
        currency: str = "USD",
        language: str = "en",
    ) -> list[Product]:
        """Fetch products and attach promo links to each."""
        products = await self.fetch_recommended_products(
            page_num=page_num,
            page_size=page_size,
            ship_to=ship_to,
            currency=currency,
            language=language,
        )

        for product in products:
            promo_url = await self.get_promo_link(
                product_id=product.item_id,
                ship_to=ship_to,
                currency=currency,
            )
            product.promo_url = promo_url

        return products
