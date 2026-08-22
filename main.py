import argparse
import asyncio
import logging
import os
import sys
import time
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.table import Table
from rich.live import Live

from linkedin_enricher.config import ScraperConfig
from linkedin_enricher.proxy_manager import ProxyManager
from linkedin_enricher.human_emulation import HumanEmulation
from linkedin_enricher.search_engine_fallback import SearchEngineFallback
from linkedin_enricher.browser_engine import StealthBrowserEngine
from linkedin_enricher.data_pipeline import DataPipeline

# Configure UTF-8 encoding for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Configure logging
logging.basicConfig(
    filename="scraper.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("LinkedInEnricherCLI")

console = Console()

def display_banner():
    banner_text = r"""[bold cyan]
  _     _       _            _ ___            ______            _ _ _                
 | |   (_)     | |          | |_  |          |  ____|          (_) (_)               
 | |    _ _ __ | | _____  __| | | |  _ __ ___| |__   _ __  _ __ _ _ _ __   __ _ ___  
 | |   | | '_ \| |/ / _ \/ _` | | | | '_ ` _ \  __| | '_ \| '__| | | '_ \ / _` / __| 
 | |___| | | | |   <  __/ (_| |_| |_| | | | | | |____| | | | |  | | | | | | (_| \__ \ 
 |______|_|_| |_|_|\_\___|\__,_(_)___|_| |_| |_|______|_| |_|_|  |_|_|_| |_|\__, |___/ 
                                                                             __/ |   
                                                                            |___/    
    [/bold cyan]
    [bold green]High-Throughput LinkedIn Data Enrichment Tool (1M Records Scale)[/bold green]
    [yellow]Features: Proxy Rotation | Stealth Browser | Human Emulation | Anti-Block Checkpoints[/yellow]
    """
    console.print(Panel(banner_text, expand=False, border_style="cyan"))

async def worker_task(
    worker_id: int,
    queue_item: dict,
    config: ScraperConfig,
    proxy_manager: ProxyManager,
    data_pipeline: DataPipeline,
    search_fallback: SearchEngineFallback,
    stealth_browser: StealthBrowserEngine
):
    item_id = queue_item["id"]
    username = queue_item["username"]
    city = queue_item.get("city", "Seattle")
    orig_company = queue_item.get("orig_company", "")


    try:
        # Step 1: Human Emulation Random Delay
        await HumanEmulation.random_delay(config.min_human_delay, config.max_human_delay)

        # Step 2: Primary Fast X-Ray Search Engine Method
        result = await search_fallback.enrich_user(username, city, orig_company)
        company = result.get("company")
        profile_url = result.get("profile_url")


        # Step 3: Stealth Browser Verification (if X-Ray search needs verification)
        if (not company or company == "Not Found") and config.stealth_browser_fallback and profile_url:
            browser_res = await stealth_browser.fetch_profile_details(profile_url)
            if browser_res.get("company"):
                company = browser_res["company"]

        status = "COMPLETED" if (company and company != "Not Found") else "NOT_FOUND"
        data_pipeline.update_result(item_id, company, profile_url, status)

        if company and company != "Not Found":
            console.print(f"[bold green]✔ [{username}] -> Current Company: [white]{company}[/white] | Profile: {profile_url}[/bold green]")
        else:
            console.print(f"[dim yellow]✖ [{username}] -> Not Found[/dim yellow]")

    except Exception as e:
        logger.error(f"Worker {worker_id} error processing {username}: {e}")
        data_pipeline.update_result(item_id, "Error", "", "FAILED", str(e))
        console.print(f"[bold red]✘ [{username}] -> Error: {e}[/bold red]")


async def main_async(args):
    config = ScraperConfig(
        input_file=args.input,
        output_file=args.output,
        concurrency=args.workers,
        proxy_file=args.proxies,
        headless_browser=args.headless
    )

    # Initialize Proxy Manager
    proxy_manager = ProxyManager()
    num_proxies = config.load_proxies_from_file()
    if num_proxies > 0:
        proxy_manager.set_proxies(config.proxy_list)
        console.print(f"[bold green]✔ Loaded {num_proxies} proxies from {config.proxy_file}[/bold green]")
    else:
        console.print(f"[bold yellow]⚠ No proxies loaded. Operating in direct connection mode.[/bold yellow]")

    # Initialize Pipeline & Engines
    pipeline = DataPipeline(db_path=config.db_file)
    
    if args.reset_db:
        pipeline.reset_queue()
        console.print("[bold red]Cleared database queue for fresh start.[/bold red]")

    # Import Input Dataset into Database Queue
    if os.path.exists(config.input_file):
        imported = pipeline.import_csv(config.input_file, default_state=config.default_state)
        console.print(f"[bold cyan]Database ready. Queue contains total dataset records.[/bold cyan]")

    if args.export_only:
        exported = pipeline.export_to_csv(config.output_file)
        console.print(f"[bold green]Exported {exported} rows to {config.output_file}[/bold green]")
        return

    search_fallback = SearchEngineFallback(config=config, proxy_manager=proxy_manager)
    stealth_browser = StealthBrowserEngine(config=config, proxy_manager=proxy_manager)

    stats = pipeline.get_statistics()
    total_items = stats["total"]
    completed_items = stats["completed"] + stats["failed"]
    pending_items = stats["pending"]

    console.print(f"[bold white]Progress Snapshot: Total: {total_items} | Completed: {stats['completed']} | Pending: {pending_items} | Failed: {stats['failed']}[/bold white]\n")

    if pending_items == 0:
        console.print("[bold green]All items in queue have been processed! Exporting CSV...[/bold green]")
        exported = pipeline.export_to_csv(config.output_file)
        console.print(f"[bold green]Saved output to [underline]{config.output_file}[/underline][/bold green]")
        return

    # Rich Progress Bar setup
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TextColumn("[bold yellow]Completed: {task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Enriching LinkedIn Data...", total=total_items, completed=completed_items)

        try:
            while True:
                # Fetch pending batch from queue
                batch = pipeline.get_pending_batch(limit=config.concurrency)
                if not batch:
                    break

                batch_ids = [item["id"] for item in batch]
                pipeline.mark_processing(batch_ids)

                # Spawn async workers for current batch
                tasks = [
                    worker_task(
                        worker_id=idx,
                        queue_item=item,
                        config=config,
                        proxy_manager=proxy_manager,
                        data_pipeline=pipeline,
                        search_fallback=search_fallback,
                        stealth_browser=stealth_browser
                    )
                    for idx, item in enumerate(batch)
                ]

                await asyncio.gather(*tasks)
                
                # Update progress bar
                current_stats = pipeline.get_statistics()
                new_completed = current_stats["completed"] + current_stats["failed"]
                progress.update(task, completed=new_completed)

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Gracefully pausing execution... Saving checkpoint state.[/bold yellow]")
        finally:
            exported = pipeline.export_to_csv(config.output_file)
            console.print(f"\n[bold green]✔ Output saved to [underline]{config.output_file}[/underline][/bold green]")

def parse_args():
    parser = argparse.ArgumentParser(description="LinkedIn High-Throughput Data Enrichment Tool")
    parser.add_argument("--input", "-i", default="shiva.csv", help="Path to input CSV file")
    parser.add_argument("--output", "-o", default="enriched_linkedin_data.csv", help="Path to output CSV file")
    parser.add_argument("--workers", "-w", type=int, default=5, help="Number of concurrent worker tasks")
    parser.add_argument("--proxies", "-p", default="proxies.txt", help="Path to proxy list file")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode")
    parser.add_argument("--reset-db", action="store_true", help="Reset SQLite checkpoint database before starting")
    parser.add_argument("--export-only", action="store_true", help="Export existing checkpoint DB to CSV without scraping")
    return parser.parse_args()

if __name__ == "__main__":
    display_banner()
    args = parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        console.print("[bold red]Application interrupted by user.[/bold red]")
        sys.exit(0)
