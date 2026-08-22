import os
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ScraperConfig:
    # Input / Output File Paths
    input_file: str = "shiva.csv"
    output_file: str = "enriched_linkedin_data.csv"
    db_file: str = "checkpoint_queue.db"
    proxy_file: str = "proxies.txt"
    
    # State / Location Scope
    default_state: str = "Washington"
    default_state_code: str = "WA"
    
    # Performance & Concurrency Settings
    concurrency: int = 5
    max_retries: int = 3
    request_timeout: int = 25
    batch_size: int = 50
    
    # Anti-Blocking & Stealth Settings
    enable_proxies: bool = False
    proxy_list: List[str] = field(default_factory=list)
    search_engine_fallback: bool = True
    stealth_browser_fallback: bool = True
    
    # Human Emulation Timers (seconds)
    min_human_delay: float = 1.5
    max_human_delay: float = 4.5
    headless_browser: bool = True

    def load_proxies_from_file(self):
        if os.path.exists(self.proxy_file):
            with open(self.proxy_file, "r", encoding="utf-8") as f:
                proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                if proxies:
                    self.proxy_list = proxies
                    self.enable_proxies = True
            return len(self.proxy_list)
        return 0
