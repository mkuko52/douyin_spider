// dtrait_server.mjs —— 用 **nv8 补环境框架**现场采集 `x-tt-session-dtrait` 的 payload。
//
// 职责：只产出设备指纹 payload（JSON），**不发任何网络**。
//        RSA-2048 包 (AES key‖iv) + AES-128-CBC 加密由 Python 侧做（utils/dtrait.py）。
//
// 为什么必须用 nv8：
//   `uc-secure-dtrait-core`（assets/dtrait_core.js）是 JSVMP 混淆库，会读
//   navigator / screen / canvas / WebGL 等大量浏览器环境特征 —— 裸 Node 跑不了，
//   nv8 就是把这套环境补到“检测不出来”的运行时。
//
// 协议：JSON-Lines over stdio（常驻，只启一次沙箱）。
//   -> {"id":1,"cmd":"dtrait"}      <- {"id":1,"ok":true,"payload":{...}}
//   -> {"id":2,"cmd":"ping"}        <- {"id":2,"ok":true}
//
// 环境变量：NV8_SRC 覆盖 nv8 入口，默认 D:/develop_software/nv8/src/index.js
//
// 采集顺序（踩过的坑）：必须先替换 window.fetch，再 getInstance；
// 反过来会把 SDK 自己的请求拦截器顶掉，永远采不到 payload。

import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const NV8_SRC = process.env.NV8_SRC || 'D:/develop_software/nv8/src/index.js';

const dtraitCore = fs.readFileSync(path.join(ROOT, 'assets/dtrait_core.js'), 'utf8');
const rsa = JSON.parse(fs.readFileSync(path.join(ROOT, 'assets/dtrait_rsa.json'), 'utf8'));

const { EdgeSandbox } = await import(pathToFileURL(NV8_SRC).href);

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

let sandbox = null;

async function getSandbox() {
  if (sandbox) return sandbox;
  const sb = await EdgeSandbox.create({
    page: { url: 'https://www.douyin.com/', html: '<!doctype html><html><body></body></html>' },
    limits: { timeoutMs: 120000 },
  });
  // 核心在模块加载时 console.log('[params]', payload)，且是两个参数 —— 必须拼起来再解析
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
  sandbox = sb;
  return sb;
}

async function collectDtrait() {
  const sb = await getSandbox();
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

// --------------------------------------------------------------- JSON-Lines
function send(obj) { process.stdout.write(JSON.stringify(obj) + '\n'); }

process.stdout.write(JSON.stringify({ ready: true, nv8: NV8_SRC }) + '\n');

const rl = readline.createInterface({ input: process.stdin });
for await (const line of rl) {
  const text = line.trim();
  if (!text) continue;
  let req;
  try { req = JSON.parse(text); } catch (e) { send({ ok: false, error: 'bad json' }); continue; }
  try {
    if (req.cmd === 'ping') send({ id: req.id, ok: true });
    else if (req.cmd === 'dtrait') send({ id: req.id, ok: true, payload: await collectDtrait() });
    else send({ id: req.id, ok: false, error: 'unknown cmd ' + req.cmd });
  } catch (e) {
    send({ id: req.id, ok: false, error: String((e && e.message) || e) });
  }
}
