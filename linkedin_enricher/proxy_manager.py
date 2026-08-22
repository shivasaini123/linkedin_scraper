import itertools
import logging
import random
import time
from typing import Dict, List, Optional

logger = logging.getLogger("ProxyManager")

class ProxyManager:
    """
    Proxy & IP Rotation Manager supporting HTTP, HTTPS, and SOCKS5 proxies.
    Features automatic health checking, cool-off periods for rate-limited IPs, and per-worker rotation.
    """

    def __init__(self, proxy_list: Optional[List[str]] = None, cool_off_seconds: int = 300):
        self.raw_proxies = proxy_list or []
        self.cool_off_seconds = cool_off_seconds
        self.failed_proxies: Dict[str, float] = {}  # proxy -> failed_timestamp
        self.proxy_cycle = None
        self._initialize_cycle()

    def set_proxies(self, proxies: List[str]):
        self.raw_proxies = proxies
        self.failed_proxies.clear()
        self._initialize_cycle()

    def _initialize_cycle(self):
        if self.raw_proxies:
            self.proxy_cycle = itertools.cycle(self.raw_proxies)

    def get_active_proxies(self) -> List[str]:
        now = time.time()
        active = []
        for p in self.raw_proxies:
            if p in self.failed_proxies:
                if now - self.failed_proxies[p] > self.cool_off_seconds:
                    del self.failed_proxies[p]
                    active.append(p)
            else:
                active.append(p)
        return active

    def get_proxy(self) -> Optional[str]:
        """Returns the next available proxy URL or None if proxy pool is empty."""
        active = self.get_active_proxies()
        if not active:
            return None
        return random.choice(active)

    def mark_failed(self, proxy_url: str, status_code: Optional[int] = None):
        """Marks a proxy as failed or rate-limited, placing it in temporary cool-off."""
        if proxy_url:
            logger.warning(f"Proxy failed/rate-limited (Status: {status_code}): {proxy_url}")
            self.failed_proxies[proxy_url] = time.time()

    def get_httpx_proxy(self) -> Optional[str]:
        """Returns proxy string ready for httpx client."""
        return self.get_proxy()

    def get_playwright_proxy(self) -> Optional[Dict[str, str]]:
        """Returns proxy dict formatted for Playwright browser context."""
        proxy_str = self.get_proxy()
        if not proxy_str:
            return None

        # Parse user:pass@ip:port or http://ip:port
        clean = proxy_str.replace("http://", "").replace("https://", "").replace("socks5://", "")
        if "@" in clean:
            auth, server = clean.split("@", 1)
            username, password = auth.split(":", 1)
            return {
                "server": f"http://{server}",
                "username": username,
                "password": password
            }
        else:
            return {"server": f"http://{clean}"}
