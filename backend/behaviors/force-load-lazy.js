// Custom browsertrix-crawler behavior: force-load all lazy/deferred content
// Replaces the default autoscroll with a more thorough version that:
// 1. Pre-fetches ALL Next.js/Webpack dynamic chunks (fixes missing JS components)
// 2. Scrolls slowly through the entire page (multiple passes)
// 3. Forces all loading="lazy" images to load
// 4. Scrolls each image element into view to trigger IntersectionObserver
// 5. Prefetches srcset/data-src URLs found in the DOM

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

    // --- Pass 1: Slow scroll down to trigger IntersectionObserver lazy loading ---
    var scrollHeight = function() {
      return Math.max(
        document.documentElement.scrollHeight,
        document.body.scrollHeight
      );
    };
    var viewportHeight = window.innerHeight;
    var increment = Math.floor(viewportHeight * 0.25);

    yield { msg: "Starting thorough scroll pass 1..." };

    var pos = 0;
    var lastHeight = scrollHeight();

    while (pos < scrollHeight()) {
      window.scrollTo({ top: pos, behavior: "smooth" });
      await sleep(500);

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

    yield { msg: "Scroll pass 1 complete (" + pos + "px)" };

    // --- Pass 2: Scroll every image/video element into the viewport ---
    // This triggers IntersectionObserver callbacks that lazy-load content
    yield { msg: "Scrolling individual media elements into view..." };

    var mediaElements = document.querySelectorAll(
      "img, video, picture, [data-src], [data-lazy], [class*=lazy], [class*=Lazy]"
    );
    var scrolledCount = 0;

    for (var i = 0; i < mediaElements.length; i++) {
      var el = mediaElements[i];
      try {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        await sleep(150);
        scrolledCount++;
      } catch (e) {
        // ignore
      }
    }

    yield { msg: "Scrolled " + scrolledCount + " media elements into view" };

    // Wait for network requests triggered by IntersectionObserver
    await sleep(3000);

    // --- Pass 3: Force lazy images (loading="lazy" attribute) ---
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

    // --- Pass 5: Reverse scroll ---
    yield { msg: "Starting reverse scroll..." };

    pos = scrollHeight();
    while (pos > 0) {
      window.scrollTo({ top: pos, behavior: "smooth" });
      await sleep(300);
      pos -= increment;
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
    await sleep(1000);

    // --- Pass 6: Final forward scroll ---
    yield { msg: "Final forward scroll..." };

    pos = 0;
    while (pos < scrollHeight()) {
      window.scrollTo({ top: pos, behavior: "smooth" });
      await sleep(200);
      pos += increment;
    }
    window.scrollTo({ top: scrollHeight(), behavior: "smooth" });
    await sleep(2000);

    // Final cleanup: force any remaining lazy images
    var finalLazy = document.querySelectorAll('img[loading="lazy"]');
    for (var y = 0; y < finalLazy.length; y++) {
      finalLazy[y].removeAttribute("loading");
      state.imagesForced++;
    }

    yield {
      msg: "Done! Scrolled " + state.scrolled + "px, forced " + state.imagesForced + " lazy images, fetched " + state.urlsFetched + " URLs, " + state.chunksFetched + " chunks, scrolled " + scrolledCount + " elements",
    };
  }
}
