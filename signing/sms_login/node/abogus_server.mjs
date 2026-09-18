// signer_server.mjs — Node 侧「逆向参数」生成服务（常驻，JSON-Lines over stdio）。
//
// 职责（只生成参数，绝不发包）：
//   1. dtrait  —— nv8 运行 uc-secure-dtrait-core，现场采集设备指纹 payload。
//   2. abogus  —— nv8 运行 **bdms**（a_bogus 的真正生成者），由它把 a_bogus 追加到 URL 上。
//
// 为什么 a_bogus 要用 bdms：
//   - 用 CDP/早注入 hook 抓到真正写入点是 bdms 的 URLSearchParams.append
//     （bdms_1.0.1.19_fix.js），不是 webmssdk（那只给 X-Bogus）、也不是 secsdk
//     （那只给 x-secsdk-web-signature）。公开移植版（ylcangel/a_bogus）与之不一致。
//   - bdms 的算法是**编译后的字节码 + VM**，所以静态源码里搜不到 "a_bogus"。
//
// 为什么之前 bdms 在 nv8 里会挂死：
//   bdms 初始化使用**同步 XHR**（open(..., false)）。若把它替换成异步桩，
//   初始化会永远等不到响应。这里提供一个「同步也能立刻返回」的 XHR 桩。
//
// 边界：本进程不做任何网络 I/O；最终 HTTP 出口由 Python 独占。

import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { pathToFileURL } from 'node:url';

const HERE = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const ROOT = path.resolve(HERE, '..');
const NV8_SRC = process.env.NV8_SRC || 'D:/develop_software/nv8/src/index.js';

const dtraitCore = fs.readFileSync(path.join(ROOT, 'assets/dtrait_core.js'), 'utf8');
const bdmsSrc = fs.readFileSync(path.join(ROOT, 'js_reverse_cache/source/bdms.js'), 'utf8');
const webmssdkSrc = fs.readFileSync(path.join(ROOT, 'assets/webmssdk.es5.1.0.0.20.js'), 'utf8');
const sdkGlueSrc = fs.readFileSync(path.join(ROOT, 'js_reverse_cache/source/sdk-glue.js'), 'utf8');
const secsdkSrc = fs.readFileSync(path.join(ROOT, 'js_reverse_cache/source/secsdk-runtime34.js'), 'utf8');
// bdms 逐字段读取的环境画像（由 recon/capture_env_profile.py 从真实页面导出）
const ENV_PROFILE_PATH = path.join(ROOT, 'js_reverse_cache/private/bdms_env_profile.json');
const STORAGE_PATH = path.join(ROOT, 'js_reverse_cache/private/bdms_storage.json');
let ENV_PROFILE = null;
let ENV_STORAGE = null;
try {
  if (fs.existsSync(ENV_PROFILE_PATH)) {
    ENV_PROFILE = JSON.parse(fs.readFileSync(ENV_PROFILE_PATH, 'utf8'));
    process.stderr.write('[abogus] loaded env profile\n');
  }
  if (fs.existsSync(STORAGE_PATH)) {
    ENV_STORAGE = JSON.parse(fs.readFileSync(STORAGE_PATH, 'utf8'));
    process.stderr.write('[abogus] loaded storage seed\n');
  }
} catch (e) { process.stderr.write('[abogus] env/storage load failed: ' + e.message + '\n'); }
const rsa = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets/dtrait_rsa.json'), 'utf8'));

const { EdgeSandbox } = await import(pathToFileURL(NV8_SRC).href);

