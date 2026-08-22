import asyncio
import logging
import random
from typing import Dict, Optional
from playwright.async_api import async_playwright

from linkedin_enricher.config import ScraperConfig
from linkedin_enricher.human_emulation import HumanEmulation
from linkedin_enricher.proxy_manager import ProxyManager
from linkedin_enricher.session_manager import SessionManager

logger = logging.getLogger("BrowserEngine")

class StealthBrowserEngine:
    """
    Playwright Stealth Browser Engine.
    Executes automated profile verification in a headless/headed browser with anti-bot evasion techniques.
    """

    def __init__(self, config: ScraperConfig, proxy_manager: Optional[ProxyManager] = None):
        self.config = config
        self.proxy_manager = proxy_manager
        self.session_manager = SessionManager()

    async def fetch_profile_details(self, profile_url: str) -> Dict[str, Optional[str]]:
        """
        Launches stealth browser context, navigates to profile URL, and extracts current company.
        """
        result = {"company": None, "profile_url": profile_url, "success": False}
        
        proxy_settings = self.proxy_manager.get_playwright_proxy() if self.proxy_manager else None
        user_agent = self.session_manager.get_random_user_agent()

        async with async_playwright() as p:
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors",
            ]

            browser = await p.chromium.launch(
                headless=self.config.headless_browser,
                args=browser_args,
                proxy=proxy_settings
            )

            context = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
                locale="en-US",
                timezone_id="America/Los_Angeles"
            )

            # Inject Stealth Scripts into Page Context
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """)

            page = await context.new_page()

            try:
                # Navigate safely with randomized timeout
                await page.goto(profile_url, timeout=self.config.request_timeout * 1000, wait_until="domcontentloaded")
                await HumanEmulation.micro_pause()
                await HumanEmulation.simulate_human_scroll(page, num_scrolls=2)

                # Extract company name from meta tags or profile headers
                og_title = await page.get_attribute('meta[property="og:title"]', "content") or ""
                og_description = await page.get_attribute('meta[property="og:description"]', "content") or ""

                company = self.parse_meta_info(og_title, og_description)
                
                if company:
                    result["company"] = company
                    result["success"] = True
                
            except Exception as e:
                logger.warning(f"Browser navigation error for {profile_url}: {e}")
            finally:
                await context.close()
                await browser.close()

        return result

    def parse_meta_info(self, title: str, description: str) -> Optional[str]:
        """Parses OpenGraph metadata for current company."""
        import re
        combined = f"{title} {description}"
        m = re.search(r'\bat\s+([A-Z0-9\s\,\.\&\-\'\"]+?)(?:\s*[\-\|]|\.|$)', combined, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None
