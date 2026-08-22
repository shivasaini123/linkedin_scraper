import asyncio
import logging
import re
import urllib.parse
from typing import Dict, Optional, Tuple
import httpx
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from linkedin_enricher.config import ScraperConfig
from linkedin_enricher.proxy_manager import ProxyManager

logger = logging.getLogger("SearchEngineFallback")

class SearchEngineFallback:
    """
    High-Speed Multi-Engine X-Ray Search Engine Parser (Yahoo + Bing + DuckDuckGo + Playwright).
    Queries search engines for LinkedIn profiles and extracts current company names
    from public snippets without requiring LinkedIn login.
    """

    def __init__(self, config: ScraperConfig, proxy_manager: Optional[ProxyManager] = None):
        self.config = config
        self.proxy_manager = proxy_manager
        self.ua = UserAgent()

    def _get_headers(self) -> Dict[str, str]:
        try:
            user_agent = self.ua.random
        except Exception:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

        return {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        }

    async def fetch_search_results_bing(self, username: str, city: str, orig_company: str = "") -> Tuple[Optional[str], Optional[str]]:
        """Queries Bing Search endpoint for LinkedIn profile snippets."""
        query_parts = [f'site:linkedin.com/in/ "{username}"']
        if orig_company:
            query_parts.append(orig_company)
        query = " ".join(query_parts)
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&cc=us&setlang=en-us"

        headers = self._get_headers()
        proxy = self.proxy_manager.get_httpx_proxy() if self.proxy_manager else None

        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=self.config.request_timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    comp, link = self.parse_bing_html(resp.text, username)
                    if comp:
                        return comp, link
                elif resp.status_code in (429, 403) and self.proxy_manager and proxy:
                    self.proxy_manager.mark_failed(proxy, resp.status_code)
        except Exception as e:
            logger.debug(f"Bing search error: {e}")
            if self.proxy_manager and proxy:
                self.proxy_manager.mark_failed(proxy)

        # Fallback query without orig_company if first attempt didn't yield results
        if orig_company:
            try:
                fallback_url = f"https://www.bing.com/search?q={urllib.parse.quote(f'site:linkedin.com/in/ \"{username}\"')}&cc=us&setlang=en-us"
                async with httpx.AsyncClient(proxy=proxy, timeout=self.config.request_timeout, follow_redirects=True) as client:
                    resp = await client.get(fallback_url, headers=headers)
                    if resp.status_code == 200:
                        return self.parse_bing_html(resp.text, username)
            except Exception:
                pass

        return None, None

    def parse_bing_html(self, html: str, username: str) -> Tuple[Optional[str], Optional[str]]:
        soup = BeautifulSoup(html, "html.parser")
        algos = soup.find_all("li", class_=re.compile("b_algo"))
        first_name = username.split()[0].lower() if username else ""

        for item in algos:
            h2 = item.find("h2")
            a_tag = h2.find("a") if h2 else item.find("a", href=re.compile(r'linkedin\.com/in/'))
            if not a_tag:
                continue

            snippet_el = item.find("div", class_=re.compile("b_caption")) or item.find("p")
            
            title_text = h2.get_text(strip=True) if h2 else ""
            snippet_text = snippet_el.get_text(strip=True) if snippet_el else ""
            href = a_tag.get("href", "")

            if "linkedin.com/in/" in href or "linkedin" in title_text.lower():
                if first_name and first_name not in title_text.lower() and first_name not in snippet_text.lower():
                    continue

                company = self.parse_company_from_text(title_text, snippet_text)
                clean_url = self.clean_linkedin_url(href)
                if company:
                    return company, clean_url

        return None, None

    async def fetch_search_results_duckduckgo(self, username: str, city: str, orig_company: str = "") -> Tuple[Optional[str], Optional[str]]:
        """Queries DuckDuckGo HTML search endpoint for LinkedIn profile snippets."""
        query_parts = [f'site:linkedin.com/in/ "{username}"']
        if orig_company:
            query_parts.append(orig_company)
        query = " ".join(query_parts)
        url = "https://html.duckduckgo.com/html/"

        headers = self._get_headers()
        proxy = self.proxy_manager.get_httpx_proxy() if self.proxy_manager else None

        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=self.config.request_timeout, follow_redirects=True) as client:
                resp = await client.post(url, data={"q": query}, headers=headers)
                if resp.status_code == 200:
                    comp, link = self.parse_duckduckgo_html(resp.text, username)
                    if comp:
                        return comp, link
        except Exception as e:
            logger.debug(f"DuckDuckGo search error: {e}")

        # Fallback query without orig_company
        if orig_company:
            try:
                async with httpx.AsyncClient(proxy=proxy, timeout=self.config.request_timeout, follow_redirects=True) as client:
                    resp = await client.post(url, data={"q": f'site:linkedin.com/in/ "{username}"'}, headers=headers)
                    if resp.status_code == 200:
                        return self.parse_duckduckgo_html(resp.text, username)
            except Exception:
                pass

        return None, None

    def parse_duckduckgo_html(self, html: str, username: str) -> Tuple[Optional[str], Optional[str]]:
        soup = BeautifulSoup(html, "html.parser")
        results = soup.find_all("div", class_=re.compile("result"))
        first_name = username.split()[0].lower() if username else ""

        for item in results:
            a_tag = item.find("a", class_=re.compile("result__title|result__url")) or item.find("a")
            if not a_tag:
                continue

            snippet_el = item.find("a", class_=re.compile("result__snippet")) or item.find("div", class_=re.compile("snippet"))
            title_text = a_tag.get_text(strip=True)
            snippet_text = snippet_el.get_text(strip=True) if snippet_el else ""
            href = a_tag.get("href", "")

            if "linkedin.com/in/" in href or "linkedin" in title_text.lower():
                if first_name and first_name not in title_text.lower() and first_name not in snippet_text.lower():
                    continue

                company = self.parse_company_from_text(title_text, snippet_text)
                clean_url = self.clean_linkedin_url(href)
                if company:
                    return company, clean_url

        return None, None

    async def fetch_search_results_yahoo(self, username: str, city: str, orig_company: str = "") -> Tuple[Optional[str], Optional[str]]:
        """Queries Yahoo Search endpoint for high-accuracy LinkedIn profile snippets."""
        query_parts = [f'site:linkedin.com/in/ "{username}"']
        if orig_company:
            query_parts.append(orig_company)
        query = " ".join(query_parts)
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}"

        headers = self._get_headers()
        proxy = self.proxy_manager.get_httpx_proxy() if self.proxy_manager else None

        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=self.config.request_timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    comp, link = self.parse_yahoo_html(resp.text, username)
                    if comp:
                        return comp, link
                elif resp.status_code in (429, 403) and self.proxy_manager and proxy:
                    self.proxy_manager.mark_failed(proxy, resp.status_code)
        except Exception as e:
            logger.debug(f"Yahoo search error: {e}")
            if self.proxy_manager and proxy:
                self.proxy_manager.mark_failed(proxy)

        # Fallback query without orig_company
        if orig_company:
            try:
                fallback_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(f'site:linkedin.com/in/ \"{username}\"')}"
                async with httpx.AsyncClient(proxy=proxy, timeout=self.config.request_timeout, follow_redirects=True) as client:
                    resp = await client.get(fallback_url, headers=headers)
                    if resp.status_code == 200:
                        return self.parse_yahoo_html(resp.text, username)
            except Exception:
                pass

        return None, None

    def parse_yahoo_html(self, html: str, username: str) -> Tuple[Optional[str], Optional[str]]:
        soup = BeautifulSoup(html, "html.parser")
        algos = soup.find_all("div", class_=re.compile("algo|dd"))
        first_name = username.split()[0].lower() if username else ""

        for item in algos:
            a_tag = item.find("a", href=re.compile(r'linkedin\.com/in/')) or item.find("a")
            if not a_tag:
                continue

            h3 = item.find("h3")
            snippet_el = item.find("div", class_=re.compile("compText|snippet")) or item.find("p")
            
            title_text = h3.get_text(strip=True) if h3 else item.get_text(separator=" ", strip=True)
            snippet_text = snippet_el.get_text(strip=True) if snippet_el else ""
            href = a_tag.get("href", "")
            
            if "linkedin.com/in/" in href or "linkedin" in title_text.lower():
                if first_name and first_name not in title_text.lower() and first_name not in snippet_text.lower():
                    continue

                company = self.parse_company_from_text(title_text, snippet_text)
                clean_url = self.clean_linkedin_url(href)
                if company:
                    return company, clean_url

        return None, None

    async def search_via_playwright(self, username: str, city: str, orig_company: str = "") -> Tuple[Optional[str], Optional[str]]:
        """Fallback method using Playwright stealth browser to execute live Yahoo search query."""
        from playwright.async_api import async_playwright
        proxy_settings = self.proxy_manager.get_playwright_proxy() if self.proxy_manager else None

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config.headless_browser,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                proxy=proxy_settings
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="en-US"
            )
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            page = await context.new_page()

            try:
                query = f'site:linkedin.com/in/ "{username}" {orig_company}'.strip()
                search_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}"
                await page.goto(search_url, timeout=self.config.request_timeout * 1000, wait_until="domcontentloaded")
                await asyncio.sleep(1.5)

                algos = await page.query_selector_all(".algo")
                for item in algos:
                    h3 = await item.query_selector("h3.title a") or await item.query_selector("a")
                    snippet_el = await item.query_selector(".compText") or await item.query_selector("p")

                    title = await h3.inner_text() if h3 else ""
                    href = await h3.get_attribute("href") if h3 else ""
                    snippet = await snippet_el.inner_text() if snippet_el else ""

                    if "linkedin.com/in/" in href or "linkedin" in title.lower():
                        company = self.parse_company_from_text(title, snippet)
                        clean_url = self.clean_linkedin_url(href)
                        if company:
                            await context.close()
                            await browser.close()
                            return company, clean_url

            except Exception as e:
                logger.debug(f"Playwright search fallback error: {e}")
            finally:
                await context.close()
                await browser.close()

        return None, None

    def parse_company_from_text(self, title: str, snippet: str) -> Optional[str]:
        """Extracts current company name using multi-pattern regex matching from experience/titles."""
        combined = f"{title} | {snippet}"

        # 1. Look for 'Position at CompanyName' (e.g., 'Vice President at Microsoft' or 'Director at Cascade Hardwood LLC')
        m1 = re.search(r'\bat\s+([A-Z0-9\s\,\.\&\-\'\"]+?)(?:\s*[\·\-\|\,]|\s+in\s+|\.|\s+Location:|\s+Experience:|$)', combined, re.IGNORECASE)
        if m1:
            comp = self._clean_company_str(m1.group(1))
            if self._is_valid_company_name(comp):
                return comp

        # 2. Look for 'Current: ... at/ - CompanyName' or 'Present: ... at/ - CompanyName'
        m_curr = re.search(r'\b(?:Current|Present):\s*([A-Z0-9\s\,\.\&\-\'\"]+?)(?:\s*[\·\-\|]|\s+Past:|\s+Location:|$)', combined, re.IGNORECASE)
        if m_curr:
            raw_curr = m_curr.group(1)
            if " at " in raw_curr.lower():
                raw_curr = raw_curr.split(" at ")[-1]
            elif " - " in raw_curr:
                raw_curr = raw_curr.split(" - ")[-1]
            comp = self._clean_company_str(raw_curr)
            if self._is_valid_company_name(comp):
                return comp

        # 3. Look for 'Experience: Position - CompanyName' or 'Experience: CompanyName'
        m0 = re.search(r'Experience:\s*([A-Z0-9\s\,\.\&\-\'\"]+?)(?:\s*[\·\-\|]|\s+Location:|$)', combined, re.IGNORECASE)
        if m0:
            raw_exp = m0.group(1)
            if " at " in raw_exp.lower():
                raw_exp = raw_exp.split(" at ")[-1]
            elif " - " in raw_exp:
                raw_exp = raw_exp.split(" - ")[-1]
            comp = self._clean_company_str(raw_exp)
            if self._is_valid_company_name(comp):
                return comp

        # 4. Look for 'Name - Company Name - LinkedIn' or 'Name - Position - Company Name | LinkedIn'
        m2 = re.search(r'[\-\–\—]\s*([A-Z0-9\s\,\.\&\-\'\"]+?)\s*(?:[\-\|]\s*LinkedIn|$)', title, re.IGNORECASE)
        if m2:
            raw_t = m2.group(1)
            if " - " in raw_t:
                raw_t = raw_t.split(" - ")[-1]
            comp = self._clean_company_str(raw_t)
            if self._is_valid_company_name(comp):
                return comp

        return None

    def _clean_company_str(self, raw_name: str) -> str:
        if not raw_name:
            return ""
        # Remove line breaks and normalize spaces
        cleaned = raw_name.replace("\n", " ").replace("\r", " ")
        cleaned = re.sub(r'\s+', ' ', cleaned)
        # Strip locations, regions, and unwanted trailing noise
        cleaned = re.sub(r'(?i)\b(Seattle|Redmond|Bellevue|Tacoma|Spokane|Washington|WA|United States|USA|Greater\s+[A-Za-z\s]+Area|Metropolitan\s+Area|Location:?|\.\.\.)\b', '', cleaned)
        cleaned = re.sub(r'^[,\.\s\-\|]+|[,\.\s\-\|]+$', '', cleaned)
        return cleaned.strip()

    def _is_valid_company_name(self, name: str) -> bool:
        if not name or len(name) < 2 or len(name) > 50:
            return False
        name_lower = name.lower()
        invalid_keywords = [
            "linkedin", "profile", "view", "connections", "washington", "wa",
            "united states", "see", "experience", "horoscope", "wikipedia", "imdb", "youtube", "location", "present", "past",
            "professional", "executive", "experienced", "specialist", "passionate", "helping", "building", "driving",
            "managing", "transforming", "enthusiast", "seeking", "looking for", "open to", "freelance", "self-employed",
            "metropolitan area", "greater", "area"
        ]
        for word in invalid_keywords:
            if word in name_lower:
                return False
        # Reject if string is just location noise or punctuation
        if re.match(r'^(united states|washington|seattle|redmond|bellevue|canada|\.|\s)+$', name, re.IGNORECASE):
            return False
        return True

    def clean_linkedin_url(self, raw_url: str) -> Optional[str]:
        m = re.search(r'(https?://[a-z]+\.linkedin\.com/in/[a-zA-Z0-9\-_]+)', raw_url)
        if m:
            return m.group(1)
        return None

    async def enrich_user(self, username: str, city: str, orig_company: str = "") -> Dict[str, Optional[str]]:
        """Main method to query multi-engine X-Ray search (Bing -> DuckDuckGo -> Yahoo -> Playwright) and return enriched company data."""
        # 1. Try Bing Search
        company, profile_url = await self.fetch_search_results_bing(username, city, orig_company)
        
        # 2. Try DuckDuckGo Search if Bing returned no company
        if not company or company == "Not Found":
            company, profile_url = await self.fetch_search_results_duckduckgo(username, city, orig_company)

        # 3. Try Yahoo Search if still no company
        if not company or company == "Not Found":
            company, profile_url = await self.fetch_search_results_yahoo(username, city, orig_company)

        # 4. Try Playwright browser fallback if still no company
        if not company or company == "Not Found":
            company, profile_url = await self.search_via_playwright(username, city, orig_company)

        return {
            "username": username,
            "city": city,
            "company": company or "Not Found",
            "profile_url": profile_url or "",
            "method": "X-Ray Multi-Search",
            "status": "SUCCESS" if company and company != "Not Found" else "NOT_FOUND"
        }