// --------------------------------------------------------------- dtrait
const DTRAIT_PARAMS = {
  urlVersion: rsa.urlVersion || '1.0.0.16',
  centralRsaPub: rsa.centralRsaPub_pem,
  centralVersion: rsa.centralVersion || 'd0',
  edgeRsaPub: rsa.edgeRsaPub_pem,
  edgeVersion: 'd0',
  dTraitVersion: '0',
};
const DTRAIT_OPTS = {
  dTraitPath: ['/passport/web/sms_login/'],
  dTraitHost: ['login.douyin.com'],
  urlRewriteRules: [],
  containerSdkVersion: '1.1.11',
  libraGroup: '',
  delayCollect: 0,
  monitor: {},
};
const TARGET_URL = 'https://login.douyin.com/passport/web/sms_login/';

let dtraitSandbox = null;

async function getDtraitSandbox() {
  if (dtraitSandbox) return dtraitSandbox;
  const sb = await EdgeSandbox.create({
    page: { url: 'https://www.douyin.com/', html: '<!doctype html><html><body></body></html>' },
    limits: { timeoutMs: 120000 },
  });
  await sb.evaluate(`(function(){
    window.__payloads = [];
    function j(a){ if (a === null || a === undefined) return ''; if (typeof a === 'string') return a;
      try { return JSON.stringify(a); } catch (e) { return ''; } }
    console.log = function(){
      try {
        var txt = Array.prototype.map.call(arguments, j).join(' ');
        var k = txt.indexOf('[params]'); if (k < 0) return;
        var b = txt.indexOf('{', k); if (b < 0) return;
        var o = JSON.parse(txt.slice(b));
        if (o && (o.str || o.bool || o.num)) window.__payloads.push(o);
      } catch (e) { window.__payloadErr = String((e && e.message) || e); }
    };
    window.fetch = function(){ return Promise.resolve({ ok:true, status:200,
      text:function(){ return Promise.resolve('{}'); }, json:function(){ return Promise.resolve({}); } }); };
    return 'ok';
  })()`);
  dtraitSandbox = sb;
  return sb;
}

async function collectDtrait() {
  const sb = await getDtraitSandbox();
  await sb.evaluate('window.__payloads = []; "ok"');
  await sb.evaluate(dtraitCore);
  const raw = await sb.evaluate(`(async function(){
    var out = { n: 0, payload: null, err: null };
    try {
      var cls = window.DTraitSDK && (window.DTraitSDK.default || window.DTraitSDK);
      if (!cls) return JSON.stringify({ n:0, payload:null, err:'DTraitSDK missing' });
      await cls.getInstance(${JSON.stringify(DTRAIT_PARAMS)}, ${JSON.stringify(DTRAIT_OPTS)});
      for (var i = 0; i < 50 && !window.__payloads.length; i++) {
        await new Promise(function(r){ setTimeout(r, 100); });
      }
    } catch (e) { out.err = String((e && e.stack) || e); }
    out.n = window.__payloads.length;
    out.payload = window.__payloads[window.__payloads.length - 1] || null;
    return JSON.stringify(out);
  })()`);
  const text = (raw && raw.value !== undefined) ? raw.value : raw;
  const out = (typeof text === 'string') ? JSON.parse(text) : text;
  if (!out || !out.payload) throw new Error('dtrait collect failed :: ' + JSON.stringify(out).slice(0, 500));
  return out.payload;
}

