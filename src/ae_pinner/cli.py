"""CLI entry point for the AliExpress-to-Pinterest bot."""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console

from ae_pinner.ai_generator import AIProvider
from ae_pinner.automation import AutomationPlan, run_automation
from ae_pinner.bot import run_bot
from ae_pinner.config import Config
from ae_pinner.database import Database

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
    """Run the bot: fetch products -> AI descriptions -> create pins."""
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
        f"[bold]AliExpress -> Pinterest Pin Bot[/]\n"
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
            f"\n[bold yellow]Dry run complete. {result.total_products} products ready.[/]"
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

    # Check Database
    if config.db_host:
        from ae_pinner.database import Database

        try:
            db = Database(
                host=config.db_host,
                port=config.db_port,
                name=config.db_name,
                user=config.db_user,
                password=config.db_password,
            )
            db.init_tables()
            stats = db.get_stats()
            console.print(f"  Database: [green]OK[/] ({stats['total']} products stored)")
        except Exception as e:
            console.print(f"  Database: [red]FAILED[/] ({e})")
    else:
        console.print("  Database: [yellow]SKIPPED (no DB_HOST)[/]")


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind the web server to")
@click.option("--port", default=5000, help="Port for the web server")
@click.option("--env-file", default=None, help="Path to .env file")
@click.option("--debug", is_flag=True, help="Run in debug mode")
def web(host: str, port: int, env_file: str | None, debug: bool):
    """Start the web UI for managing products and Pinterest content.

    No .env file required -- database credentials can be entered
    through the web UI on first run and are saved locally.
    """
    from ae_pinner.web import init_app

    config = Config.load(env_file)

    if config.db_configured:
        console.print(
            f"[bold]Starting Web UI[/]\n"
            f"  URL: http://{host}:{port}\n"
            f"  Database: {config.db_host}:{config.db_port}/{config.db_name}",
            highlight=False,
        )
    else:
        console.print(
            f"[bold]Starting Web UI[/]\n"
            f"  URL: http://{host}:{port}\n"
            f"  [yellow]No database configured -- you will be prompted in the UI[/]",
            highlight=False,
        )

    flask_app = init_app(config)
    flask_app.run(host=host, port=port, debug=debug)


@main.command(name="init-db")
@click.option("--env-file", default=None, help="Path to .env file")
def init_db(env_file: str | None):
    """Initialize database tables."""
    from ae_pinner.database import Database

    config = Config.load(env_file)

    if not config.db_host:
        console.print("[red]Database configuration required.[/]")
        console.print("Set DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in .env")
        sys.exit(1)

    try:
        db = Database(
            host=config.db_host,
            port=config.db_port,
            name=config.db_name,
            user=config.db_user,
            password=config.db_password,
        )
        db.init_tables()
        console.print("[green]Database tables created successfully![/]")
    except Exception as e:
        console.print(f"[red]Failed to initialize database:[/] {e}")
        sys.exit(1)


@main.command()
@click.option(
    "--plan",
    type=click.Path(exists=True, dir_okay=False),
    help="JSON/YAML automation plan file",
)
@click.option("--pages", default=1, help="Number of pages to process")
@click.option("--page", default=1, help="Starting page number")
@click.option("--count", default=12, help="Products per page (max 12)")
@click.option(
    "--ai",
    type=click.Choice(["gemini", "openai"]),
    default="gemini",
    help="AI provider for generating descriptions",
)
@click.option("--save", is_flag=True, help="Save fetched products to the database")
@click.option("--publish", is_flag=True, help="Automatically publish pins to Pinterest")
@click.option("--skip-generate", is_flag=True, help="Skip AI content generation")
@click.option("--dry-run", is_flag=True, help="Preview without creating pins")
@click.option("--delay", default=3.0, help="Seconds to wait between pages")
@click.option("--pin-delay", default=1.5, help="Seconds to wait between pins")
@click.option("--interval", default=0.0, help="Repeat every N minutes (0 = run once)")
@click.option("--max-runs", default=None, type=int, help="Limit scheduled repetitions")
@click.option("--env-file", default=None, help="Path to .env file")
def auto(
    plan: str | None,
    pages: int,
    page: int,
    count: int,
    ai: str,
    save: bool,
    publish: bool,
    skip_generate: bool,
    dry_run: bool,
    delay: float,
    pin_delay: float,
    interval: float,
    max_runs: int | None,
    env_file: str | None,
):
    """Run the advanced automation pipeline: fetch -> generate -> publish."""
    config = Config.load(env_file)

    if plan:
        auto_plan = AutomationPlan.load(plan)
    else:
        auto_plan = AutomationPlan(
            pages=pages,
            page=page,
            page_size=count,
            ai=ai,
            save=save,
            generate=not skip_generate,
            publish=publish,
            dry_run=dry_run,
            page_delay=delay,
            pin_delay=pin_delay,
            interval_minutes=interval,
            max_runs=max_runs,
        )

    db = None
    if auto_plan.save:
        if not config.db_configured:
            console.print("[red]--save requires DB_HOST, DB_NAME, DB_USER, DB_PASSWORD[/]")
            sys.exit(1)
        db = Database(
            host=config.db_host,
            port=config.db_port,
            name=config.db_name,
            user=config.db_user,
            password=config.db_password,
        )

    try:
        asyncio.run(run_automation(config, auto_plan, db=db))
    except KeyboardInterrupt:
        console.print("\n[yellow]Automation stopped by user.[/]")
        sys.exit(0)
    except Exception as exc:
        console.print(f"[red]Automation failed:[/] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
