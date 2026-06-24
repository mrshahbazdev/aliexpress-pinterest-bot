"""Main orchestrator — ties AliExpress, AI, and Pinterest together."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

from ae_pinner.ai_generator import AIProvider, PinContent, generate_pin_content
from ae_pinner.aliexpress import AliExpressClient, Product
from ae_pinner.config import Config
from ae_pinner.pinterest import PinResult, PinterestClient

console = Console()


@dataclass
class PinJob:
    """A single pin creation job with all its data."""

    product: Product
    pin_content: PinContent | None = None
    pin_result: PinResult | None = None


@dataclass
class BotResult:
    """Summary of a bot run."""

    total_products: int = 0
    pins_created: int = 0
    pins_failed: int = 0
    jobs: list[PinJob] = field(default_factory=list)


async def run_bot(
    config: Config,
    page_num: int = 1,
    page_size: int = 12,
    ai_provider: AIProvider = AIProvider.GEMINI,
    dry_run: bool = False,
) -> BotResult:
    """Run the full pipeline: fetch products → AI descriptions → create pins.

    Args:
        config: Loaded application config.
        page_num: Which page of products to fetch.
        page_size: How many products to fetch (max 12).
        ai_provider: Which AI to use for descriptions.
        dry_run: If True, skip actual Pinterest pin creation.

    Returns:
        BotResult with summary of the run.
    """
    result = BotResult()

    # Step 1: Fetch products from AliExpress
    console.print("\n[bold blue]Step 1:[/] Fetching products from AliExpress...", highlight=False)
    ae_client = AliExpressClient(
        xman_us_t=config.ae_cookie_xman_us_t,
        xman_us_f=config.ae_cookie_xman_us_f,
        tracking_id=config.ae_tracking_id,
    )

    products = await ae_client.fetch_products_with_promo_links(
        page_num=page_num,
        page_size=page_size,
        ship_to=config.pin_ship_to,
        currency=config.pin_currency,
        language=config.pin_language,
    )

    result.total_products = len(products)
    console.print(f"  Found [green]{len(products)}[/] products with promo links")

    if not products:
        console.print("[red]No products found. Check your AliExpress cookies.[/]")
        return result

    # Step 2: Generate AI descriptions
    console.print(
        f"\n[bold blue]Step 2:[/] Generating AI descriptions using [cyan]{ai_provider.value}[/]...",
        highlight=False,
    )

    for i, product in enumerate(products, 1):
        job = PinJob(product=product)
        try:
            pin_content = await generate_pin_content(
                product=product,
                provider=ai_provider,
                openai_api_key=config.openai_api_key,
                gemini_api_key=config.gemini_api_key,
            )
            job.pin_content = pin_content
            console.print(f"  [{i}/{len(products)}] Generated: {pin_content.title[:60]}...")
        except Exception as e:
            console.print(f"  [{i}/{len(products)}] [red]AI Error:[/] {e}")
            # Use fallback content
            job.pin_content = PinContent(
                title=product.title[:100],
                description=(
                    f"{product.discount_price} (was {product.original_price})"
                    f" - {product.discount_rate}% OFF!"
                ),
                alt_text=product.title[:100],
            )

        result.jobs.append(job)

    # Step 3: Create Pinterest pins
    if dry_run:
        console.print("\n[bold yellow]Step 3:[/] DRY RUN — skipping Pinterest pin creation")
        _print_dry_run_table(result.jobs)
        return result

    console.print("\n[bold blue]Step 3:[/] Creating Pinterest pins...", highlight=False)
    pinterest = PinterestClient(access_token=config.pinterest_access_token)

    for i, job in enumerate(result.jobs, 1):
        if not job.pin_content or not job.product.promo_url:
            console.print(
                f"  [{i}/{len(result.jobs)}] [yellow]Skipped[/] (missing content or promo URL)"
            )
            result.pins_failed += 1
            continue

        pin_result = await pinterest.create_pin(
            board_id=config.pinterest_board_id,
            title=job.pin_content.title,
            description=job.pin_content.description,
            link=job.product.promo_url,
            image_url=job.product.image_url,
            alt_text=job.pin_content.alt_text,
        )
        job.pin_result = pin_result

        if pin_result.success:
            result.pins_created += 1
            console.print(f"  [{i}/{len(result.jobs)}] [green]Created[/] Pin: {pin_result.pin_url}")
        else:
            result.pins_failed += 1
            console.print(f"  [{i}/{len(result.jobs)}] [red]Failed[/]: {pin_result.error}")

        # Small delay between pin creations to avoid rate limits
        await asyncio.sleep(1.5)

    # Summary
    console.print("\n[bold]Summary:[/]")
    console.print(f"  Products fetched: {result.total_products}")
    console.print(f"  Pins created: [green]{result.pins_created}[/]")
    console.print(f"  Pins failed: [red]{result.pins_failed}[/]")

    return result


def _print_dry_run_table(jobs: list[PinJob]) -> None:
    """Print a table of what would be pinned in dry run mode."""
    table = Table(title="Dry Run - Pins to Create")
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", max_width=40)
    table.add_column("Price", width=12)
    table.add_column("AI Title", max_width=40)
    table.add_column("Promo URL", max_width=30)

    for i, job in enumerate(jobs, 1):
        table.add_row(
            str(i),
            job.product.title[:40],
            job.product.discount_price,
            job.pin_content.title[:40] if job.pin_content else "N/A",
            (job.product.promo_url or "N/A")[:30],
        )

    console.print(table)
