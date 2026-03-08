import asyncio
import gzip
import json
import logging
import shutil
import uuid
import yaml
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

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
            # Let Chrome use its real UA — hardcoding creates a mismatch
            # between declared UA and actual TLS/browser fingerprint,
            # which WAFs like Akamai Bot Manager detect.
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
            # Browser locale (ISO-639-1 code only)
            "lang": "fr",
        }

        config_path = local_dir / "crawl-config.yaml"
        config_path.write_text(yaml.dump(config, default_flow_style=False))

        # The config file must be readable inside the container at /crawls/
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_dir}:/crawls/",
            settings.browsertrix_image,
            "crawl",
            "--config", "/crawls/crawl-config.yaml",
            # Stealth flags to reduce bot detection by WAFs (Akamai, etc.)
            "--extraChromeArgs",
            "--disable-blink-features=AutomationControlled",
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

            # Clean 403 entries and rebuild CDXJ as multi-member gzip
            self._rebuild_wacz_index(wacz_path)

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
    def _rebuild_wacz_index(wacz_path: Path) -> None:
        """Clean and rebuild the WACZ CDXJ index.

        Two fixes applied:
        1. Remove 403 responses (CDN bot-detection artifacts like Akamai).
        2. Rebuild index.cdx.gz as multi-member gzip with a correct index.idx.
           Browsertrix-crawler sometimes emits a single-member gzip, which
           makes ReplayWeb.page unable to find entries beyond the first block.
        """
        BLOCK_SIZE = 100  # CDXJ lines per gzip member

        try:
            with zipfile.ZipFile(wacz_path, "r") as zin:
                cdx_data = gzip.decompress(zin.read("indexes/index.cdx.gz")).decode()

            # --- Step 1: filter out 403 entries ---
            filtered = []
            removed = 0
            for line in cdx_data.splitlines():
                if not line.strip():
                    continue
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    try:
                        meta = json.loads(parts[2])
                        if meta.get("status") == "403":
                            removed += 1
                            continue
                    except (json.JSONDecodeError, KeyError):
                        pass
                filtered.append(line)

            if removed:
                logger.info("Cleaned WACZ index: removed %d x 403 entries", removed)

            # --- Step 2: rebuild as multi-member gzip + index.idx ---
            # Split CDXJ lines into blocks, compress each as a separate
            # gzip member. Build index.idx with byte offsets per block.
            cdx_gz_parts = []
            idx_lines = ['!meta 0 {"format":"cdxj-gzip-1.0","filename":"index.cdx.gz"}']
            offset = 0

            for i in range(0, len(filtered), BLOCK_SIZE):
                block_lines = filtered[i : i + BLOCK_SIZE]
                block_bytes = ("\n".join(block_lines) + "\n").encode()
                compressed = gzip.compress(block_bytes)

                # index.idx entry: first SURT key + timestamp of the block
                first_line = block_lines[0]
                parts = first_line.split(" ", 2)
                surt_key = parts[0] if parts else ""
                timestamp = parts[1] if len(parts) > 1 else ""
                idx_meta = json.dumps({
                    "offset": offset,
                    "length": len(compressed),
                    "filename": "index.cdx.gz",
                })
                idx_lines.append(f"{surt_key} {timestamp} {idx_meta}")

                cdx_gz_parts.append(compressed)
                offset += len(compressed)

            new_cdx_gz = b"".join(cdx_gz_parts)
            new_idx = "\n".join(idx_lines) + "\n"

            # --- Step 3: rebuild the WACZ ZIP ---
            tmp = NamedTemporaryFile(
                dir=wacz_path.parent, suffix=".wacz", delete=False
            )
            try:
                with zipfile.ZipFile(wacz_path, "r") as zin, \
                     zipfile.ZipFile(tmp.name, "w") as zout:
                    for info in zin.infolist():
                        if info.filename == "indexes/index.cdx.gz":
                            zout.writestr(info, new_cdx_gz)
                        elif info.filename == "indexes/index.idx":
                            zout.writestr(info, new_idx.encode())
                        else:
                            zout.writestr(info, zin.read(info.filename))
                Path(tmp.name).replace(wacz_path)
                logger.info(
                    "Rebuilt WACZ index: %d entries in %d blocks",
                    len(filtered), len(cdx_gz_parts),
                )
            except Exception:
                Path(tmp.name).unlink(missing_ok=True)
                raise

        except Exception as e:
            logger.warning("Failed to rebuild WACZ index: %s", e)

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
