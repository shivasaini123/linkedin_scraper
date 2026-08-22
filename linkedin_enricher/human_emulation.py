import asyncio
import math
import random
import time
from typing import Tuple

class HumanEmulation:
    """
    Simulates human browsing behavior: Gaussian delays, mouse movements via Bezier curves,
    and natural scroll actions to prevent bot detection algorithms.
    """

    @staticmethod
    async def random_delay(min_seconds: float = 1.5, max_seconds: float = 4.0):
        """Generates realistic delay using Gaussian distribution with mean at midpoint."""
        mean = (min_seconds + max_seconds) / 2.0
        std_dev = (max_seconds - min_seconds) / 4.0
        delay = random.gauss(mean, std_dev)
        clamped_delay = max(min_seconds, min(max_seconds, delay))
        await asyncio.sleep(clamped_delay)

    @staticmethod
    async def micro_pause():
        """Short pause simulating reading or scanning a webpage section."""
        await asyncio.sleep(random.uniform(0.3, 0.9))

    @staticmethod
    async def simulate_human_scroll(page, num_scrolls: int = 3):
        """Simulates natural human mouse scrolling down and back up slightly."""
        for _ in range(num_scrolls):
            scroll_amount = random.randint(250, 600)
            await page.evaluate(f"window.scrollBy({{top: {scroll_amount}, behavior: 'smooth'}});")
            await asyncio.sleep(random.uniform(0.6, 1.4))
            
            # 20% chance of small scroll back up (reading behavior)
            if random.random() < 0.2:
                up_amount = random.randint(50, 150)
                await page.evaluate(f"window.scrollBy({{top: -{up_amount}, behavior: 'smooth'}});")
                await asyncio.sleep(random.uniform(0.4, 0.8))

    @staticmethod
    def generate_bezier_path(start: Tuple[int, int], end: Tuple[int, int], steps: int = 25):
        """Generates a human-like mouse curve trajectory using cubic Bezier points."""
        x1, y1 = start
        x2, y2 = end

        # Generate random control points for natural curve deviation
        ctrl1_x = x1 + random.randint(-100, 100) + (x2 - x1) * 0.25
        ctrl1_y = y1 + random.randint(-100, 100) + (y2 - y1) * 0.25
        ctrl2_x = x1 + random.randint(-100, 100) + (x2 - x1) * 0.75
        ctrl2_y = y1 + random.randint(-100, 100) + (y2 - y1) * 0.75

        points = []
        for i in range(steps + 1):
            t = i / float(steps)
            # Cubic Bezier formula
            x = (1-t)**3 * x1 + 3*(1-t)**2 * t * ctrl1_x + 3*(1-t) * t**2 * ctrl2_x + t**3 * x2
            y = (1-t)**3 * y1 + 3*(1-t)**2 * t * ctrl1_y + 3*(1-t) * t**2 * ctrl2_y + t**3 * y2
            points.append((int(x), int(y)))
        return points

    @staticmethod
    async def move_mouse_naturally(page, start_x: int, start_y: int, end_x: int, end_y: int):
        """Moves mouse across page using Bezier curve path."""
        path = HumanEmulation.generate_bezier_path((start_x, start_y), (end_x, end_y))
        for x, y in path:
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.005, 0.02))
