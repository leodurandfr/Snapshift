// Custom browsertrix-crawler behavior: force-load all lazy/deferred content
// Replaces the default autoscroll with a version that:
// 0. Simulates human interaction (mouse moves, micro-scrolls) to pass WAF behavioral analysis
// 1. Pre-fetches Next.js/Webpack dynamic chunks (fixes missing JS components)
// 2. Scrolls through the entire page (single pass, top to bottom)
// 3. Forces all loading="lazy" images to load
// 4. Prefetches srcset/data-src URLs found in the DOM

class ForceLoadLazy {
  static id = "ForceLoadLazy";

  static isMatch() {
    return true;
  }

  static init() {
    return {
      state: { scrolled: 0, imagesForced: 0, urlsFetched: 0, chunksFetched: 0 },
      opts: {},
    };
  }

  async *run(ctx) {
    const { Lib, state, log } = ctx;
    const sleep = Lib.sleep;

    await log("ForceLoadLazy: starting behavior");

    // --- Step -1: Human interaction simulation ---
    // WAFs like Akamai Bot Manager collect behavioral telemetry (mouse
    // movements, scroll patterns, timing) via their sensor JS.  Dispatching
    // realistic DOM events before any heavy automation makes the session
    // look human.  This runs on every page, including the warm-up page,
    // which is where the _abck cookie gets validated.
    yield { msg: "Simulating human interaction..." };

    try {
      var vw = window.innerWidth;
      var vh = window.innerHeight;

      // Helper: dispatch a mouse event at (x, y)
      function emitMouse(type, x, y) {
        document.dispatchEvent(new MouseEvent(type, {
          clientX: x, clientY: y, bubbles: true, cancelable: true
        }));
      }

      // Simulate a natural mouse path: a few random movements across the viewport
      var steps = 8 + Math.floor(Math.random() * 6); // 8-13 moves
      var cx = Math.floor(vw * 0.3 + Math.random() * vw * 0.4);
      var cy = Math.floor(vh * 0.3 + Math.random() * vh * 0.4);

      for (var mi = 0; mi < steps; mi++) {
        // Move toward a random target with some noise
        cx += Math.floor((Math.random() - 0.5) * vw * 0.15);
        cy += Math.floor((Math.random() - 0.5) * vh * 0.15);
        cx = Math.max(10, Math.min(vw - 10, cx));
        cy = Math.max(10, Math.min(vh - 10, cy));
        emitMouse("mousemove", cx, cy);
        await sleep(80 + Math.floor(Math.random() * 120));
      }

      // Small micro-scroll (human-like hesitation before reading)
      window.scrollTo({ top: 50 + Math.floor(Math.random() * 100), behavior: "smooth" });
      await sleep(300 + Math.floor(Math.random() * 400));
      window.scrollTo({ top: 0, behavior: "smooth" });
      await sleep(200 + Math.floor(Math.random() * 300));

      // A couple of extra mouse moves after scroll
      for (var mj = 0; mj < 3; mj++) {
        emitMouse("mousemove",
          Math.floor(Math.random() * vw),
          Math.floor(Math.random() * vh));
        await sleep(100 + Math.floor(Math.random() * 150));
      }
    } catch (e) {
      await log("Human simulation error (non-fatal): " + e);
    }

    yield { msg: "Human interaction simulation done" };

    // --- Step 0a: Dismiss modals, dialogs, and overlays ---
    // Many sites show popups (cookie consent, cart warnings, newsletter,
    // geolocation) that overlay the real content. If these stay open, the
    // WACZ archive captures the dialog state instead of the actual page.
    // We try multiple strategies to close them.
    yield { msg: "Dismissing popups/modals..." };

    try {
      var dismissed = 0;

      // Strategy 1: Close native <dialog> elements
      var dialogs = document.querySelectorAll("dialog[open]");
      for (var di = 0; di < dialogs.length; di++) {
        try {
          dialogs[di].close();
          dismissed++;
        } catch (e) { /* ignore */ }
      }

      // Strategy 2: Click common close/dismiss buttons
      // Order matters: try specific refusal buttons first ("Non", "Decline",
      // "Reject"), then generic close buttons.
      var dismissSelectors = [
        // Specific refusal/dismiss buttons (e.g. Balenciaga cart warning "Non")
        'dialog button', 'dialog a',
        '[role="dialog"] button', '[role="dialog"] a',
        '[role="alertdialog"] button',
        // Cookie/consent dismiss
        'button[id*="reject"]', 'button[id*="decline"]', 'button[id*="refuse"]',
        'a[id*="reject"]', 'a[id*="decline"]',
        'button[class*="reject"]', 'button[class*="decline"]', 'button[class*="refuse"]',
        // Generic close buttons
        'button[aria-label="Close"]', 'button[aria-label="Fermer"]',
        'button[aria-label="close"]', 'button[aria-label="fermer"]',
        '[class*="close-modal"]', '[class*="modal-close"]', '[class*="dialog-close"]',
        '[class*="popup-close"]', '[class*="overlay-close"]',
        'button[class*="dismiss"]', 'button[class*="close"]',
      ];

      // Helper: check if element is visible and clickable
      function isVisible(el) {
        if (!el) return false;
        var rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return false;
        var style = window.getComputedStyle(el);
        return style.display !== "none" && style.visibility !== "hidden" && parseFloat(style.opacity) > 0;
      }

      // Helper: check if a button looks like a refusal/close (not "accept" or "continue")
      function isRefusalOrClose(el) {
        var text = (el.textContent || "").trim().toLowerCase();
        var label = (el.getAttribute("aria-label") || "").toLowerCase();
        var combined = text + " " + label;
        // Skip buttons that accept/continue (we want to dismiss, not accept)
        if (/^(oui|yes|accepter|accept|continuer|continue|proceed|ok)$/i.test(text)) return false;
        // Match close/dismiss/refuse patterns
        if (/non|no|fermer|close|dismiss|refuser|reject|decline|annuler|cancel|×|✕|✖/i.test(combined)) return true;
        // Also match if it's inside a dialog and is a secondary/cancel-looking button
        return false;
      }

      for (var dsi = 0; dsi < dismissSelectors.length; dsi++) {
        var btns = document.querySelectorAll(dismissSelectors[dsi]);
        for (var dbi = 0; dbi < btns.length; dbi++) {
          var btn = btns[dbi];
          if (isVisible(btn) && isRefusalOrClose(btn)) {
            try {
              btn.click();
              dismissed++;
              await sleep(300);
            } catch (e) { /* ignore */ }
          }
        }
        if (dismissed > 0) break; // Stop after first successful dismissal
      }

      // Strategy 3: Remove modal overlays from the DOM if still present
      // (last resort — some modals have no close button)
      await sleep(500);
      var overlaySelectors = [
        'dialog[open]',
        '[role="dialog"]',
        '[role="alertdialog"]',
        '[class*="modal"][class*="overlay"]',
        '[class*="modal-backdrop"]',
      ];
      for (var oi = 0; oi < overlaySelectors.length; oi++) {
        var overlays = document.querySelectorAll(overlaySelectors[oi]);
        for (var oj = 0; oj < overlays.length; oj++) {
          if (isVisible(overlays[oj])) {
            try {
              overlays[oj].remove();
              dismissed++;
            } catch (e) { /* ignore */ }
          }
        }
      }

      // Strategy 4: Remove body overflow:hidden (modals often lock scroll)
      if (document.body.style.overflow === "hidden") {
        document.body.style.overflow = "";
      }
      if (document.documentElement.style.overflow === "hidden") {
        document.documentElement.style.overflow = "";
      }

      if (dismissed > 0) {
        await sleep(500);
      }

      yield { msg: "Dismissed " + dismissed + " popups/modals" };
    } catch (e) {
      await log("Modal dismissal error (non-fatal): " + e);
    }

    // --- Step 0: Pre-fetch ALL dynamic JS/CSS chunks ---
    // Next.js/Webpack apps only load chunks on demand. We fetch them all
    // so they're in the WACZ and available during replay.
    yield { msg: "Pre-fetching dynamic chunks..." };

    var chunkUrls = [];

    // Method 1: Parse webpack chunk map from script tags
    // Next.js embeds chunk mappings in the webpack runtime
    var scripts = document.querySelectorAll('script[src*="/_next/"], script[src*="/static/chunks/"]');
    var nextBase = "";

    for (var si = 0; si < scripts.length; si++) {
      var scriptSrc = scripts[si].getAttribute("src") || "";
      // Extract the Next.js base path (e.g., /_next/static/BUILD_ID/)
      var baseMatch = scriptSrc.match(/(.*\/_next\/static\/[^/]+\/)/);
      if (baseMatch) {
        nextBase = baseMatch[1];
        break;
      }
    }

    // Method 2: Access webpack's chunk loading infrastructure
    // The webpack runtime stores chunk IDs and their hashes
    try {
      // Look for the webpack chunk map in all inline scripts and loaded scripts
      var allScriptEls = document.querySelectorAll("script");
      for (var sj = 0; sj < allScriptEls.length; sj++) {
        var scriptText = allScriptEls[sj].textContent || "";
        // Next.js build manifest: self.__BUILD_MANIFEST
        // Contains all page chunks
        if (scriptText.indexOf("__BUILD_MANIFEST") !== -1) {
          // Extract chunk filenames from the manifest
          var chunkMatches = scriptText.match(/static\/chunks\/[^"'\s,)]+\.js/g);
          if (chunkMatches) {
            for (var cm = 0; cm < chunkMatches.length; cm++) {
              chunkUrls.push("/_next/" + chunkMatches[cm]);
            }
          }
          var cssMatches = scriptText.match(/static\/css\/[^"'\s,)]+\.css/g);
          if (cssMatches) {
            for (var ccm = 0; ccm < cssMatches.length; ccm++) {
              chunkUrls.push("/_next/" + cssMatches[ccm]);
            }
          }
        }
      }
    } catch (e) {
      await log("Error parsing inline scripts: " + e);
    }

    // Method 3: Find the webpack runtime and extract ALL chunk IDs
    // The webpack runtime contains a map like {chunkId: "hash", ...}
    try {
      // Look for loaded script content that has the chunk map
      for (var sk = 0; sk < scripts.length; sk++) {
        var src = scripts[sk].getAttribute("src") || "";
        if (src.indexOf("webpack") !== -1 || src.indexOf("_app") !== -1) {
          try {
            var resp = await fetch(src);
            var text = await resp.text();
            // Find chunk hash map: patterns like 65206:"6afacfa7f295225d"
            var hashMap = {};
            var regex = /(\d+):"([a-f0-9]{16,})"/g;
            var match;
            while ((match = regex.exec(text)) !== null) {
              hashMap[match[1]] = match[2];
            }
            var hashCount = Object.keys(hashMap).length;
            if (hashCount > 0) {
              await log("Found webpack chunk map with " + hashCount + " chunks");
              // Build chunk URLs
              for (var chunkId in hashMap) {
                var hash = hashMap[chunkId];
                var chunkUrl = "/_next/static/chunks/" + chunkId + "." + hash + ".js";
                chunkUrls.push(chunkUrl);
              }
            }
          } catch (e) {
            // ignore fetch errors
          }
        }
      }
    } catch (e) {
      await log("Error extracting chunk map: " + e);
    }

    // Deduplicate chunk URLs
    var seenChunks = {};
    var uniqueChunks = [];
    for (var uc = 0; uc < chunkUrls.length; uc++) {
      if (!seenChunks[chunkUrls[uc]]) {
        seenChunks[chunkUrls[uc]] = true;
        uniqueChunks.push(chunkUrls[uc]);
      }
    }

    if (uniqueChunks.length > 0) {
      yield { msg: "Fetching " + uniqueChunks.length + " JS/CSS chunks..." };

      // Fetch chunks in batches
      for (var cb = 0; cb < uniqueChunks.length; cb += 10) {
        var batch = uniqueChunks.slice(cb, cb + 10);
        var promises = [];
        for (var ci = 0; ci < batch.length; ci++) {
          promises.push(fetch(batch[ci]).catch(function() {}));
        }
        await Promise.allSettled(promises);
        state.chunksFetched += batch.length;
      }

      yield { msg: "Fetched " + uniqueChunks.length + " chunks" };
    } else {
      yield { msg: "No dynamic chunks found (not a Next.js/Webpack site)" };
    }

    // --- Step 0b: Pre-fetch all image/resource URLs from __NEXT_DATA__ ---
    // Next.js SSR includes all page data (including image URLs for all product
    // variants, carousel items, etc.) in a JSON blob. These images are only
    // loaded client-side when the user interacts (e.g., clicks a color variant).
    // We extract and fetch them all to ensure they're in the WACZ.
    try {
      var nextDataEl = document.getElementById("__NEXT_DATA__");
      if (nextDataEl) {
        var nextDataText = nextDataEl.textContent || "";
        // Extract all image/video URLs from the JSON
        var urlRegex = /https?:\/\/[^"\\]+\.(?:png|jpg|jpeg|webp|gif|svg|mp4)(?:[^"\\]*)/g;
        var ndMatch;
        var nextDataUrls = [];
        var ndSeen = {};
        while ((ndMatch = urlRegex.exec(nextDataText)) !== null) {
          var ndUrl = ndMatch[0];
          if (!ndSeen[ndUrl]) {
            ndSeen[ndUrl] = true;
            nextDataUrls.push(ndUrl);
          }
        }
        if (nextDataUrls.length > 0) {
          yield { msg: "Fetching " + nextDataUrls.length + " URLs from __NEXT_DATA__..." };
          for (var ndi = 0; ndi < nextDataUrls.length; ndi += 10) {
            var ndBatch = nextDataUrls.slice(ndi, ndi + 10);
            var ndPromises = [];
            for (var ndj = 0; ndj < ndBatch.length; ndj++) {
              ndPromises.push(fetch(ndBatch[ndj], { mode: "no-cors" }).catch(function() {}));
            }
            await Promise.allSettled(ndPromises);
            state.urlsFetched += ndBatch.length;
          }
          yield { msg: "Fetched " + nextDataUrls.length + " __NEXT_DATA__ URLs" };
        }
      }
    } catch (e) {
      await log("Error parsing __NEXT_DATA__: " + e);
    }

    // Also fetch any URLs from other JSON-LD / inline script data
    try {
      var inlineScripts = document.querySelectorAll('script[type="application/json"], script[type="application/ld+json"]');
      var inlineUrls = [];
      var inlineSeen = {};
      for (var isi = 0; isi < inlineScripts.length; isi++) {
        var isText = inlineScripts[isi].textContent || "";
        var isMatch;
        var isRegex = /https?:\/\/[^"\\]+\.(?:png|jpg|jpeg|webp|gif|svg|mp4)(?:[^"\\]*)/g;
        while ((isMatch = isRegex.exec(isText)) !== null) {
          if (!inlineSeen[isMatch[0]]) {
            inlineSeen[isMatch[0]] = true;
            inlineUrls.push(isMatch[0]);
          }
        }
      }
      if (inlineUrls.length > 0) {
        yield { msg: "Fetching " + inlineUrls.length + " URLs from inline JSON..." };
        for (var ili = 0; ili < inlineUrls.length; ili += 10) {
          var ilBatch = inlineUrls.slice(ili, ili + 10);
          var ilPromises = [];
          for (var ilj = 0; ilj < ilBatch.length; ilj++) {
            ilPromises.push(fetch(ilBatch[ilj], { mode: "no-cors" }).catch(function() {}));
          }
          await Promise.allSettled(ilPromises);
          state.urlsFetched += ilBatch.length;
        }
      }
    } catch (e) {
      // ignore
    }

    // --- Scroll down to trigger IntersectionObserver lazy loading ---
    var scrollHeight = function() {
      return Math.max(
        document.documentElement.scrollHeight,
        document.body.scrollHeight
      );
    };
    var viewportHeight = window.innerHeight;
    var increment = Math.floor(viewportHeight * 0.5);

    yield { msg: "Scrolling page top to bottom..." };

    var pos = 0;
    var lastHeight = scrollHeight();

    while (pos < scrollHeight()) {
      window.scrollTo({ top: pos, behavior: "smooth" });
      await sleep(300);

      var newHeight = scrollHeight();
      if (newHeight > lastHeight) {
        yield { msg: "Page grew from " + lastHeight + " to " + newHeight + "px" };
        lastHeight = newHeight;
      }

      pos += increment;
      state.scrolled = pos;
    }

    window.scrollTo({ top: scrollHeight(), behavior: "smooth" });
    await sleep(1500);

    yield { msg: "Scroll complete (" + pos + "px)" };

    // --- Force lazy images (loading="lazy" attribute) ---
    var lazyImages = document.querySelectorAll('img[loading="lazy"]');
    for (var j = 0; j < lazyImages.length; j++) {
      var img = lazyImages[j];
      img.removeAttribute("loading");
      var imgSrc2 = img.getAttribute("src");
      if (imgSrc2) {
        img.setAttribute("src", "");
        await sleep(10);
        img.setAttribute("src", imgSrc2);
      }
      state.imagesForced++;
    }

    if (lazyImages.length > 0) {
      yield { msg: "Forced " + lazyImages.length + " loading=lazy images" };
    }

    // --- Pass 4: Activate data-src / data-lazy-src / data-srcset attributes ---
    var dataAttrs = [
      "data-src", "data-lazy-src", "data-original", "data-bg",
      "data-srcset", "data-lazy-srcset", "data-background-image"
    ];
    var urlsToFetch = [];

    for (var k = 0; k < dataAttrs.length; k++) {
      var attr = dataAttrs[k];
      var els = document.querySelectorAll("[" + attr + "]");
      for (var m = 0; m < els.length; m++) {
        var elem = els[m];
        var val = elem.getAttribute(attr);
        if (!val) continue;

        if (attr.indexOf("srcset") !== -1) {
          var entries = val.split(",");
          for (var n = 0; n < entries.length; n++) {
            var url = entries[n].trim().split(/\s+/)[0];
            if (url) urlsToFetch.push(url);
          }
          if (elem.tagName === "IMG" || elem.tagName === "SOURCE") {
            elem.setAttribute("srcset", val);
          }
        } else {
          urlsToFetch.push(val);
          if (elem.tagName === "IMG") {
            elem.setAttribute("src", val);
          }
        }
      }
    }

    // Collect all srcset URLs
    var srcsetEls = document.querySelectorAll("[srcset]");
    for (var p = 0; p < srcsetEls.length; p++) {
      var srcset = srcsetEls[p].getAttribute("srcset");
      if (srcset) {
        var parts = srcset.split(",");
        for (var q = 0; q < parts.length; q++) {
          var u = parts[q].trim().split(/\s+/)[0];
          if (u) urlsToFetch.push(u);
        }
      }
    }

    // Collect all image src URLs (ensure they are captured)
    var allImgs = document.querySelectorAll("img[src]");
    for (var r = 0; r < allImgs.length; r++) {
      var imgSrc = allImgs[r].getAttribute("src");
      if (imgSrc) urlsToFetch.push(imgSrc);
    }

    // Collect background-image URLs from computed styles
    var allElements = document.querySelectorAll("*");
    for (var s = 0; s < allElements.length && s < 2000; s++) {
      try {
        var bgImg = window.getComputedStyle(allElements[s]).backgroundImage;
        if (bgImg && bgImg !== "none") {
          var bgMatches = bgImg.match(/url\(["']?(.*?)["']?\)/g);
          if (bgMatches) {
            for (var t = 0; t < bgMatches.length; t++) {
              var bgUrl = bgMatches[t].replace(/url\(["']?/, "").replace(/["']?\)/, "");
              if (bgUrl && bgUrl !== "none") urlsToFetch.push(bgUrl);
            }
          }
        }
      } catch (e) {
        // ignore CORS errors on computed styles
      }
    }

    // Deduplicate
    var uniqueUrls = {};
    var fetchList = [];
    for (var v = 0; v < urlsToFetch.length; v++) {
      var fetchUrl = urlsToFetch[v];
      if (fetchUrl && !uniqueUrls[fetchUrl] && (fetchUrl.indexOf("http") === 0 || fetchUrl.indexOf("/") === 0)) {
        uniqueUrls[fetchUrl] = true;
        fetchList.push(fetchUrl);
      }
    }

    yield { msg: "Fetching " + fetchList.length + " resource URLs..." };

    // Fetch in batches of 10
    for (var w = 0; w < fetchList.length; w += 10) {
      var resBatch = fetchList.slice(w, w + 10);
      var resPromises = [];
      for (var x = 0; x < resBatch.length; x++) {
        resPromises.push(fetch(resBatch[x], { mode: "no-cors" }).catch(function() {}));
      }
      await Promise.allSettled(resPromises);
      state.urlsFetched += resBatch.length;
    }

    yield { msg: "Fetched " + fetchList.length + " resource URLs" };

    yield {
      msg: "Done! Scrolled " + state.scrolled + "px, forced " + state.imagesForced + " lazy images, fetched " + state.urlsFetched + " URLs, " + state.chunksFetched + " chunks",
    };
  }
}