// --------------------------------------------------------------- a_bogus (bdms)
// 同步可返回的 XHR 桩：bdms 初始化用的是同步 XHR，异步桩会让它无限等待。
const BDMS_STUBS = `
(function(){
  window.__cap = [];
  function fire(x, name){
    try { if (typeof x[name] === 'function') x[name](); } catch(e){}
    try { (x.__ls[name] || []).forEach(function(f){ try { f.call(x, { type: name.slice(2) }); } catch(e){} }); } catch(e){}
  }
  function reply(x){
    try {
      Object.defineProperty(x,'readyState',{value:4,configurable:true});
      Object.defineProperty(x,'status',{value:200,configurable:true});
      Object.defineProperty(x,'statusText',{value:'OK',configurable:true});
      Object.defineProperty(x,'responseText',{value:'{}',configurable:true});
      Object.defineProperty(x,'response',{value:'{}',configurable:true});
      Object.defineProperty(x,'responseURL',{value:x._u||'',configurable:true});
    } catch(e){}
    ['onreadystatechange','onloadstart','onprogress','onload','onloadend'].forEach(function(k){ fire(x, k); });
  }
  function X(){
    this.readyState=0; this.status=0; this.statusText=''; this.responseText=''; this.response='';
    this.responseType=''; this.responseXML=null; this.timeout=0; this.withCredentials=false;
    this.upload={ addEventListener:function(){}, removeEventListener:function(){} };
    this._h={}; this._ls={};
  }
  X.prototype.open=function(m,u,a){ this._m=m; this._u=String(u); this._a=(a===undefined)?true:!!a; this.readyState=1;
    window.__cap.push({m:m,url:this._u}); };
  X.prototype.setRequestHeader=function(k,v){ this._h[k]=v; };
  X.prototype.getAllResponseHeaders=function(){ return 'content-type: application/json\\r\\n'; };
  X.prototype.getResponseHeader=function(){ return 'application/json'; };
  X.prototype.overrideMimeType=function(){};
  X.prototype.abort=function(){ try{ this.readyState=0; fire(this,'onabort'); }catch(e){} };
  X.prototype.addEventListener=function(t,fn){ (this._ls['on'+t]=this._ls['on'+t]||[]).push(fn); };
  X.prototype.removeEventListener=function(t,fn){ try{ var a=this._ls['on'+t]||[]; var i=a.indexOf(fn); if(i>=0) a.splice(i,1); }catch(e){} };
  X.prototype.dispatchEvent=function(){ return true; };
  X.prototype.send=function(){ reply(this); return true; };
  try { Object.defineProperty(X, 'name', { value: 'XMLHttpRequest', configurable: true }); } catch(e){}
  window.XMLHttpRequest=X;
  var fetchStub=function(){ return Promise.resolve({ ok:true, status:200, statusText:'OK',
    headers:{ get:function(){ return 'application/json'; }, forEach:function(){} },
    text:function(){ return Promise.resolve('{}'); },
    json:function(){ return Promise.resolve({}); },
    arrayBuffer:function(){ return Promise.resolve(new ArrayBuffer(0)); },
    clone:function(){ return this; } }); };
  try { Object.defineProperty(fetchStub, 'name', { value: 'fetch', configurable: true }); } catch(e){}
  window.fetch=fetchStub;

  // bdms 会做环境完整性检测：字符串表里有 HeadlessChrome / webdriver /
  // (Module._compile|Object.Module|...) / "[native code]" —— 它会拿 Function.prototype.toString
  // 看我们的桩函数是不是原生。自己写的函数会返回源码，因此这里给它们伪装成原生。
  window.__stubFns = [X, fetchStub];
  try {
    var _fpts = Function.prototype.toString;
    Function.prototype.toString = function(){
      try {
        if (window.__stubFns && window.__stubFns.indexOf(this) >= 0) {
          return 'function ' + (this.name || '') + '() { [native code] }';
        }
      } catch(e){}
      return _fpts.call(this);
    };
    try { Object.defineProperty(Function.prototype.toString, 'name', { value: 'toString', configurable: true }); } catch(e){}
  } catch(e){}
  return 'bdms-stubs';
})()`;

/** 页面真实配置：_SdkGlueInit({self:{aid,pageId}, bdms:{aid,pageId,paths,boe,ddrt,ic}}) */
const BDMS_AID = 6383;
const BDMS_PAGE_ID = 6241;                      // 从页面 _SdkGlueInit 实抓
const BDMS_PATHS = ["^/webcast/", "^/aweme/v1/", "^/aweme/v2/", "/douplus/", "^/api/ad/v1/inspire", "/v1/message/send", "^/live/", "^/captcha/", "^/ecom/", "^/luna/pc", "/passport/web/sms_login/", "/passport/web/sms_login/", "/passport/web/get_qrcode/"];
const BDMS_EXTRA = { boe: false, ddrt: 8.5, ic: 8.5 };

