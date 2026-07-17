"""Advanced automation engine for the AliExpress to Pinterest bot.

Supports one-command pipelines that fetch multiple pages of products,
generate AI Pinterest content, save to the database, and publish pins
on a schedule. Plans can be written as JSON or YAML.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from ae_pinner.ai_generator import AIProvider, PinContent, generate_pin_content
from ae_pinner.aliexpress import AliExpressClient
from ae_pinner.config import Config
from ae_pinner.database import Database
from ae_pinner.pinterest import PinterestClient

console = Console()


@dataclass
class AutomationPlan:
    """A reusable automation plan."""

    pages: int = 1
    page: int = 1
    page_size: int = 12
    ai: str = "gemini"
    save: bool = False
    generate: bool = True
    publish: bool = False
    dry_run: bool = False
    page_delay: float = 3.0
    pin_delay: float = 1.5
    interval_minutes: float = 0.0
    max_runs: int | None = None

    def __post_init__(self) -> None:
        self.ai = (self.ai or "gemini").lower()
        if self.publish and not self.generate:
            self.generate = True
        if self.page_size > 12:
            self.page_size = 12
        self.pages = max(1, self.pages)
        self.page = max(1, self.page)
        self.page_delay = max(0.0, float(self.page_delay))
        self.pin_delay = max(0.0, float(self.pin_delay))
        self.interval_minutes = max(0.0, float(self.interval_minutes))
        if self.max_runs is not None:
            self.max_runs = max(1, int(self.max_runs))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutomationPlan":
        """Load a plan from a plain dict with flexible key names."""
        mapping = {
            "count": "page_size",
            "page_size": "page_size",
            "per_page": "page_size",
            "start_page": "page",
            "page": "page",
            "num_pages": "pages",
            "pages": "pages",
            "ai_provider": "ai",
            "provider": "ai",
            "ai": "ai",
            "save_to_db": "save",
            "save": "save",
            "skip_generate": "generate",
            "generate": "generate",
            "auto_publish": "publish",
            "publish": "publish",
            "dry_run": "dry_run",
            "page_delay": "page_delay",
            "delay": "page_delay",
            "pin_delay": "pin_delay",
            "interval": "interval_minutes",
            "interval_minutes": "interval_minutes",
            "max_runs": "max_runs",
        }
        kwargs: dict[str, Any] = {}
        for raw_key, value in data.items():
            key = mapping.get(raw_key, raw_key)
            if key in cls.__dataclass_fields__:
                kwargs[key] = value
            else:
                console.print(f"[yellow]Warning:[/] Unknown plan key '{raw_key}' ignored")
        return cls(**kwargs)

    @classmethod
    def load(cls, path: str | Path) -> "AutomationPlan":
        """Load a plan from a JSON or YAML file."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as exc:
                raise ImportError(
                    "PyYAML is required for YAML plans. Install it with: pip install pyyaml"
                ) from exc
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Automation plan must be a JSON/YAML object")
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Export the plan as a dict."""
        return {
            "pages": self.pages,
            "page": self.page,
            "page_size": self.page_size,
            "ai": self.ai,
            "save": self.save,
            "generate": self.generate,
            "publish": self.publish,
            "dry_run": self.dry_run,
            "page_delay": self.page_delay,
            "pin_delay": self.pin_delay,
            "interval_minutes": self.interval_minutes,
            "max_runs": self.max_runs,
        }


def _validate_plan(config: Config, plan: AutomationPlan) -> None:
    """Raise ValueError if the plan cannot be executed with the current config."""
    missing: list[str] = []
    if not config.ae_cookie_xman_us_t:
        missing.append("AE_COOKIE_XMAN_US_T")
    if plan.generate and not config.gemini_api_key and not config.openai_api_key:
        missing.append("GEMINI_API_KEY / OPENAI_API_KEY")
    if plan.publish:
        if not config.pinterest_access_token:
            missing.append("PINTEREST_ACCESS_TOKEN")
        if not config.pinterest_board_id:
            missing.append("PINTEREST_BOARD_ID")
    if missing:
        raise ValueError("Missing configuration:\n" + "\n".join(f" - {m}" for m in missing))


async def _generate_pin(
    product: Any,
    ai_provider: AIProvider,
    config: Config,
) -> PinContent:
    """Generate Pinterest content with a fallback on error."""
    try:
        return await generate_pin_content(
            product=product,
            provider=ai_provider,
            gemini_api_key=config.gemini_api_key,
            openai_api_key=config.openai_api_key,
        )
    except Exception as exc:
        console.print(f"  [red]AI Error:[/] {exc}")
        return PinContent(
            title=product.title[:100],
            description=(
                f"{product.discount_price} (was {product.original_price})"
                f" - {product.discount_rate}% OFF!"
            ),
            alt_text=product.title[:100],
        )


async def _fetch_page(
    config: Config,
    page_num: int,
    page_size: int,
) -> list[Any]:
    """Fetch one page of products with promo links."""
    ae = AliExpressClient(
        xman_us_t=config.ae_cookie_xman_us_t,
        xman_us_f=config.ae_cookie_xman_us_f,
        tracking_id=config.ae_tracking_id,
    )
    console.print(
        f"\n[bold blue]Fetching page {page_num}[/] "
        f"(count={page_size}, ship_to={config.pin_ship_to}, "
        f"currency={config.pin_currency}, lang={config.pin_language})"
    )
    products = await ae.fetch_products_with_promo_links(
        page_num=page_num,
        page_size=page_size,
        ship_to=config.pin_ship_to,
        currency=config.pin_currency,
        language=config.pin_language,
    )
    console.print(f"  Found [green]{len(products)}[/] products")
    return products


async def _process_page(
    config: Config,
    plan: AutomationPlan,
    db: Database | None,
    pinterest: PinterestClient | None,
    ai_provider: AIProvider,
    page_num: int,
) -> dict[str, int]:
    """Process a single page and return counters."""
    products = await _fetch_page(config, page_num, plan.page_size)
    if not products:
        return {"fetched": 0, "saved": 0, "generated": 0, "published": 0, "failed": 0}

    fetched = len(products)
    saved = generated = published = failed = 0

    for idx, product in enumerate(products, 1):
        if db and plan.save:
            if db.product_exists(product.item_id):
                console.print(
                    f"  [{idx}/{fetched}] [dim]{product.item_id} already saved, skipping[/]"
                )
                continue
            if db.save_product(product):
                saved += 1

        pin_content: PinContent | None = None
        if plan.generate:
            pin_content = await _generate_pin(product, ai_provider, config)
            generated += 1
            if db and plan.save:
                db.update_pin_content(product.item_id, pin_content)

        if plan.publish and pin_content:
            link = product.promo_url or product.item_url or ""
            if not link:
                console.print(f"  [{idx}/{fetched}] [yellow]Skipped[/] (no link)")
                failed += 1
                continue

            if plan.dry_run:
                published += 1
                console.print(
                    f"  [{idx}/{fetched}] [cyan]DRY RUN[/] Pin: {pin_content.title[:60]}..."
                )
            else:
                try:
                    result = await pinterest.create_pin(
                        board_id=config.pinterest_board_id,
                        title=pin_content.title,
                        description=pin_content.description,
                        link=link,
                        image_url=product.image_url,
                        alt_text=pin_content.alt_text,
                    )
                    if result.success:
                        published += 1
                        console.print(
                            f"  [{idx}/{fetched}] [green]Published[/] {result.pin_url}"
                        )
                        if db and plan.save:
                            db.update_pin_published(
                                product.item_id,
                                result.pin_id or "",
                                result.pin_url or "",
                            )
                    else:
                        failed += 1
                        console.print(f"  [{idx}/{fetched}] [red]Failed[/] {result.error}")
                except Exception as exc:
                    failed += 1
                    console.print(f"  [{idx}/{fetched}] [red]Error[/] {exc}")

        if plan.pin_delay:
            await asyncio.sleep(plan.pin_delay)

    return {
        "fetched": fetched,
        "saved": saved,
        "generated": generated,
        "published": published,
        "failed": failed,
    }


async def _run_once(
    config: Config,
    plan: AutomationPlan,
    db: Database | None,
    pinterest: PinterestClient | None,
    ai_provider: AIProvider,
) -> dict[str, int]:
    """Run a single automation pass over the configured pages."""
    totals = {"fetched": 0, "saved": 0, "generated": 0, "published": 0, "failed": 0}

    for offset in range(plan.pages):
        page_num = plan.page + offset
        page_result = await _process_page(
            config, plan, db, pinterest, ai_provider, page_num
        )
        for key in totals:
            totals[key] += page_result[key]

        if page_result["fetched"] == 0:
            console.print("[yellow]No products returned; stopping early[/]")
            break

        if plan.page_delay and offset < plan.pages - 1:
            await asyncio.sleep(plan.page_delay)

    return totals


async def run_automation(
    config: Config,
    plan: AutomationPlan,
    db: Database | None = None,
) -> dict[str, int]:
    """Execute an automation plan. Loops forever if interval_minutes > 0."""
    _validate_plan(config, plan)

    ai_provider = AIProvider.OPENAI if plan.ai == "openai" else AIProvider.GEMINI
    pinterest: PinterestClient | None = None
    if plan.publish and not plan.dry_run:
        pinterest = PinterestClient(config.pinterest_access_token)

    if plan.publish:
        console.print(
            "[bold]Advanced Automation[/]\n"
            f"  Pages: {plan.pages} (starting at {plan.page})\n"
            f"  AI: {ai_provider.value}\n"
            f"  Save to DB: {'Yes' if plan.save and db else 'No'}\n"
            f"  Publish: {'Yes (DRY RUN)' if plan.dry_run else 'Yes'}\n"
            f"  Interval: {plan.interval_minutes} minutes"
        )
    else:
        console.print(
            "[bold]Advanced Automation[/]\n"
            f"  Pages: {plan.pages} (starting at {plan.page})\n"
            f"  AI: {ai_provider.value}\n"
            f"  Save to DB: {'Yes' if plan.save and db else 'No'}\n"
            f"  Publish: No (generate/save only)"
        )

    run = 0
    grand_totals: dict[str, int] = {
        "fetched": 0,
        "saved": 0,
        "generated": 0,
        "published": 0,
        "failed": 0,
    }

    try:
        while plan.max_runs is None or run < plan.max_runs:
            run += 1
            console.print(f"\n[bold]Run {run}[/]")
            totals = await _run_once(config, plan, db, pinterest, ai_provider)
            for key in grand_totals:
                grand_totals[key] += totals[key]

            console.print(
                f"\n[bold]Run {run} summary:[/] "
                f"fetched={totals['fetched']}, saved={totals['saved']}, "
                f"generated={totals['generated']}, published={totals['published']}, "
                f"failed={totals['failed']}"
            )

            if plan.interval_minutes <= 0:
                break
            if plan.max_runs and run >= plan.max_runs:
                break

            console.print(f"[yellow]Sleeping {plan.interval_minutes} minutes...[/]")
            await asyncio.sleep(plan.interval_minutes * 60)
    except asyncio.CancelledError:
        console.print("\n[yellow]Automation cancelled.[/]")
        raise

    console.print(
        f"\n[bold]Grand total:[/] "
        f"fetched={grand_totals['fetched']}, saved={grand_totals['saved']}, "
        f"generated={grand_totals['generated']}, published={grand_totals['published']}, "
        f"failed={grand_totals['failed']}"
    )
    return grand_totals
