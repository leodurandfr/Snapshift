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

  /* --- Wombat Function.prototype.call/apply tolerance --- */
  /* wombat.js wraps Function.prototype.call/apply for URL rewriting.            */
  /* Heavily obfuscated JS (SFCC/LV) chains .call()/.apply() results as         */
  /* property keys or function calls. When wombat alters the return value,       */
  /* the chain breaks with "is not a function". We save the native versions      */
  /* and re-wrap wombat's overrides with a fallback to the originals.            */
  var _nativeApply=Function.prototype.apply;
  var _nativeCall=Function.prototype.call;
  var _R=typeof Reflect!=='undefined'?Reflect:null;
  /* Poll until wombat has overridden call/apply, then wrap with fallback.
     All internal calls use Reflect.apply which does NOT go through
     Function.prototype, avoiding infinite recursion. */
  var _wombatCheckCount=0;
  var _wombatCheck=setInterval(function(){
    _wombatCheckCount++;
    if(_wombatCheckCount>100){clearInterval(_wombatCheck);return}
    if(Function.prototype.apply===_nativeApply)return;
    clearInterval(_wombatCheck);
    var wApply=Function.prototype.apply;
    var wCall=Function.prototype.call;
    if(!_R)return; /* Reflect required for safe wrapping */
    Function.prototype.apply=function(thisArg,args){
      try{return _R.apply(wApply,this,[thisArg,args])}
      catch(e){
        /* Fallback: call the target function directly via Reflect,
           bypassing both wombat and this wrapper entirely. */
        try{return _R.apply(this,thisArg,args||[])}
        catch(e2){return undefined}
      }
    };
    Function.prototype.call=function(thisArg){
      var a=[];for(var i=1;i<arguments.length;i++)a.push(arguments[i]);
      try{return _R.apply(wCall,this,_R.apply(_nativeCall,Array.prototype.slice,[arguments,[0]]))}
      catch(e){
        /* Fallback: invoke target function directly, skip .call wrapper */
        try{return _R.apply(this,thisArg,a)}
        catch(e2){return undefined}
      }
    };
  },10);

  /* --- Force scroll: prevent JS from blocking scroll events --- */
  /* Sites (Shopify, cookie banners, etc.) add non-passive wheel/touchmove  */
  /* listeners that call preventDefault(), killing scroll ~1s after load.   */
  /* We force these listeners passive so preventDefault() becomes a no-op.  */
  var _origAEL2=EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener=function(t,h,o){
    if(/^(wheel|touchmove|touchstart|scroll)$/.test(t)){
      if(typeof o==='object'&&o!==null)o=Object.assign({},o,{passive:true});
      else o={capture:!!o,passive:true};
    }
    return _origAEL2.call(this,t,h,o);
  };

  /* --- Force page visibility (anti-blank-page) --- */
  /* SPAs and SFCC sites hide the page (opacity:0, visibility:hidden, etc.)     */
  /* until JS initialization completes. When JS crashes in replay, the SSR      */
  /* content stays invisible. We force everything visible via CSS overrides      */
  /* and delayed inline-style cleanup.                                          */
  var vs=document.createElement('style');
  vs.textContent=[
    'html,body,#app,#root,#__next,[data-app],main,.app-wrapper,.page-wrapper,',
    '.lv-page,.lv-app,[data-component]:not([role="dialog"]):not([role="alertdialog"]){',
    'opacity:1!important;visibility:visible!important;overflow:visible!important}',
    'img,picture,video,source{opacity:1!important;visibility:visible!important}',
    /* Kill transitions/animations that keep content hidden during "loading" */
    '[class*="loading"],[class*="preload"],[class*="initializing"]{',
    'opacity:1!important;visibility:visible!important;pointer-events:auto!important}',
    /* Hide dialogs/modals/backdrops — these are interactive overlays that */
    /* don't work in archive replay and block the actual page content.     */
    '[role="dialog"],[role="alertdialog"],[aria-modal="true"]{',
    'display:none!important}',
    '[class*="backdrop"]{display:none!important}',
    /* Hide consent/tracking iframes (TCF, CMP, analytics) — invisible 0×0  */
    /* frames that serve no purpose in archive replay.                       */
    'iframe[name*="tcfapi"],iframe[name*="__cmp"],iframe[name*="__usp"],',
    'iframe[name*="googlefcPresent"],iframe[name*="__tcfapi"]{display:none!important}'
  ].join('');
  (document.head||document.documentElement).appendChild(vs);

  /* Delayed forced visibility: remove hiding inline styles + classes */
  function forceVisible(){
    /* Force inline styles on key containers */
    var sels='body,body>*,#app,#root,#__next,main,[data-app],[role="main"],.page-wrapper';
    document.querySelectorAll(sels).forEach(function(el){
      var s=el.style;
      if(s.opacity==='0')s.opacity='1';
      if(s.visibility==='hidden')s.visibility='visible';
      if(s.display==='none'&&el.tagName!=='SCRIPT'&&el.tagName!=='STYLE')s.display='';
    });
    /* Force scroll on html/body (JS may have set overflow:hidden inline) */
    document.documentElement.style.setProperty('overflow','auto','important');
    document.body.style.setProperty('overflow','auto','important');
    /* Remove loading/preload classes from html and body */
    ['loading','is-loading','not-ready','preload','no-js'].forEach(function(c){
      document.documentElement.classList.remove(c);
      document.body.classList.remove(c);
    });
    /* Re-dispatch load events on images */
    document.querySelectorAll('img').forEach(function(img){
      if(img.complete)img.dispatchEvent(new Event('load'));
    });
  }
  setTimeout(forceVisible,1500);
  setTimeout(forceVisible,3000);
  setTimeout(forceVisible,6000);

  /* --- Fix zero-height images: uncollapse flex/hidden ancestors --- */
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
                var isAsset = /\\.(js|css|png|jpe?g|gif|svg|webp|woff2?|ttf|eot|ico|mp4|webm|m4v|m3u8|ts|ogg|aac|mp3|avif)(\\?|$)/i.test(url);
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