/** 与我们实际发出的请求一致的环境（a_bogus 会把环境编码进去）。 */
const DEFAULT_ENV = {
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    + '(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36',
  platform: 'Win32',
  screen: { width: 1920, height: 1080, availWidth: 1920, availHeight: 1032 },
  window: { innerWidth: 1264, innerHeight: 971, outerWidth: 160, outerHeight: 28 },
};

/**
 * 在 bdms 加载前，把它会读取的环境字段**逐字段**对齐到真实页面画像。
 * 字段清单来自 recon/capture_bdms_inputs.py 的实测（bdms 实际读了哪些）。
 */
function envScript(profile) {
  return `(function(){
    var P = ${JSON.stringify(profile || {})};
    function def(o, k, v) {
      try { Object.defineProperty(o, k, { value: v, writable: true, configurable: true }); }
      catch (e) { try { o[k] = v; } catch (e2) {} }
    }
    var applied = {};
    if (P.navigator) {
      var n = P.navigator;
      ['userAgent','appVersion','appName','appCodeName','platform','product','productSub',
       'vendor','vendorSub','language','hardwareConcurrency','deviceMemory','maxTouchPoints',
       'webdriver','onLine','cookieEnabled','doNotTrack','pdfViewerEnabled'].forEach(function(k){
        if (n[k] !== undefined && n[k] !== null) { def(navigator, k, n[k]); applied['nav.'+k] = 1; }
      });
      if (n.languages) def(navigator, 'languages', n.languages);
      // plugins / mimeTypes：bdms 会读 length 与逐项 name/type
      if (n.plugins) {
        // 必须是「类数组普通对象」而不是真 Array，否则 String(pl) 会走 Array.prototype.toString
        // 输出元素列表，而浏览器是 "[object PluginArray]"（bdms 会把它读走）。
        var pl = { length: n.plugins.length };
        for (var pi = 0; pi < n.plugins.length; pi++) {
          pl[pi] = { name: n.plugins[pi], filename: 'internal-pdf-viewer',
                     description: 'Portable Document Format', length: 1,
                     0: { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' } };
        }
        pl.item = function (i) { return pl[i]; };
        pl.namedItem = function (nm) { for (var i=0;i<pl.length;i++) if (pl[i] && pl[i].name===nm) return pl[i]; return null; };
        try { Object.defineProperty(pl, Symbol.toStringTag, { value: 'PluginArray', configurable: true }); } catch (e) {}
        def(navigator, 'plugins', pl);
      }
      if (n.mimeTypes) {
        var mt = { length: n.mimeTypes.length };
        for (var mi = 0; mi < n.mimeTypes.length; mi++) {
          mt[mi] = { type: n.mimeTypes[mi], suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: null };
        }
        mt.item = function (i) { return mt[i]; };
        mt.namedItem = function (t) { for (var i=0;i<mt.length;i++) if (mt[i] && mt[i].type===t) return mt[i]; return null; };
        try { Object.defineProperty(mt, Symbol.toStringTag, { value: 'MimeTypeArray', configurable: true }); } catch (e) {}
        def(navigator, 'mimeTypes', mt);
      }
      if (n.uaBrands) {
        var uad = {
          brands: n.uaBrands, mobile: !!n.uaMobile, platform: n.uaPlatform || 'Windows',
          toJSON: function () { return { brands: n.uaBrands, mobile: !!n.uaMobile, platform: n.uaPlatform || 'Windows' }; },
          getHighEntropyValues: function () { return Promise.resolve({ brands: n.uaBrands, mobile: !!n.uaMobile, platform: n.uaPlatform || 'Windows' }); }
        };
        try { def(uad, Symbol.toStringTag, 'NavigatorUAData'); } catch (e) {}
        def(navigator, 'userAgentData', uad);
      }
      if (n.connection) {
        var conn = n.connection;
        try { def(conn, Symbol.toStringTag, 'NetworkInformation'); } catch (e) {}
        def(navigator, 'connection', conn);
      }
    }
    if (P.screen) {
      Object.keys(P.screen).forEach(function (k) {
        if (k === 'orientation') {
          def(screen, 'orientation', { type: P.screen.orientation || 'landscape-primary', angle: 0 });
          return;
        }
        def(screen, k, P.screen[k]); applied['screen.'+k] = 1;
      });
    }
    if (P.window) Object.keys(P.window).forEach(function (k) { def(window, k, P.window[k]); applied['win.'+k] = 1; });
    if (P.document) {
      if (P.document.referrer !== undefined) def(document, 'referrer', P.document.referrer);
      if (P.document.visibilityState !== undefined) {
        def(document, 'visibilityState', P.document.visibilityState);
        def(document, 'hidden', !!P.document.hidden);
      }
    }
    window.__envApplied = applied;
    // ==== VM 探针（recon/vm_probe.mjs）发现的真实差异 ====
    // bdms 会直接读 screen.sizeWidth / screen.sizeHeight；nv8 的 screen 是代理对象，
    // delete/defineProperty 都不生效（仍返回 1280/720），而真实 Chrome 这两个属性不存在（undefined）。
    // 因此直接把 window.screen 换成一个与 Chrome 形状一致的普通对象。
    if (P.screen) {
      var sc = P.screen;
      var fakeScreen = {
        width: sc.width, height: sc.height,
        availWidth: sc.availWidth, availHeight: sc.availHeight,
        colorDepth: sc.colorDepth, pixelDepth: sc.pixelDepth,
        availLeft: sc.availLeft || 0, availTop: sc.availTop || 0,
        orientation: { type: sc.orientation || 'landscape-primary', angle: 0 },
        isExtended: false, onchange: null,
        // 注意：故意 **不** 提供 sizeWidth / sizeHeight
      };
      // 浏览器侧 bdms 会读到 "[object Screen]"
      try { Object.defineProperty(fakeScreen, Symbol.toStringTag, { value: 'Screen', configurable: true }); } catch (e) {}
      var ok = false;
      try { Object.defineProperty(window, 'screen', { value: fakeScreen, writable: true, configurable: true }); ok = true; }
      catch (e) { try { window.screen = fakeScreen; ok = true; } catch (e2) {} }
      window.__screenReplaced = ok;
    }
    // 真实页面在签名时刻的 outerWidth/outerHeight 实测为 1296/808（由浏览器侧 VM 探针得出）。
    // 之前错误地按另一次测量把它强制成 0，反而引入了差异。
    if (P.window) {
      try { Object.defineProperty(window, 'outerWidth', { value: P.window.outerWidth, writable: true, configurable: true }); } catch (e) {}
      try { Object.defineProperty(window, 'outerHeight', { value: P.window.outerHeight, writable: true, configurable: true }); } catch (e) {}
    }
    window.__envFixed = {
      screenReplaced: !!window.__screenReplaced,
      sizeWidth: typeof window.screen.sizeWidth,
      outerWidth: window.outerWidth
    };

    // ==== 由「浏览器侧 VM 探针」diff 出的两处真实差异 ====
    // 1) 权限：nv8 默认返回 denied，真实 Chrome 是 prompt（bdms 会读 microphone）
    try {
      var perm = {};
      perm.query = function (desc) {
        return Promise.resolve({
          state: 'prompt', onchange: null,
          addEventListener: function () {}, removeEventListener: function () {},
          dispatchEvent: function () { return true; }
        });
      };
      try { Object.defineProperty(perm, Symbol.toStringTag, { value: 'Permissions', configurable: true }); } catch (e) {}
      try { Object.defineProperty(navigator, 'permissions', { value: perm, configurable: true, writable: true }); }
      catch (e) { navigator.permissions = perm; }
    } catch (e) {}
    // 2) storage.estimate()：真实 Chrome 返回磁盘配额（~5.4e9），nv8 固定 1GiB
    try {
      var sm = {
        estimate: function () { return Promise.resolve({ quota: 5368911241, usage: 202121 }); },
        persist: function () { return Promise.resolve(false); },
        persisted: function () { return Promise.resolve(false); }
      };
      try { Object.defineProperty(sm, Symbol.toStringTag, { value: 'StorageManager', configurable: true }); } catch (e) {}
      try { Object.defineProperty(navigator, 'storage', { value: sm, configurable: true, writable: true }); }
      catch (e) { navigator.storage = sm; }
    } catch (e) {}
    return 'env-ok';
  })()`;
}

