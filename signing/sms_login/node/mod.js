// mod.js — verified Node environment for Douyin Web parameter generation (a_bogus).
//
// GENERATED FILE — do not edit by hand. Regenerate with: python tests/build_mod_js.py
//
// provenance:
//   sm3.js    sha256 6d8da1ccc373ac9f2222fdc59ab0cf33a3d41ba1c70ed3120d94bcf54d0c1be6  (js_reverse_cache/source/sm3.js)
//   abogus.js sha256 efc47afe23c0f9320e0416e3b862e0d909fc7c864c7f2582af11fb6beb3e95f7  (js_reverse_cache/source/abogus.js)
//   patches   6 applied, fail-closed
//
// Boundary: parameter generation only. This file performs no network I/O.
// Python (utils/sign.py) bridges via execjs and owns the final HTTP egress.
//
// NOTE: intentionally NOT "use strict" — the vendored a_bogus core assigns
// implicit globals (U, G_DEBUG, ...), which strict mode would reject.
/* eslint-disable */

function __mulberry32(seed) {
  var a = seed >>> 0;
  return function random() {
    a = (a + 0x6d2b79f5) | 0;
    var t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function __frozenDate(now) {
  var RealDate = globalThis.Date;
  function FrozenDate() {
    if (arguments.length === 0) {
      return new RealDate(now);
    }
    var args = Array.prototype.slice.call(arguments);
    return new (Function.prototype.bind.apply(RealDate, [null].concat(args)))();
  }
  FrozenDate.now = function () { return now; };
  FrozenDate.parse = RealDate.parse;
  FrozenDate.UTC = RealDate.UTC;
  FrozenDate.prototype = RealDate.prototype;
  return FrozenDate;
}

// Build one isolated a_bogus environment. `freeze` ({now, seed}) pins Date and
// Math.random so a_bogus becomes reproducible for offline fixed-vector parity.
function __buildEnv(freeze) {
  var window = {
    innerWidth: 1264, innerHeight: 971, outerWidth: 160, outerHeight: 28,
    screen: {
      availWidth: 1920, availHeight: 1032, width: 1920, height: 1080,
      sizeWidth: 1920, sizeHeight: 1080
    }
  };
  var navigator = {
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    platform: "Win32"
  };
  var screen = window.screen;
  var onwheelx = { value: "0X21", writable: false, enumerable: true, configurable: true };
  var Date = freeze ? __frozenDate(Number(freeze.now)) : globalThis.Date;
  var Math = freeze ? __frozenMath(Number(freeze.seed) || 0) : globalThis.Math;

/* ==== BEGIN js_reverse_cache/source/sm3.js ==== */
/*
 * Copyright AngelToms
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * 国密_SM3加密{JS实现}
 * 参考 https://blog.csdn.net/Shen_yuanjia/article/details/111879819
 * https://www.jianshu.com/p/06905998e4e7
 */

function _SM3() {
    if (!(this instanceof _SM3)) {
        return new _SM3();
    }

    this.reg = new Array(8);
    this.chunk = [];
    this.size = 0;

    this.reset();
}

_SM3.prototype.reset = function () {
    this.reg[0] = 0x7380166f;
    this.reg[1] = 0x4914b2b9;
    this.reg[2] = 0x172442d7;
    this.reg[3] = 0xda8a0600;
    this.reg[4] = 0xa96f30bc;
    this.reg[5] = 0x163138aa;
    this.reg[6] = 0xe38dee4d;
    this.reg[7] = 0xb0fb0e4e;
    this.chunk = [];
    this.size = 0;
};

_SM3.prototype.strToBytes = function (s) {
    var ch, st, re = [];
    for (var i = 0; i < s.length; i++) {
        ch = s.charCodeAt(i);
        st = [];
        do {
            st.push(ch & 0xFF);
            ch = ch >> 8;
        }
        while (ch);
        re = re.concat(st.reverse());
    }
    return re;
};

_SM3.prototype.write = function (msg) {
    var m = (typeof msg === 'string') ? this.strToBytes(msg) : msg;
    this.size += m.length;
    var i = 64 - this.chunk.length;
    if (m.length < i) {
        this.chunk = this.chunk.concat(m);
        return;
    }

    this.chunk = this.chunk.concat(m.slice(0, i));
    while (this.chunk.length >= 64) {
        this._compress(this.chunk);
        if (i < m.length) {
            this.chunk = m.slice(i, Math.min(i + 64, m.length));
        } else {
            this.chunk = [];
        }
        i += 64;
    }
};

_SM3.prototype.sum = function (msg, enc) {
    if (msg) {
        this.reset();
        this.write(msg);
    }

    this._fill();
    for (var i = 0; i < this.chunk.length; i += 64) {
        this._compress(this.chunk.slice(i, i + 64));
    }

    var digest = null;
    if (enc == 'hex') {
        digest = "";
        for (var i = 0; i < 8; i++) {
            digest += this.reg[i].toString(16);
        }
    } else {
        var digest = new Array(32);
        for (var i = 0; i < 8; i++) {
            var h;
            h = this.reg[i];
            digest[i * 4 + 3] = (h & 0xff) >>> 0;
            h >>>= 8;
            digest[i * 4 + 2] = (h & 0xff) >>> 0;
            h >>>= 8;
            digest[i * 4 + 1] = (h & 0xff) >>> 0;
            h >>>= 8;
            digest[i * 4] = (h & 0xff) >>> 0;
        }
    }

    this.reset();
    return digest;
};

_SM3.prototype._compress = function (m) {
    var w = this._expand(m);
    var r = this.reg.slice(0);
    for (var j = 0; j < 64; j++) {
        var ss1 = this._rotl(r[0], 12) + r[4] + this._rotl(this._t(j), j)
        ss1 = (ss1 & 0xffffffff) >>> 0;
        ss1 = this._rotl(ss1, 7);

        var ss2 = (ss1 ^ this._rotl(r[0], 12)) >>> 0;
        var tt1 = this._ff(j, r[0], r[1], r[2]);
        tt1 = tt1 + r[3] + ss2 + w[j + 68];
        tt1 = (tt1 & 0xffffffff) >>> 0;
        var tt2 = this._gg(j, r[4], r[5], r[6]);
        tt2 = tt2 + r[7] + ss1 + w[j];
        tt2 = (tt2 & 0xffffffff) >>> 0;
        r[3] = r[2];
        r[2] = this._rotl(r[1], 9);
        r[1] = r[0];
        r[0] = tt1;
        r[7] = r[6]
        r[6] = this._rotl(r[5], 19);
        r[5] = r[4];
        r[4] = (tt2 ^ this._rotl(tt2, 9) ^ this._rotl(tt2, 17)) >>> 0;
    }

    for (var i = 0; i < 8; i++) {
        this.reg[i] = (this.reg[i] ^ r[i]) >>> 0;
    }
};

_SM3.prototype._fill = function () {
    var l = this.size * 8;
    var len = this.chunk.push(0x80) % 64;
    if (64 - len < 8) {
        len -= 64;
    }
    for (; len < 56; len++) {
        this.chunk.push(0x00);
    }

    for (var i = 0; i < 4; i++) {
        var hi = Math.floor(l / 0x100000000);
        this.chunk.push((hi >>> ((3 - i) * 8)) & 0xff);
    }
    for (var i = 0; i < 4; i++) {
        this.chunk.push((l >>> ((3 - i) * 8)) & 0xff);
    }
};

_SM3.prototype._expand = function (b) {
    var w = new Array(132);
    for (var i = 0; i < 16; i++) {
        w[i] = b[i * 4] << 24;
        w[i] |= b[i * 4 + 1] << 16;
        w[i] |= b[i * 4 + 2] << 8;
        w[i] |= b[i * 4 + 3];
        w[i] >>>= 0;
    }

    for (var j = 16; j < 68; j++) {
        var x;
        x = w[j - 16] ^ w[j - 9] ^ this._rotl(w[j - 3], 15);
        x = x ^ this._rotl(x, 15) ^ this._rotl(x, 23);
        w[j] = (x ^ this._rotl(w[j - 13], 7) ^ w[j - 6]) >>> 0;
    }

    for (var j = 0; j < 64; j++) {
        w[j + 68] = (w[j] ^ w[j + 4]) >>> 0;
    }

    return w;
};

_SM3.prototype._rotl = function (x, n) {
    n %= 32;
    return ((x << n) | (x >>> (32 - n))) >>> 0;
};

_SM3.prototype._t = function (j) {
    if (0 <= j && j < 16) {
        return 0x79cc4519;
    } else if (16 <= j && j < 64) {
        return 0x7a879d8a;
    }
};

_SM3.prototype._ff = function (j, x, y, z) {
    if (0 <= j && j < 16) {
        return (x ^ y ^ z) >>> 0;
    } else if (16 <= j && j < 64) {
        return ((x & y) | (x & z) | (y & z)) >>> 0;
    }
};

_SM3.prototype._gg = function (j, x, y, z) {
    if (0 <= j && j < 16) {
        return (x ^ y ^ z) >>> 0;
    } else if (16 <= j && j < 64) {
        return ((x & y) | (~x & z)) >>> 0;
    }
};

_SM3.prototype.toArray = function (s, f) {
    var a = [];
    for (var i = 0; i < s.length; i++) {
        var t = s[i];
        if (f) {
            t = f(t);
        }
        a.push(t);
    }
    return a;
};

function sm3DigestHex(msg) {
    var _sm3 = new _SM3();
    var digest = _sm3.sum(msg);
    var hashHex = _sm3.toArray(digest, function (byte) { return ('0' + (byte & 0xFF).toString(16)).slice(-2); }).join('');
    return hashHex;
}

function sm3Digest(msg) {
    var _sm3 = new _SM3();
    var digest = _sm3.sum(msg);
    return digest;
}

function sm3DigestTwice(msg) {
    var _sm3 = new _SM3();
    var digest = _sm3.sum(msg);
    var digest1 = _sm3.sum(digest);
    return digest1;
}

/* ==== END sm3.js ==== */

/* ==== BEGIN js_reverse_cache/source/abogus.js (patched) ==== */
/*
 * Copyright AngelToms
 * SPDX-License-Identifier: Apache-2.0
 * ylcangel/a_bogus - a_bogus算法实现（从 https://raw.githubusercontent.com/ylcangel/a_bogus 抓取）
 * 适配 Node 运行：本文件末尾附 makeABogus；window/navigator/screen 由宿主 stub 提供。
 */

G_DEBUG = "debug";
G_RELEASE = "release";
programVersion = G_DEBUG;

EnvTestTurnOn = false;
PerformanceTestTurnOn = false;
enterPageTs = +Date.now();

var AB_ARRAY_SIZE = 256;
var DY_SALT = "dhzx";
U = [];

var sdkVersion = "1.0.1.19-fix.01";
var aid = 6383;
var pageId = 6241;

function random(inObj) {
  inval = inObj["0"];
  inval1 = inObj["1"];

  in0 = inval[0];
  in1 = inval[1];

  flag = 0;
  r = Math.random() * 65535;

  r1 = r & 255;
  r2 = (r >> 8) & 255;

  if (inObj["length"] > 1) {
    if (inval1 != void 0) {
      flag = inObj["1"];
    }
  } else {
    flag = 0;
  }

  if (flag === 1) {
    r2 = (Math.random * 40) >> 0;
  }

  if (flag === 2) {
    r1 = (Math.random() * 240) >> 0;
    if (r1 > 109) {
      r1 = r1 + (r1 % 2);
      r1 += 1;
    }
    r2 = ((Math.random * 255) >> 0) & 77;
    r2 |= 1 << 1;
    r2 |= 1 << 4;
    r2 |= 1 << 5;
    r2 |= 1 << 7;
  }

  u1 = (r1 & 170) | (in0 & 85);
  u2 = (r1 & 85) | (in0 & 170);
  u3 = (r2 & 170) | (in1 & 85);
  u4 = (r2 & 85) | (in1 & 170);
  return [u1, u2, u3, u4];
}

function getTxUri(url, method) {
    if (method == 'post') {
        return url + DY_SALT;
    } else {
        return "" + DY_SALT;
    }
}

function createKey() {
    var keyArray = [];
    var magic = 1;
    magic /= AB_ARRAY_SIZE;
    keyArray.push(magic);
    magic = 1;
    magic %= AB_ARRAY_SIZE;
    keyArray.push(magic);
    magic = 10;
    magic %= AB_ARRAY_SIZE;
    keyArray.push(magic);
    return String.fromCharCode.apply(String, keyArray);
};

function dyRc4(key, text) {
    var S = new Uint8Array(AB_ARRAY_SIZE);
    var K = new Uint8Array(AB_ARRAY_SIZE);

    var maxSIndex = AB_ARRAY_SIZE - 1;
    for (var i = 0; i < AB_ARRAY_SIZE; i++) {
        S[i] = maxSIndex - i;
        K[i] = key.charCodeAt(i % key.length);
    }

    var j = 0;
    for (var i = 0; i < AB_ARRAY_SIZE; i++) {
        j = (j * S[i] + j + K[i]) % AB_ARRAY_SIZE;
        [S[i], S[j]] = [S[j], S[i]];
    }

    var i = 0, k = 0;
    var cipher = new Uint8Array(text.length);
    var ucipher = "";

    for (let n = 0; n < text.length; n++) {
        i = (i + 1) % AB_ARRAY_SIZE;
        k = (k + S[i]) % AB_ARRAY_SIZE;
        [S[i], S[k]] = [S[k], S[i]];
        let rnd = S[(S[i] + S[k]) % AB_ARRAY_SIZE];
        cipher[n] = text.charCodeAt(n) ^ rnd;
        ucipher += String.fromCharCode(cipher[n]);
    }
    return ucipher;
}

function dyBase64(ucode, mindex, pad) {
    if (pad === null) {
        pad = "=";
    }

    var letter0 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=";
    var letter1 = "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=";
    var letter2 = "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=";
    var letter3 = "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe";
    var letter4 = "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe";

    var mapTable = {};
    mapTable["s0"] = letter0;
    mapTable["s1"] = letter1;
    mapTable["s2"] = letter2;
    mapTable["s3"] = letter3;
    mapTable["s4"] = letter4;

    var uaTable = mapTable[mindex];

    var uaEncode = "";
    var i = 0;
    while (i < ucode.length) {
        var c1 = ucode.charCodeAt(i++);
        var c2 = _c2 = ucode.charCodeAt(i++);
        var c3 = _c3 = ucode.charCodeAt(i++);

        c1 = (c1 & 255) << 16;

        if (isNaN(_c2)) {
            c2 = 0;
        } else {
            c2 = (c2 & 255) << 8;
        }

        if (isNaN(_c3)) {
            c3 = 0;
        } else {
            c3 = (c3 & 255);
        }

        c = (c1 | c2) | c3;

        var ch1 = (c & 16515072) >> 18;
        var ch2 = (c & 258048) >> 12;
        var ch3 = (c & 4032) >> 6;
        var ch4 = (c & 63);

        uaEncode += uaTable.charAt(ch1);
        uaEncode += uaTable.charAt(ch2);

        if (!isNaN(_c2)) {
            uaEncode += uaTable.charAt(ch3);
        }

        if (!isNaN(_c3)) {
            uaEncode += uaTable.charAt(ch4);
        }

        if (isNaN(_c2)) {
            uaEncode += pad;
        }

        if (isNaN(_c3)) {
            uaEncode += pad;
        }
    }

    return uaEncode;
}

function makeVersionArray(ver) {
    var verArray = [];
    var array = ver.split(".");
    verArray.length = array.length;
    for (var i = 0; i < array.length; i++) {
        array[i] = ~array[i];
        array[i] = ~array[i];
        verArray[i] = array[i];
    }
    return verArray;
}

function u88Transform(array) {
    narray = [];
    var i = 0;
    var E1 = 145, E2 = 110, E3 = 66, E4 = 189, E5 = 44, E6 = 211;
    while (i < array.length) {
        if ((i + 2) < array.length) {
            var x = (Math.random() * 1000) & 255;
            a = (x & E1) | (array[i] & E2);
            b = (x & E3) | (array[i + 1] & E4);
            c = (x & E5) | (array[i + 2] & E6);
            d = (array[i] & E1) | (array[i + 1] & E3) | (array[i + 2] & E5);

            narray.push(a);
            narray.push(b);
            narray.push(c);
            narray.push(d);
        }
        else {
            narray.push(array[i]);
            if (array[i + 1] != void 0) {
                    narray.push(array[i + 1]);
            }
        }
        i += 3;
    }
    return narray;
}

// uri 为调用方传入的完整 query（SDK 内部构造）
function makeABogus(uri, ts) {

    if (programVersion === G_DEBUG && ts !== 0) {
        enterPageTs = ts;
    }

    _ink = +Date.now() - 1;
    navigator.vendorSubs = { ink: _ink };
    ink = navigator.vendorSubs.ink;

    U[0] = [];
    U[0].length = 22;
    U[0][0] = {};
    U[0][1] = { "length": 0 };
    U[0][2] = "aVPX";
    U[0][3] = enterPageTs;
    U[0][4] = 1;

    U[1] = [];
    U[1].length = 9;
    U[1][0] = 1;
    U[1][1] = 0;
    U[1][2] = 8;
    U[1][3] = uri;
    U[1][4] = "";
    U[1][5] = navigator.userAgent;
    U[1][6] = pageId;
    U[1][7] = aid;
    U[1][8] = sdkVersion;

    U[2] = 1;
    U[3] = 0;
    U[4] = 8;

    if (uri.endsWith(DY_SALT)) {
        U[5] = uri;
    } else {
        U[5] = uri + DY_SALT;
    }

    U[6] = "";
    U[7] = navigator.userAgent.trim();
    U[8] = pageId;
    U[9] = aid;
    U[10] = sdkVersion;

    var urlSm3Array = sm3DigestTwice(U[5]);
    haltSm3Array = sm3DigestTwice(U[0][2]);
    var uaCrypt = dyRc4(createKey(), U[7]);

    uaEncode = dyBase64(uaCrypt, "s3", null);
    uaeSm3Array = sm3Digest(uaEncode);

    U[11] = navigator.vendorSubs;
    U[12] = 3;

    window.onwheelx = onwheelx;
    U[13] = window.onwheelx;

    U[14] = +Date.now();

    U[15] = [];

    U[16] = 1;

    U[17] = 10;
    U[18] = urlSm3Array;
    U[19] = haltSm3Array;
    U[20] = uaEncode;
    U[21] = uaeSm3Array;
    U[22] = ink;
    U[23] = [3, 82];
    U[24] = 41;
    U[25] = makeVersionArray(sdkVersion);

    var G1 = [void 0];
    var z = Date;
    var utc = +"1721836800000";
    var gDate = new (Function.bind.apply(z, G1));
    var gNow = gDate.getTime();
    U[26] = ((gNow - utc) / 1000 / 60 / 60 / 24 / 14) >> 0;
    U[27] = 5;

    U[28] = (U[14] - U[0][3] + 3) & 255;
    U[29] = U[14] & 255;
    U[30] = (U[14] >> 8) & 255;
    U[31] = (U[14] >> 16) & 255;
    U[32] = (U[14] >> 24) & 255;
    U[33] = (U[14] / 256 / 256 / 256 / 256) & 255;
    U[34] = (U[14] / 256 / 256 / 256 / 256 / 256) & 255;
    U[35] = (U[16] % 256) & 255;
    U[36] = (U[16] / 256) & 255;

    U[37] = [0, 1, 1, 0, 1];
    U[38] = U[37][4] & 255;
    U[39] = (U[37][4] >> 8) & 255;
    U[40] = U[37][0];
    U[41] = U[37][1];
    U[42] = U[37][2];
    U[43] = U[37][3];
    U[44] = U[17] & 255;
    U[45] = (U[17] >> 8) & 255;
    U[46] = (U[17] >> 16) & 255;
    U[47] = (U[17] >> 24) & 255;
    U[48] = U[18][9];
    U[49] = U[18][18];
    U[50] = 3;
    U[51] = U[18][U[50]];

    U[52] = U[19][10];
    U[53] = U[19][19];
    U[54] = 4;
    U[55] = U[19][U[54]];

    U[56] = U[21][11];
    U[57] = U[21][21];
    U[58] = 5;
    U[59] = U[21][U[58]];

    U[60] = U[22] & 255;
    U[61] = (U[22] >> 8) & 255;
    U[62] = (U[22] >> 16) & 255;
    U[63] = (U[22] >> 24) & 255;
    U[64] = (U[22] / 256 / 256 / 256 / 256) & 255;
    U[65] = (U[22] / 256 / 256 / 256 / 256 / 256) & 255;
    U[66] = U[12];
    U[67] = U[8] & 255;
    U[68] = (U[8] >> 8) & 255;
    U[69] = (U[8] >> 16) & 255;
    U[70] = (U[8] >> 24) & 255;
    U[71] = U[9] & 255;
    U[72] = (U[9] >> 8) & 255;
    U[73] = (U[9] >> 16) & 255;
    U[74] = (U[9] >> 24) & 255;

    innerWinow = Object.defineProperty({}, "innerWidth", {
        value: window.innerWidth >> 0,
        writable: !0,
        configurable: !0,
        enumerable: !0
    });

    innerWinow = Object.defineProperty(innerWinow, "innerHeight", {
        value: window.innerHeight >> 0,
        writable: !0,
        configurable: !0,
        enumerable: !0
    });

    innerWinow = Object.defineProperty(innerWinow, "outerWidth", {
        value: window.outerWidth >> 0,
        writable: !0,
        configurable: !0,
        enumerable: !0
    });

    innerWinow = Object.defineProperty(innerWinow, "outerHeight", {
        value: window.outerHeight >> 0,
        writable: !0,
        configurable: !0,
        enumerable: !0
    });

    innerWinow = Object.defineProperty(innerWinow, "availWidth", {
        value: window.screen.availWidth >> 0,
        writable: !0,
        configurable: !0,
        enumerable: !0
    });

    innerWinow = Object.defineProperty(innerWinow, "availHeight", {
        value: window.screen.availHeight >> 0,
        writable: !0,
        configurable: !0,
        enumerable: !0
    });

    innerWinow = Object.defineProperty(innerWinow, "sizeWidth", {
        value: ((window.screen.width >> 0) == 0) ? 2560 : (window.screen.sizeWidth >> 0),
        writable: !0,
        configurable: !0,
        enumerable: !0
    });

    innerWinow = Object.defineProperty(innerWinow, "sizeHeight", {
        value: ((window.screen.height >> 0) == 0) ? 1440 : (window.screen.sizeHeight >> 0),
        writable: !0,
        configurable: !0,
        enumerable: !0
    });

    innerWinow = Object.defineProperty(innerWinow, "platform", {
        value: navigator.platform,
        writable: !0,
        configurable: !0,
        enumerable: !0
    });

    U[75] = innerWinow;

    U[76] = "";
    keys = Object.keys.apply(Object, [U[75]]);
    for (var key in keys, innerWinow) {
        U[76] += innerWinow[key] + "|";
    }
    U[76] = U[76].substring(0, U[76].length - 1);

    U[77] = [];
    for (var i = 0; i < U[76].length; i++) {
        U[77].push(U[76].charCodeAt(i));
    }

    U[78] = U[77].length;
    U[79] = U[78] & 255;
    U[80] = (U[78] >> 8) & 255;
    U[81] = ((U[14] + 3) & 255) + ",";

    U[82] = [];
    for (var i = 0; i < U[81].length; i++) {
        U[82].push(U[81].charCodeAt(i));
    }

    U[83] = U[82].length;
    U[84] = U[83] & 255;
    U[85] = (U[83] >> 8) & 255;

    var inObj1 = {0:[U[25][0], U[25][1]], length:1};
    var inObj2 = {0:[U[25][0], U[25][1]], 1:2, length:2};
    U[86] = random(inObj1).concat(random(inObj2));

    U[87] = U[86][0] ^ U[86][1] ^ U[86][2] ^ U[86][3] ^ U[86][4] ^ U[86][5] ^ U[86][6] ^ U[86][7] ^
        U[24] ^ U[26] ^ U[27] ^ U[28] ^ U[29] ^ U[30] ^ U[31] ^ U[32] ^ U[33] ^ U[34] ^
        U[35] ^ U[36] ^ U[38] ^ U[39] ^ U[40] ^ U[41] ^ U[42] ^ U[43] ^ U[44] ^ U[45] ^
        U[46] ^ U[47] ^ U[48] ^ U[49] ^ U[51] ^ U[52] ^ U[53] ^ U[55] ^ U[56] ^ U[57] ^
        U[59] ^ U[60] ^ U[61] ^ U[62] ^ U[63] ^ U[64] ^ U[65] ^ U[66] ^ U[67] ^ U[68] ^
        U[69] ^ U[70] ^ U[71] ^ U[72] ^ U[73] ^ U[74] ^ U[79] ^ U[80] ^ U[84] ^ U[85];

    tlist = [U[34], U[44], U[56], U[61], U[73], U[29], U[70], U[45], U[35], U[49],
    U[38], U[66], U[51], U[68], U[28], U[48], U[64], U[47], U[30], U[71],
    U[26], U[55], U[31], U[69], U[59], U[40], U[62], U[63], U[27], U[72],
    U[41], U[74], U[57], U[52], U[42], U[39], U[33], U[67], U[53], U[43],
    U[65], U[46], U[36], U[24], U[60], U[32], U[79], U[80], U[84], U[85]];

    U[88] = tlist.concat(U[77], U[82], [U[87]]);

    inObj = {0:U[23], 1:1, length:2};
    U[89] = random(inObj);
    u89 = String.fromCharCode.apply(String, U[89]);
    U[89] = u89;

    U[90] = u88Transform(U[88]);

    nkey = String.fromCharCode(211);

    t1list = U[86];
    t1list = t1list.concat(U[90]);

    ncode = String.fromCharCode.apply(String, t1list);

    cryptNcode = dyRc4(nkey, ncode);
    U[91] = cryptNcode;

    U[92] = U[89] + U[91];

    U[93] = dyBase64(U[92], "s4", null);

    return U[93];
}


/* ==== END abogus.js ==== */

  return { makeABogus: makeABogus };
}

function __frozenMath(seed) {
  var shadow = Object.create(globalThis.Math);
  shadow.random = __mulberry32(seed);
  return shadow;
}

function __normalize(options) {
  if (options === undefined || options === null || options === "") {
    return {};
  }
  if (typeof options === "string") {
    return JSON.parse(options);
  }
  return options;
}

// Return the a_bogus value for a raw query string.
function signABogus(query, options) {
  var opts = __normalize(options);
  return __buildEnv(opts.freeze).makeABogus(String(query), 0);
}

// Return the same URL with `a_bogus` set.
function signUrl(url, options) {
  var target = new URL(String(url));
  var aBogus = signABogus(target.search.slice(1), options);
  target.searchParams.set("a_bogus", aBogus);
  return target.href;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { signABogus: signABogus, signUrl: signUrl };
}
