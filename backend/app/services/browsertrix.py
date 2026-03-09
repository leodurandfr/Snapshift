import asyncio
import gzip
import io
import json
import logging
import shutil
import sqlite3
import tarfile
import uuid
import yaml
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import urlparse

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
    {"url": r"go-mpulse\.net"},
    # Consent / cookie managers
    # NOTE: Do NOT block onetrust.com / cookielaw.org — their SDK defines
    # global functions (e.g. document._l) that many sites call at init.
    # Blocking them removes the script from the WACZ, causing "not a function"
    # crashes during replay.  The behavior script dismisses cookie banners instead.
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
    # E-commerce cart/checkout — page JS may call cart endpoints during capture
    # (e.g. SFCC Cart-AddProduct, minicart).  If these responses end up in the
    # WACZ, replay JS re-triggers them and shows cart popups over the page.
    {"url": r"Cart-AddProduct"},
    {"url": r"Cart-Show"},
    {"url": r"Cart-MiniCart"},
    {"url": r"cart\?isMiniCart"},
    {"url": r"/cart/add"},
    {"url": r"/cart\.js"},
    {"url": r"/api/cart"},
]


@dataclass
class BrowsertrixResult:
    wacz_path: Path
    screenshot_path: Path | None


class BrowsertrixService:
    async def capture(self, url: str, capture_id: uuid.UUID) -> BrowsertrixResult | None:
        crawl_id = f"capture-{capture_id}"
        local_dir = Path(settings.browsertrix_crawl_dir) / str(capture_id)
        use_volume = bool(settings.browsertrix_docker_volume)

        local_dir.mkdir(parents=True, exist_ok=True)

        # Copy custom behavior script into the crawl dir
        behavior_src = BEHAVIORS_DIR / "force-load-lazy.js"
        behavior_dst = local_dir / "force-load-lazy.js"
        if behavior_src.exists():
            shutil.copy2(behavior_src, behavior_dst)

        if use_volume:
            # Docker named volume: mount entire volume at /crawls/,
            # config and behavior in a capture-specific subdir.
            crawls_subdir = str(capture_id)
            behavior_container_path = f"/crawls/{crawls_subdir}/force-load-lazy.js"
            config_container_path = f"/crawls/{crawls_subdir}/crawl-config.yaml"
            volume_arg = f"{settings.browsertrix_docker_volume}:/crawls/"
        else:
            # Bind mount: mount capture-specific dir at /crawls/
            host_dir = (
                Path(settings.browsertrix_host_crawl_dir) / str(capture_id)
                if settings.browsertrix_host_crawl_dir
                else local_dir
            )
            behavior_container_path = "/crawls/force-load-lazy.js"
            config_container_path = "/crawls/crawl-config.yaml"
            volume_arg = f"{host_dir}:/crawls/"

        # --- Warm-up phase (separate Docker run) ---
        # Anti-bot WAFs (Akamai Bot Manager, etc.) set a validation cookie
        # (_abck) via client-side JS on the first page visit. Protected
        # sub-pages require this cookie. We run a quick, lightweight crawl
        # of the domain root to let the WAF JS execute and set the cookie,
        # then save the browser profile.  The real capture reuses that
        # profile, getting a fresh full page load (no SPA interference).
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}/"
        needs_warmup = (
            bool(parsed.scheme) and bool(parsed.netloc)
            and url.rstrip("/") != origin.rstrip("/")
        )

        # Stealth Chrome flags to reduce bot fingerprinting by WAFs.
        chrome_stealth_args = " ".join([
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--hide-scrollbars",
        ])

        profile_path: str | None = None
        if needs_warmup:
            profile_path = await self._run_warmup(
                origin, local_dir, volume_arg, use_volume,
                behavior_container_path, chrome_stealth_args,
            )

        # --- Main capture config ---
        config = {
            "seeds": [{"url": url, "depth": 0, "scopeType": "page"}],
            "blockRules": DEFAULT_BLOCK_RULES,
            # blockAds uses EasyList/EasyPrivacy which blocks consent managers
            # (cookielaw.org, onetrust.com) that define critical globals like
            # document._l — causing page init crashes during replay.
            # Our custom blockRules are sufficient.
            "blockAds": False,
            # Let Chrome use its real UA — hardcoding creates a mismatch
            # between declared UA and actual TLS/browser fingerprint,
            # which WAFs like Akamai Bot Manager detect.
            "behaviors": ["autoplay", "autofetch", "siteSpecific"],
            "customBehaviors": [behavior_container_path],
            "behaviorTimeout": settings.browsertrix_time_limit,
            "postLoadDelay": 5,
            "pageExtraDelay": 0,
            "netIdleWait": 5,
            "generateWACZ": True,
            "limit": 1,
            "collection": crawl_id,
            "timeLimit": settings.browsertrix_time_limit,
            "screenshot": ["fullPage"],
            "waitUntil": ["load", "networkidle2"],
            "lang": "fr",
        }

        config_path = local_dir / "crawl-config.yaml"
        config_path.write_text(yaml.dump(config, default_flow_style=False))

        cmd = [
            "docker", "run", "--rm",
            "--ulimit", "nofile=65536:65536",
            "-v", volume_arg,
            settings.browsertrix_image,
            "crawl",
            "--config", config_container_path,
            "--extraChromeArgs", chrome_stealth_args,
        ]
        if profile_path:
            cmd.extend(["--profile", profile_path])

        timeout = settings.browsertrix_time_limit + 120

        try:
            logger.info(
                "Starting browsertrix capture for %s (limit=%d, profile=%s)",
                url, config["limit"], "yes" if profile_path else "no",
            )
            logger.info("Browsertrix config:\n%s", yaml.dump(config, default_flow_style=False))
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

            stdout_text = stdout.decode(errors="replace") if stdout else ""
            stderr_text = stderr.decode(errors="replace") if stderr else ""
            # Always log browsertrix output for debugging
            for line in stdout_text.splitlines()[-30:]:
                logger.info("browsertrix: %s", line)
            if stderr_text.strip():
                for line in stderr_text.splitlines()[-10:]:
                    logger.warning("browsertrix stderr: %s", line)

            if proc.returncode != 0:
                logger.error(
                    "Browsertrix failed (rc=%d) for %s: %s",
                    proc.returncode, url, stderr_text[-500:],
                )
                return None

            # Find the .wacz file
            # With named volume, collections are at the volume root;
            # with bind mount, they're in the capture-specific subdir.
            crawl_base = Path(settings.browsertrix_crawl_dir) if use_volume else local_dir
            collection_dir = crawl_base / "collections" / crawl_id
            wacz_path = collection_dir / f"{crawl_id}.wacz"
            if not wacz_path.exists():
                wacz_files = list(collection_dir.rglob("*.wacz")) if collection_dir.exists() else []
                if wacz_files:
                    wacz_path = wacz_files[0]
                else:
                    logger.error("No .wacz file found in %s", collection_dir)
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

            # Find screenshot in the collection output dir (not the whole volume)
            screenshot_path = self._find_screenshot(collection_dir)

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

    async def _run_warmup(
        self,
        origin: str,
        local_dir: Path,
        volume_arg: str,
        use_volume: bool,
        behavior_container_path: str,
        chrome_stealth_args: str,
    ) -> str | None:
        """Run a lightweight crawl of the domain root to warm up cookies.

        Returns the container path to the saved browser profile (tar.gz),
        or None if the warm-up failed (non-fatal, capture continues without it).
        """
        warmup_id = "warmup"
        if use_volume:
            crawls_subdir = local_dir.name  # capture UUID
            config_path_container = f"/crawls/{crawls_subdir}/warmup-config.yaml"
            profile_save_path = f"/crawls/{crawls_subdir}/profile.tar.gz"
        else:
            config_path_container = "/crawls/warmup-config.yaml"
            profile_save_path = "/crawls/profile.tar.gz"

        warmup_config = {
            "seeds": [{"url": origin, "depth": 0, "scopeType": "page"}],
            "blockRules": DEFAULT_BLOCK_RULES,
            # blockAds uses EasyList/EasyPrivacy which blocks consent managers
            # (cookielaw.org, onetrust.com) that define critical globals like
            # document._l — causing page init crashes during replay.
            # Our custom blockRules are sufficient.
            "blockAds": False,
            # Run only the custom behavior (human simulation) — skip heavy
            # built-in behaviors to keep the warm-up fast.
            "behaviors": [],
            "customBehaviors": [behavior_container_path],
            "behaviorTimeout": 30,
            "postLoadDelay": 3,
            "netIdleWait": 3,
            "generateWACZ": False,
            "limit": 1,
            "collection": warmup_id,
            "timeLimit": 60,
            "waitUntil": ["load", "networkidle2"],
            "lang": "fr",
        }

        warmup_config_path = local_dir / "warmup-config.yaml"
        warmup_config_path.write_text(yaml.dump(warmup_config, default_flow_style=False))

        cmd = [
            "docker", "run", "--rm",
            "--ulimit", "nofile=65536:65536",
            "-v", volume_arg,
            settings.browsertrix_image,
            "crawl",
            "--config", config_path_container,
            "--extraChromeArgs", chrome_stealth_args,
            "--saveProfile", profile_save_path,
        ]

        try:
            logger.info("Warm-up: visiting %s to set WAF cookies", origin)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)

            stdout_text = stdout.decode(errors="replace") if stdout else ""
            for line in stdout_text.splitlines()[-10:]:
                logger.info("warmup: %s", line)

            if proc.returncode != 0:
                logger.warning(
                    "Warm-up failed (rc=%d), continuing without profile",
                    proc.returncode,
                )
                return None

            # Verify profile was saved
            profile_local = local_dir / "profile.tar.gz"
            if profile_local.exists() and profile_local.stat().st_size > 100:
                # Strip non-WAF cookies to avoid session pollution
                # (e.g. cart state from homepage causing dialogs on product pages)
                self._filter_profile_cookies(profile_local)
                logger.info(
                    "Warm-up OK: profile saved (%.1f KB)",
                    profile_local.stat().st_size / 1024,
                )
                return profile_save_path

            logger.warning("Warm-up: profile file not found or empty")
            return None

        except asyncio.TimeoutError:
            logger.warning("Warm-up timed out, continuing without profile")
            return None
        except Exception as e:
            logger.warning("Warm-up error: %s, continuing without profile", e)
            return None

    # Cookie name patterns to KEEP from the warmup profile.
    # These are WAF / bot-detection cookies that must survive for the
    # main capture to pass anti-bot checks.  Everything else (session,
    # cart, preferences, consent) is deleted to avoid polluting the
    # main capture with unwanted server-side state.
    WAF_COOKIE_PATTERNS = [
        # Akamai Bot Manager
        "_abck", "bm_sz", "ak_bmsc", "bm_mi", "bm_sv",
        # Cloudflare
        "cf_clearance", "__cf_bm", "cf_chl_",
        # PerimeterX / Human Security
        "_px", "_pxhd", "_pxvid", "_pxde",
        # DataDome
        "datadome",
        # Kasada
        "x-]]cd",
        # Incapsula / Imperva
        "incap_ses_", "visid_incap_", "nlbi_",
        # AWS WAF
        "aws-waf-token",
        # Generic bot-management
        "bm_", "bot_",
    ]

    @staticmethod
    def _filter_profile_cookies(profile_path: Path) -> None:
        """Remove non-WAF cookies from the warmup browser profile.

        The warmup crawl visits the domain root to obtain WAF validation
        cookies (e.g. Akamai _abck).  But it also picks up session, cart,
        and preference cookies that can pollute the main capture — for
        example, causing "you already have items in your cart" dialogs
        on e-commerce sites.

        We open the Chromium Cookies SQLite database inside the profile
        tar.gz and delete all cookies except known WAF patterns.
        """
        try:
            with TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)

                # Extract profile
                with tarfile.open(profile_path, "r:gz") as tar:
                    tar.extractall(tmpdir_path)

                # Find Cookies database (Chromium stores it at Default/Cookies
                # or sometimes just Cookies at the profile root)
                cookies_db = None
                for candidate in [
                    tmpdir_path / "Default" / "Cookies",
                    tmpdir_path / "Cookies",
                    # Browsertrix might nest under a profile subdir
                    *tmpdir_path.rglob("Cookies"),
                ]:
                    if candidate.is_file():
                        cookies_db = candidate
                        break

                if not cookies_db:
                    logger.debug("No Cookies database found in profile, skipping filter")
                    return

                # Delete session-carrying storage (localStorage, IndexedDB,
                # Cache, Service Workers) — these can hold cart state that
                # cookies alone don't cover.
                for storage_dir in [
                    "Local Storage", "Session Storage", "IndexedDB",
                    "Cache", "Code Cache", "Service Worker",
                    "File System", "GPUCache",
                ]:
                    for match in tmpdir_path.rglob(storage_dir):
                        if match.is_dir():
                            shutil.rmtree(match, ignore_errors=True)
                            logger.info("Cleaned profile storage: %s", match.name)

                # Open SQLite and delete non-WAF cookies
                conn = sqlite3.connect(str(cookies_db))
                try:
                    cursor = conn.cursor()

                    # Log all cookies for debugging
                    cursor.execute("SELECT name FROM cookies ORDER BY name")
                    all_names = [r[0] for r in cursor.fetchall()]
                    logger.info("Profile cookies before filter: %s", all_names)

                    # Build WHERE clause: keep cookies whose name starts with
                    # any of the WAF patterns.  Use ESCAPE to handle literal
                    # underscores (LIKE treats _ as single-char wildcard).
                    keep_conditions = " OR ".join(
                        f"name LIKE '{p.replace('_', '~_')}%' ESCAPE '~'"
                        for p in BrowsertrixService.WAF_COOKIE_PATTERNS
                    )
                    delete_sql = f"DELETE FROM cookies WHERE NOT ({keep_conditions})"

                    total = len(all_names)
                    cursor.execute(delete_sql)
                    deleted = cursor.rowcount

                    # Log kept cookies
                    cursor.execute("SELECT name FROM cookies ORDER BY name")
                    kept_names = [r[0] for r in cursor.fetchall()]
                    logger.info("Profile cookies after filter: %s", kept_names)

                    conn.commit()
                    logger.info(
                        "Profile cookie filter: kept %d/%d cookies (deleted %d non-WAF)",
                        total - deleted, total, deleted,
                    )
                finally:
                    conn.close()

                # Repack profile tar.gz
                with tarfile.open(profile_path, "w:gz") as tar:
                    for item in tmpdir_path.iterdir():
                        tar.add(str(item), arcname=item.name)

        except Exception as e:
            logger.warning("Failed to filter profile cookies (non-fatal): %s", e)

    # URL patterns to strip from the WACZ index during post-processing.
    # These are e-commerce cart/checkout endpoints whose responses, if kept
    # in the WACZ, cause replay JS to show cart popups over the page.
    WACZ_STRIP_URL_PATTERNS = [
        r"Cart-AddProduct",
        r"Cart-Show",
        r"Cart-MiniCart",
        r"cart\?isMiniCart",
        r"/cart/add",
        r"/cart\.js",
        r"/api/cart",
        r"itemAddedToCartPopin",
    ]

    @staticmethod
    def _rebuild_wacz_index(wacz_path: Path) -> None:
        """Clean and rebuild the WACZ CDXJ index.

        Fixes applied:
        1. Remove 403 responses (CDN bot-detection artifacts like Akamai).
        2. Remove cart/checkout responses that cause popups during replay.
        3. Rebuild index.cdx.gz as multi-member gzip with a correct index.idx.
           Browsertrix-crawler sometimes emits a single-member gzip, which
           makes ReplayWeb.page unable to find entries beyond the first block.
        """
        import re as _re

        BLOCK_SIZE = 100  # CDXJ lines per gzip member

        # Compile strip patterns once
        strip_re = _re.compile(
            "|".join(BrowsertrixService.WACZ_STRIP_URL_PATTERNS)
        )

        try:
            with zipfile.ZipFile(wacz_path, "r") as zin:
                cdx_data = gzip.decompress(zin.read("indexes/index.cdx.gz")).decode()

            # --- Step 1: filter out unwanted entries ---
            filtered = []
            removed_403 = 0
            removed_cart = 0
            for line in cdx_data.splitlines():
                if not line.strip():
                    continue
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    try:
                        meta = json.loads(parts[2])
                        if meta.get("status") == "403":
                            removed_403 += 1
                            continue
                        url = meta.get("url", "")
                        if url and strip_re.search(url):
                            removed_cart += 1
                            continue
                    except (json.JSONDecodeError, KeyError):
                        pass
                filtered.append(line)

            if removed_403:
                logger.info("Cleaned WACZ index: removed %d x 403 entries", removed_403)
            if removed_cart:
                logger.info("Cleaned WACZ index: removed %d cart/checkout entries", removed_cart)

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

            # --- Step 3: rebuild the WACZ ZIP with updated hashes ---
            import hashlib

            new_idx_bytes = new_idx.encode()

            # Pre-compute updated datapackage.json with correct hashes
            with zipfile.ZipFile(wacz_path, "r") as zin:
                dp = json.loads(zin.read("datapackage.json"))
            for res in dp.get("resources", []):
                if res["path"] == "indexes/index.cdx.gz":
                    res["hash"] = "sha256:" + hashlib.sha256(new_cdx_gz).hexdigest()
                    res["bytes"] = len(new_cdx_gz)
                elif res["path"] == "indexes/index.idx":
                    res["hash"] = "sha256:" + hashlib.sha256(new_idx_bytes).hexdigest()
                    res["bytes"] = len(new_idx_bytes)
            new_dp = json.dumps(dp, indent=2).encode()
            new_digest = json.dumps({
                "path": "datapackage.json",
                "hash": "sha256:" + hashlib.sha256(new_dp).hexdigest(),
            }).encode()

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
                            zout.writestr(info, new_idx_bytes)
                        elif info.filename == "datapackage.json":
                            zout.writestr(info, new_dp)
                        elif info.filename == "datapackage-digest.json":
                            zout.writestr(info, new_digest)
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
        """Extract the full-page screenshot from the browsertrix WARC output.

        Browsertrix-crawler v1.11+ stores screenshots inside a WARC file
        (screenshots-*.warc.gz) rather than as standalone PNGs on disk.
        We parse the multi-member gzip WARC to find the PNG resource.

        When multiple seeds are crawled (e.g. warm-up + target), the WARC
        contains multiple PNGs.  We return the **last** one, which
        corresponds to the target page (browsertrix processes seeds in order).
        """
        # Try standalone PNGs first (older browsertrix versions)
        # Return the last (most recent) one
        pngs = [f for f in sorted(local_dir.rglob("*.png")) if f.stat().st_size > 10_000]
        if pngs:
            return pngs[-1]

        # Extract from screenshots WARC (v1.11+)
        for warc_file in local_dir.rglob("screenshots-*.warc.gz"):
            try:
                # Decompress all gzip members
                raw_data = warc_file.read_bytes()
                all_data = b""
                stream = io.BytesIO(raw_data)
                while stream.tell() < len(raw_data):
                    try:
                        with gzip.GzipFile(fileobj=stream) as gz:
                            all_data += gz.read()
                    except EOFError:
                        break

                # Find ALL PNG payloads and keep the last one (target page)
                last_png = None
                search_from = 0
                while True:
                    png_start = all_data.find(b"\x89PNG", search_from)
                    if png_start == -1:
                        break
                    iend = all_data.find(b"IEND", png_start)
                    if iend == -1:
                        break
                    png_data = all_data[png_start : iend + 8]
                    if len(png_data) >= 10_000:
                        last_png = png_data
                    search_from = iend + 8

                if last_png:
                    out_path = local_dir / "screenshot.png"
                    out_path.write_bytes(last_png)
                    return out_path
            except Exception as e:
                logger.warning("Failed to extract screenshot from WARC: %s", e)

        return None

    @staticmethod
    def cleanup(crawl_dir: Path, capture_id: uuid.UUID | None = None) -> None:
        try:
            shutil.rmtree(crawl_dir, ignore_errors=True)
        except Exception as e:
            logger.warning("Failed to cleanup browsertrix dir %s: %s", crawl_dir, e)

        # With named volumes, collections are at the volume root
        if capture_id and settings.browsertrix_docker_volume:
            collections_dir = (
                Path(settings.browsertrix_crawl_dir)
                / "collections"
                / f"capture-{capture_id}"
            )
            try:
                shutil.rmtree(collections_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("Failed to cleanup collections dir %s: %s", collections_dir, e)
