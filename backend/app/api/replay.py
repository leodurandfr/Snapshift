from fastapi import APIRouter
from fastapi.responses import RedirectResponse, Response

router = APIRouter(prefix="/replay", tags=["replay"])

REPLAYWEB_CDN = "https://cdn.jsdelivr.net/npm/replaywebpage@2.4.3"

# Script injected into replayed HTML to make WACZ replay robust on any site.
#
# 1. Fix StorageEvent: wombat.js proxies localStorage/sessionStorage, so
#    new StorageEvent('storage', {storageArea: localStorage}) fails — we strip storageArea.
#
# 2. Global error suppression: prevents React/Next.js/Vue error boundaries from
#    turning the page white when wombat.js breaks obfuscated JS. We prefer a partially
#    broken page over a completely blank one.
_REPLAY_PATCH = r"""<script>
(function(){
  /* --- StorageEvent fix --- */
  /* wombat.js proxies localStorage with non-Storage objects, breaking           */
  /* new StorageEvent('storage', {storageArea: localStorage}) in Next.js etc.    */
  var N=window.StorageEvent;
  if(N){
    function P(t,i){
      try{return new N(t,i)}catch(e){
        if(i){var c={};for(var k in i)if(k!=='storageArea')c[k]=i[k];c.storageArea=null;try{return new N(t,c)}catch(e2){}}
        return new Event(t);
      }
    }
    P.prototype=N.prototype;
    Object.defineProperty(window,'StorageEvent',{get:function(){return P},set:function(v){N=v;P.prototype=v.prototype},configurable:true});
  }
  /* --- Global error suppression (prevents white pages from error boundaries) --- */
  window.addEventListener('error',function(e){e.stopImmediatePropagation();e.preventDefault()},true);
  window.addEventListener('unhandledrejection',function(e){e.stopImmediatePropagation();e.preventDefault()},true);
  /* (fetch 404 interception moved to SW level — wombat.js wraps page fetch) */
  /* (IntersectionObserver patch removed — conflicts with wombat.js wrapper) */
  /* --- Force media elements visible --- */
  /* Many sites hide images via CSS (opacity:0/visibility:hidden) until a JS        */
  /* onload callback adds a "loaded" class. In replay, onload may not fire           */
  /* correctly, leaving images invisible. We force all media visible and             */
  /* re-dispatch load events on already-complete images.                             */
  var ss=document.createElement('style');
  ss.textContent='img,picture,video,source{opacity:1!important;visibility:visible!important}';
  (document.head||document.documentElement).appendChild(ss);
  setTimeout(function(){
    document.querySelectorAll('img').forEach(function(img){
      if(img.complete)img.dispatchEvent(new Event('load'));
    });
  },2000);
  /* --- Fix zero-height images: uncollapse flex/hidden ancestors --- */
  /* When site JS fails in replay, images end up at 0px inside flex containers  */
  /* or ancestors with height:0. We detect loaded images with 0 rendered height */
  /* and fix them + their ancestor chain. Runs on each image load + intervals.  */
  function fixImg(img){
    if(img.naturalHeight<1)return;
    if(img.getBoundingClientRect().height>=2)return;
    var p=img.parentElement;
    if(p&&p.tagName==='PICTURE'){
      var cs=window.getComputedStyle(p);
      if(cs.display==='flex'||cs.display==='inline-flex'){
        var hasVideo=p.parentElement&&p.parentElement.querySelector('video');
        if(!hasVideo){
          p.style.setProperty('display','block','important');
        }
      }
    }
  }
  function fixAllImgs(){document.querySelectorAll('img').forEach(fixImg)}
  document.addEventListener('load',function(e){if(e.target&&e.target.tagName==='IMG')fixImg(e.target)},true);
  setTimeout(fixAllImgs,3000);
  setTimeout(fixAllImgs,6000);
  setTimeout(fixAllImgs,10000);
})();
</script>""".strip().replace("\n", "")


@router.get("/sw.js")
async def replay_sw():
    # Custom Service Worker that wraps ReplayWeb.page's SW.
    # We intercept addEventListener to wrap ReplayWeb.page's fetch handler,
    # injecting a StorageEvent fix into HTML responses from the WACZ archive.
    js = f"""
// Patch to inject into replayed HTML <head>
var REPLAY_PATCH = {_REPLAY_PATCH!r};

// Wrap addEventListener to intercept ReplayWeb.page's fetch handler
var _origAEL = self.addEventListener.bind(self);
self.addEventListener = function(type, handler, opts) {{
  if (type === 'fetch') {{
    var origHandler = handler;
    handler = function(event) {{
      var _origRW = event.respondWith.bind(event);
      event.respondWith = function(p) {{
        return _origRW(Promise.resolve(p).then(function(resp) {{
          try {{
            var ct = resp.headers.get('content-type') || '';
            // Inject patch into HTML responses
            if (ct.indexOf('text/html') !== -1) {{
              return resp.text().then(function(text) {{
                var m = text.match(/<head[^>]*>/i);
                if (!m) return new Response(text, {{
                  status: resp.status, headers: resp.headers
                }});
                var i = text.indexOf(m[0]) + m[0].length;
                return new Response(
                  text.slice(0, i) + REPLAY_PATCH + text.slice(i),
                  {{ status: resp.status, headers: resp.headers }}
                );
              }});
            }}
            // Convert 404/5xx API responses to empty 200 JSON
            // In replay, 404 = "not captured", not "doesn't exist".
            // Sites check status/health endpoints and crash when they fail.
            // Skip ReplayWeb.page internal API calls (/w/api/) — converting
            // those breaks collection loading and page lookup.
            if (resp.status >= 400) {{
              var url = event.request.url || '';
              var isRWPApi = /\/w\/api\//.test(url);
              if (!isRWPApi) {{
                var isAsset = /\\.(js|css|png|jpe?g|gif|svg|webp|woff2?|ttf|eot|ico)(\\?|$)/i.test(url);
                if (!isAsset) {{
                  return new Response('{{}}', {{
                    status: 200,
                    headers: {{'content-type': 'application/json'}}
                  }});
                }}
              }}
            }}
            return resp;
          }} catch(e) {{ return resp; }}
        }}));
      }};
      return origHandler(event);
    }};
  }}
  return _origAEL(type, handler, opts);
}};

// Now import ReplayWeb.page's SW (its fetch handler will be wrapped)
importScripts("{REPLAYWEB_CDN}/sw.js");
"""
    return Response(
        content=js,
        media_type="application/javascript",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache",
        },
    )


@router.get("/ui.js")
async def replay_ui():
    return RedirectResponse(f"{REPLAYWEB_CDN}/ui.js", status_code=302)
