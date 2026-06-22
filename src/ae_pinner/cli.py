"""CLI entry point for the AliExpress-to-Pinterest bot."""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console

from ae_pinner.ai_generator import AIProvider
from ae_pinner.bot import run_bot
from ae_pinner.config import Config

console = Console()


@click.group()
@click.version_option(version="1.0.0")
def main():
    """AliExpress to Pinterest Auto-Pin Bot.

    Fetches trending products from AliExpress affiliate portal,
    generates AI-powered descriptions, and creates Pinterest pins
    with your affiliate links.
    """
    pass


@main.command()
@click.option("--page", default=1, help="Page number for product recommendations")
@click.option("--count", default=12, help="Number of products to fetch (max 12)")
@click.option(
    "--ai",
    type=click.Choice(["gemini", "openai"]),
    default="gemini",
    help="AI provider for generating descriptions",
)
@click.option("--dry-run", is_flag=True, help="Preview without creating pins on Pinterest")
@click.option("--env-file", default=None, help="Path to .env file")
def run(page: int, count: int, ai: str, dry_run: bool, env_file: str | None):
    """Run the bot: fetch products → AI descriptions → create pins."""
    config = Config.load(env_file)
    missing = config.validate()

    if missing and not dry_run:
        console.print("[red]Missing required configuration:[/]")
        for m in missing:
            console.print(f"  - {m}")
        console.print("\nCopy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    ai_provider = AIProvider.OPENAI if ai == "openai" else AIProvider.GEMINI

    console.print(
        f"[bold]AliExpress → Pinterest Pin Bot[/]\n"
        f"  AI Provider: [cyan]{ai_provider.value}[/]\n"
        f"  Page: {page} | Count: {count}\n"
        f"  Dry Run: {'Yes' if dry_run else 'No'}",
        highlight=False,
    )

    result = asyncio.run(
        run_bot(
            config=config,
            page_num=page,
            page_size=count,
            ai_provider=ai_provider,
            dry_run=dry_run,
        )
    )

    if result.pins_created > 0:
        console.print(f"\n[bold green]Done! {result.pins_created} pins created.[/]")
    elif dry_run:
        console.print(
            f"\n[bold yellow]Dry run complete. "
            f"{result.total_products} products ready.[/]"
        )
    else:
        console.print("\n[bold red]No pins were created.[/]")


@main.command()
@click.option("--env-file", default=None, help="Path to .env file")
def boards(env_file: str | None):
    """List your Pinterest boards (to find board_id)."""
    from ae_pinner.pinterest import PinterestClient

    config = Config.load(env_file)
    if not config.pinterest_access_token:
        console.print("[red]PINTEREST_ACCESS_TOKEN is required. Set it in .env[/]")
        sys.exit(1)

    async def _list_boards():
        client = PinterestClient(config.pinterest_access_token)
        boards_list = await client.get_boards()
        if not boards_list:
            console.print("[yellow]No boards found or token invalid.[/]")
            return
        console.print("\n[bold]Your Pinterest Boards:[/]\n")
        for board in boards_list:
            console.print(f"  ID: [cyan]{board['id']}[/]  Name: {board.get('name', 'N/A')}")

    asyncio.run(_list_boards())


@main.command()
@click.option("--env-file", default=None, help="Path to .env file")
def verify(env_file: str | None):
    """Verify all API connections are working."""
    config = Config.load(env_file)

    console.print("[bold]Verifying connections...[/]\n")

    async def _verify():
        # Check Pinterest
        if config.pinterest_access_token:
            from ae_pinner.pinterest import PinterestClient

            client = PinterestClient(config.pinterest_access_token)
            ok = await client.verify_token()
            status = "[green]OK[/]" if ok else "[red]FAILED[/]"
            console.print(f"  Pinterest API: {status}")
        else:
            console.print("  Pinterest API: [yellow]SKIPPED (no token)[/]")

        # Check AliExpress
        if config.ae_cookie_xman_us_t:
            from ae_pinner.aliexpress import AliExpressClient

            ae = AliExpressClient(config.ae_cookie_xman_us_t, config.ae_cookie_xman_us_f)
            products = await ae.fetch_recommended_products(page_size=1)
            status = "[green]OK[/]" if products else "[red]FAILED (check cookies)[/]"
            console.print(f"  AliExpress API: {status}")
        else:
            console.print("  AliExpress API: [yellow]SKIPPED (no cookies)[/]")

        # Check AI
        if config.gemini_api_key:
            console.print("  Gemini API: [green]Key configured[/]")
        elif config.openai_api_key:
            console.print("  OpenAI API: [green]Key configured[/]")
        else:
            console.print("  AI Provider: [red]No API key set[/]")

    asyncio.run(_verify())


if __name__ == "__main__":
    main()