/** bdms 会读 localStorage/sessionStorage，把真实页面的内容种子化进来。 */
function storageScript(data) {
  return `(function(){
    var D = ${JSON.stringify(data || {})};
    var n = 0;
    function seed(store, obj) {
      if (!obj) return;
      Object.keys(obj).forEach(function (k) {
        try { store.setItem(k, obj[k]); n++; } catch (e) {}
      });
    }
    try { seed(window.localStorage, D.localStorage); } catch (e) {}
    try { seed(window.sessionStorage, D.sessionStorage); } catch (e) {}
    window.__storageSeeded = n;
    return 'storage:' + n;
  })()`;
}

let bdmsSandbox = null;
let bdmsReady = false;
let bdmsEnvKey = null;

/**
 * 创建/重建 bdms 沙箱。环境（UA/屏幕/uifid）改变时必须重建，
 * 因为 bdms 会在 init 时采集环境。
 */
async function getBdmsSandbox(env) {
  const key = JSON.stringify(env);
  if (bdmsSandbox && bdmsReady && bdmsEnvKey === key) return bdmsSandbox;

  const sb = await EdgeSandbox.create({
    page: { url: 'https://www.douyin.com/', html: '<!doctype html><html><body></body></html>' },
    limits: { timeoutMs: 60000 },
  });
  bdmsReady = false;
  await sb.evaluate(envScript(ENV_PROFILE ? Object.assign({}, ENV_PROFILE, env.overrides || {}) : {}));
  await sb.evaluate(storageScript(ENV_STORAGE));
  await sb.evaluate(BDMS_STUBS);
  // 页面里这些 byted 全局是**同一批、同一个页面上下文**：webmssdk / sdk-glue /
  // secsdk-strategy / uc-secure-dtrait-core / bdms。它们互相读写全局，
  // 因此必须装进**同一个**沙箱上下文，而不是分开沙箱。
  // 顺序按页面实际加载：webmssdk → sdk-glue → secsdk → dtrait-core → bdms。
  try { await sb.evaluate(webmssdkSrc); } catch (e) { process.stderr.write('[abogus] webmssdk failed: ' + e.message + '\n'); }

  // secsdk-strategy 壳需要 document.currentScript.getAttribute('project-id')
  await sb.evaluate(`(function(){
    try {
      window.__fakeScript = { getAttribute: function(k){
        if (k === 'project-id') return 'douyin_web';
        if (k === 'custom-report-host') return '';
        return null;
      } };
      Object.defineProperty(document, 'currentScript', { get: function(){ return window.__fakeScript; }, configurable: true });
    } catch (e) {}
    return 'currentScript';
  })()`);

  // 页面真实的 secsdk/verifyCenter 桩（避免联网加载）
  await sb.evaluate(`(function(){
    window.TTGCaptcha = window.TTGCaptcha || { init: function(){ return true; } };
    window.secsdk = window.secsdk || { csrf: { setOptions: function(){ return true; }, setProtectedHost: function(){ return true; } } };
    return 'secsdk-stubs';
  })()`);
  try { await sb.evaluate(sdkGlueSrc); } catch (e) { process.stderr.write('[abogus] sdk-glue failed: ' + e.message + '\n'); }
  try { await sb.evaluate(secsdkSrc); } catch (e) { process.stderr.write('[abogus] secsdk failed: ' + e.message + '\n'); }
  try { await sb.evaluate(dtraitCore); } catch (e) { process.stderr.write('[abogus] dtrait-core failed: ' + e.message + '\n'); }

  const acr = await sb.evaluate(`(function(){
    var out = { inited: false };
    try {
      if (window.byted_acrawler && typeof window.byted_acrawler.init === 'function') {
        window.byted_acrawler.init({
          aid: ${BDMS_AID}, isSDK: true, boe: false, boeHost: '',
          enablePathList: ${JSON.stringify(BDMS_PATHS)}, urlRewriteRules: []
        });
        out.inited = true;
      } else { out.err = 'no byted_acrawler'; }
    } catch (e) { out.err = String((e && e.message) || e); }
    return JSON.stringify(out);
  })()`);
  process.stderr.write('[abogus] acrawler init: ' + String((acr && acr.value) || acr) + '\n');
  const hasGlue = await sb.evaluate('typeof window._SdkGlueInit');
  process.stderr.write('[abogus] sdk-glue _SdkGlueInit: ' + String((hasGlue && hasGlue.value) || hasGlue)
    + ' | secsdk use: ' + String(((await sb.evaluate('typeof window.use')) || {}).value) + '\n');

  await sb.evaluate(bdmsSrc);

  // init 用 setTimeout 调度，避免个别实现里的同步等待卡住 evaluate
  await sb.evaluate(`(function(){
    window.__initRet = 'scheduled';
    setTimeout(function(){
      try {
        var appBdms = { aid: ${BDMS_AID}, pageId: ${BDMS_PAGE_ID}, paths: ${JSON.stringify(BDMS_PATHS)}, boe: false, ddrt: 8.5, ic: 8.5 };
        var pptBdms = { paths: ['/passport/web/sms_login/','/passport/web/sms_login/','/passport/web/get_qrcode/'] };
        if (typeof window._SdkGlueInit === 'function') {
          // 完全复现页面：应用调一次（带 self），passport SDK 再调一次
          window._SdkGlueInit({ self: { aid: ${BDMS_AID}, pageId: ${BDMS_PAGE_ID} }, bdms: appBdms },
                              { bdms: { srcList: [] } });
          window._SdkGlueInit({ bdms: pptBdms }, { bdms: { srcList: [] } });
          window.__initVia = 'sdk-glue';
        } else {
          window.bdms.init(appBdms);
          window.bdms.init(pptBdms);
          window.__initVia = 'direct';
        }
        window.__initRet = 'ok';
      }
      catch (e) { window.__initRet = 'ERR ' + String((e && e.message) || e); }
    }, 0);
    return 'scheduled';
  })()`);
  await new Promise((r) => setTimeout(r, 1500));
  const st = await sb.evaluate('window.__initRet');
  const val = (st && st.value !== undefined) ? st.value : st;
  if (val !== 'ok') throw new Error('bdms init failed: ' + val);

  // 热身：页面里的 bdms 已经跑很久、签过很多请求（热），我们每次都是刚 init 就签（冷）。
  // 冷状态可能走一段额外的环境采集/判定分支（见 env/browser_vm_probe.md 的 str73 差异）。
  // 这里先让它签一批无关请求，再签目标。
  const warm = await sb.evaluate(`(function(){
    var n = 0;
    var seeds = [
      'https://www.douyin.com/aweme/v1/web/query/user/?aid=6383&device_platform=webapp&channel=channel_pc_web',
      'https://www.douyin.com/aweme/v2/web/module/feed/?aid=6383&device_platform=webapp&channel=channel_pc_web',
      'https://www.douyin.com/aweme/v1/web/aweme/detail/?aid=6383&device_platform=webapp&channel=channel_pc_web'
    ];
    try {
      for (var i = 0; i < ${Number(process.env.ABOGUS_WARMUP || 30)}; i++) {
        var x = new XMLHttpRequest();
        x.open('GET', seeds[i % seeds.length] + '&_w=' + i);
        x.send();
        n++;
      }
    } catch (e) { return 'warm-ERR:' + String((e && e.message) || e); }
    return 'warm:' + n;
  })()`);
  process.stderr.write('[abogus] warmup: ' + String((warm && warm.value) || warm) + '\n');
  bdmsSandbox = sb;
  bdmsReady = true;
  bdmsEnvKey = key;
  const info = await sb.evaluate('JSON.stringify(window.__envApplied)');
  process.stderr.write('[abogus] bdms ready in nv8 ' + String((info && info.value) || info) + '\n');
  return sb;
}

