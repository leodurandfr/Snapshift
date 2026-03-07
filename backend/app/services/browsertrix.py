import asyncio
import logging
import shutil
import uuid
import yaml
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# Path to custom behavior scripts (relative to backend/)
BEHAVIORS_DIR = Path(__file__).resolve().parent.parent.parent / "behaviors"

# Third-party scripts that crash during replay because their APIs are unreachable.
# Blocking them during capture means they won't be in the WACZ at all,
# so the site's JS won't try to init them and crash.
DEFAULT_BLOCK_RULES = [
    # Analytics / tracking
    {"url": r"google-analytics\.com"},
    {"url": r"googletagmanager\.com"},
    {"url": r"googlesyndication\.com"},
    {"url": r"doubleclick\.net"},
    {"url": r"facebook\.(com|net)"},
    {"url": r"connect\.facebook"},
    {"url": r"hotjar\.com"},
    {"url": r"newrelic\.com"},
    {"url": r"nr-data\.net"},
    {"url": r"sentry\.io"},
    {"url": r"tags\.tiqcdn\.com"},
    {"url": r"tealiumiq\.com"},
    # APM / RUM monitoring
    {"url": r"ruxitagentjs"},
    {"url": r"dynatrace\.com"},
    {"url": r"rum\.cdn\.mkt\.go"},
    {"url": r"akstat\.io"},
    {"url": r"akamaized\.net/.*rum"},
    # Consent / cookie managers
    {"url": r"onetrust\.com"},
    {"url": r"cookielaw\.org"},
    {"url": r"osano\.com"},
    {"url": r"trustarc\.com"},
    {"url": r"quantcast\.com"},
    {"url": r"didomi\.io"},
    # Feature flags / A-B testing / personalization
    {"url": r"launchdarkly\.com"},
    {"url": r"optimizely\.com"},
    {"url": r"split\.io"},
    {"url": r"dynamicyield\.com"},
    {"url": r"abtasty\.com"},
    {"url": r"monetate\.net"},
    {"url": r"kameleoon\.eu"},
    # Bot detection (blocks crawlers)
    {"url": r"datadome\.co"},
    {"url": r"kasada\.io"},
    {"url": r"perimeterx\.net"},
]


@dataclass
class BrowsertrixResult:
    wacz_path: Path
    screenshot_path: Path | None


class BrowsertrixService:
    async def capture(self, url: str, capture_id: uuid.UUID) -> BrowsertrixResult | None:
        crawl_id = f"capture-{capture_id}"
        local_dir = Path(settings.browsertrix_crawl_dir) / str(capture_id)
        host_dir = (
            Path(settings.browsertrix_host_crawl_dir) / str(capture_id)
            if settings.browsertrix_host_crawl_dir
            else local_dir
        )

        local_dir.mkdir(parents=True, exist_ok=True)

        # Copy custom behavior script into the crawl dir (mounted into container at /crawls/)
        behavior_src = BEHAVIORS_DIR / "force-load-lazy.js"
        behavior_dst = local_dir / "force-load-lazy.js"
        if behavior_src.exists():
            shutil.copy2(behavior_src, behavior_dst)

        # Generate YAML config (needed for blockRules which has no CLI equivalent)
        config = {
            "seeds": [{"url": url, "depth": 0, "scopeType": "page"}],
            "blockRules": DEFAULT_BLOCK_RULES,
            "blockAds": True,
            # Realistic Chrome UA to avoid CDN anti-bot blocking (e.g. LV/Dior)
            "userAgent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            # Custom behavior replaces autoscroll with a more thorough version
            # that forces lazy-loaded images to load
            "behaviors": ["autoplay", "autofetch", "siteSpecific"],
            "customBehaviors": ["/crawls/force-load-lazy.js"],
            "behaviorTimeout": settings.browsertrix_time_limit,
            "postLoadDelay": 10,
            "pageExtraDelay": 5,
            "netIdleWait": 10,
            "generateWACZ": True,
            "limit": 1,
            "collection": crawl_id,
            "timeLimit": settings.browsertrix_time_limit,
            "screenshot": ["fullPage"],
            # Wait for network idle and full page load before behaviors
            "waitUntil": ["load", "networkidle0"],
        }

        config_path = local_dir / "crawl-config.yaml"
        config_path.write_text(yaml.dump(config, default_flow_style=False))

        # The config file must be readable inside the container at /crawls/
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_dir}:/crawls/",
            settings.browsertrix_image,
            "crawl",
            "--config", f"/crawls/crawl-config.yaml",
        ]

        timeout = settings.browsertrix_time_limit + 60

        try:
            logger.info("Starting browsertrix capture for %s", url)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning("Browsertrix timeout after %ds, killing process", timeout)
                proc.kill()
                await proc.wait()
                return None

            if proc.returncode != 0:
                stderr_text = stderr.decode(errors="replace")[-500:] if stderr else ""
                logger.error(
                    "Browsertrix failed (rc=%d) for %s: %s",
                    proc.returncode, url, stderr_text,
                )
                return None

            # Find the .wacz file
            wacz_path = local_dir / "collections" / crawl_id / f"{crawl_id}.wacz"
            if not wacz_path.exists():
                wacz_files = list(local_dir.rglob("*.wacz"))
                if wacz_files:
                    wacz_path = wacz_files[0]
                else:
                    logger.error("No .wacz file found in %s", local_dir)
                    return None

            # Check size limit
            size_mb = wacz_path.stat().st_size / (1024 * 1024)
            if size_mb > settings.browsertrix_size_limit_mb:
                logger.warning(
                    "WACZ too large (%.1f MB > %d MB limit) for %s, skipping",
                    size_mb, settings.browsertrix_size_limit_mb, url,
                )
                return None

            # Find screenshot in the output
            screenshot_path = self._find_screenshot(local_dir)

            logger.info(
                "Browsertrix capture OK: %s (%.1f MB, screenshot=%s)",
                url, size_mb, "yes" if screenshot_path else "no",
            )
            return BrowsertrixResult(wacz_path=wacz_path, screenshot_path=screenshot_path)

        except FileNotFoundError:
            logger.error("Docker CLI not found — cannot run browsertrix-crawler")
            return None
        except Exception as e:
            logger.error("Browsertrix capture error for %s: %s", url, e)
            return None

    @staticmethod
    def _find_screenshot(local_dir: Path) -> Path | None:
        """Find a screenshot PNG in the browsertrix output directory."""
        for f in sorted(local_dir.rglob("*.png")):
            # Filter out tiny files (favicons, etc.)
            if f.stat().st_size > 10_000:
                return f
        return None

    @staticmethod
    def cleanup(crawl_dir: Path) -> None:
        try:
            shutil.rmtree(crawl_dir, ignore_errors=True)
        except Exception as e:
            logger.warning("Failed to cleanup browsertrix dir %s: %s", crawl_dir, e)
