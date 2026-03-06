from fastapi import APIRouter
from fastapi.responses import RedirectResponse, Response

router = APIRouter(prefix="/replay", tags=["replay"])

REPLAYWEB_CDN = "https://cdn.jsdelivr.net/npm/replaywebpage@2.4.3"

# Script injected into replayed HTML to make WACZ replay robust on any site.
# 1. Fix StorageEvent: wombat.js proxies localStorage/sessionStorage, so
#    new StorageEvent('storage', {storageArea: localStorage}) fails — we strip storageArea.
# 2. Global error suppression: prevents React/Next.js/Vue error boundaries from
#    turning the page white when wombat.js breaks obfuscated JS. We prefer a partially
#    broken page over a completely blank one.
_REPLAY_PATCH = r"""<script>
(function(){
  /* --- StorageEvent fix --- */
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
})();
</script>""".strip().replace("\n", "")


@router.get("/sw.js")
async def replay_sw():
    # Custom Service Worker that wraps ReplayWeb.page's SW.
    # We intercept addEventListener to wrap ReplayWeb.page's fetch handler,
    # injecting a StorageEvent fix into HTML responses from the WACZ archive.
    js = f"""
// StorageEvent patch to inject into replayed HTML <head>
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
            if (ct.indexOf('text/html') === -1) return resp;
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