/**
 * 让 bdms 把 a_bogus 追加到给定 URL 上，然后取回 a_bogus 的**编码后**取值。
 * @param {string} url 完整 URL（含 query），应与将要发出的请求一致。
 */
async function makeABogus(url, env, method, body) {
  const sb = await getBdmsSandbox(env);
  const m = (method || 'GET').toUpperCase();
  const script = `(function(){
    window.__cap.length = 0;
    try {
      var x = new XMLHttpRequest();
      x.open(${JSON.stringify(m)}, ${JSON.stringify(url)});
      x.send(${JSON.stringify(body || null)});
    } catch (e) { return JSON.stringify({ err: String((e && e.message) || e) }); }
    var u = window.__cap.length ? window.__cap[window.__cap.length - 1].url : '';
    var m = /[?&]a_bogus=([^&]*)/.exec(u);
    return JSON.stringify({ url: u, a_bogus: m ? m[1] : null });
  })()`;
  const raw = await sb.evaluate(script);
  const text = (raw && raw.value !== undefined) ? raw.value : raw;
  const out = (typeof text === 'string') ? JSON.parse(text) : text;
  if (!out || !out.a_bogus) {
    throw new Error('bdms produced no a_bogus :: ' + JSON.stringify(out).slice(0, 400));
  }
  // bdms 可能自补参数（如 msToken），调用方需要整条签名后的 URL
  return { a_bogus: out.a_bogus, signedUrl: out.url };
}

async function handle(req) {
  switch (req.cmd) {
    case 'ping':
      return { ok: true, node: process.version };
    case 'dtrait':
      return { ok: true, payload: await collectDtrait() };
    case 'abogus': {
      // url 优先；否则用 query 拼到默认端点上
      const env = Object.assign({}, DEFAULT_ENV, req.env || {});
      const url = req.url
        || ('https://login.douyin.com/passport/web/sms_login/?' + String(req.query || ''));
      const r = await makeABogus(url, env, req.method, req.body);
      return { ok: true, a_bogus: r.a_bogus, signedUrl: r.signedUrl };
    }
    default:
      return { ok: false, error: 'unknown cmd: ' + req.cmd };
  }
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });
let pending = 0;
let inputClosed = false;
function maybeExit() { if (inputClosed && pending === 0) process.exit(0); }

rl.on('line', async (line) => {
  const text = line.trim();
  if (!text) return;
  let req;
  try { req = JSON.parse(text); } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: 'bad json' }) + '\n');
    return;
  }
  pending += 1;
  let res;
  try { res = await handle(req); }
  catch (e) { res = { ok: false, error: String((e && e.stack) || e) }; }
  process.stdout.write(JSON.stringify(Object.assign({ id: req.id }, res)) + '\n');
  pending -= 1;
  maybeExit();
});

process.stdout.write(JSON.stringify({ ready: true, node: process.version }) + '\n');
rl.on('close', () => { inputClosed = true; maybeExit(); });
