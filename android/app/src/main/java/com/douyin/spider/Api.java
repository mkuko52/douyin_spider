package com.douyin.spider;

import android.os.Handler;
import android.os.Looper;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/**
 * Api —— 和本地 Python 服务说话的工具（只做网络，不碰界面）。
 *
 * 两种用法：
 *   1. 同步版 {@link #get} / {@link #postJson}（会阻塞）；
 *   2. 异步版 {@link #getAsync} / {@link #postJsonAsync}：自动开子线程请求，
 *      回到主线程再把结果交给回调 —— 界面里一律用异步版，别卡 UI。
 */
final class Api {

    private static final int CONNECT_TIMEOUT_MS = 8000;
    private static final int READ_TIMEOUT_MS = 180000;   // 采集可能很久
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private Api() {
    }

    /** 请求结束后的回调，永远在主线程被调用，可以直接改界面。 */
    interface TextCb {
        void onText(String text);
    }

    /** 异步 GET。 */
    static void getAsync(final String url, final TextCb cb) {
        runAsync(url, null, "GET", cb);
    }

    /** 异步 POST JSON。 */
    static void postJsonAsync(final String url, final String body, final TextCb cb) {
        runAsync(url, body, "POST", cb);
    }

    /** 异步 GET，但只把**正文**给回调（去掉 "HTTP 200" 那行）—— 给纯文本接口用。 */
    static void getTextAsync(final String url, final TextCb cb) {
        new Thread(new Runnable() {
            public void run() {
                final String body = stripStatusLine(request(url, null, "GET"));
                MAIN.post(new Runnable() {
                    public void run() {
                        cb.onText(body);
                    }
                });
            }
        }).start();
    }

    private static String stripStatusLine(String raw) {
        int newline = raw.indexOf('\n');
        return newline >= 0 ? raw.substring(newline + 1) : raw;
    }

    private static void runAsync(final String url, final String body, final String method, final TextCb cb) {
        new Thread(new Runnable() {
            public void run() {
                final String text = request(url, body, method);
                MAIN.post(new Runnable() {
                    public void run() {
                        cb.onText(text);
                    }
                });
            }
        }).start();
    }

    /** GET，返回 "HTTP 200\n{...}" 这样的文本（出错也返回文本，方便直接显示）。 */
    static String get(String url) {
        return request(url, null, "GET");
    }

    /** POST JSON，body 形如 {"target":"mysql"}。 */
    static String postJson(String url, String body) {
        return request(url, body, "POST");
    }

    private static String request(String url, String body, String method) {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setRequestMethod(method);
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(READ_TIMEOUT_MS);
            if (body != null) {
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                OutputStream out = conn.getOutputStream();
                out.write(body.getBytes("UTF-8"));
                out.flush();
                out.close();
            }
            int code = conn.getResponseCode();
            InputStream in = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            if (in == null) {
                return "HTTP " + code;
            }
            BufferedReader reader = new BufferedReader(new InputStreamReader(in, "UTF-8"));
            StringBuilder text = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                text.append(line).append('\n');
            }
            reader.close();
            return "HTTP " + code + "\n" + text;
        } catch (Exception e) {
            return "请求失败: " + e;
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    // ------------------------------------------------------------------ 小解析
    /**
     * 取一个 JSON 字符串字段的值：jsonValue("{\"job\": \"123\"}", "job") -> "123"。
     * 够用就行，不引第三方 JSON 库（保持 APK 极简）。
     */
    static String jsonValue(String text, String key) {
        String needle = "\"" + key + "\": \"";
        int start = text.indexOf(needle);
        if (start < 0) {
            needle = "\"" + key + "\":\"";
            start = text.indexOf(needle);
        }
        if (start < 0) {
            return "-";
        }
        start += needle.length();
        int end = text.indexOf('"', start);
        return end > start ? text.substring(start, end) : "-";
    }

    /** 取一个 JSON 数字字段（不带引号的那种）：jsonNumber("{\"cookies\": 50}", "cookies") -> "50"。 */
    static String jsonNumber(String text, String key) {
        int start = text.indexOf("\"" + key + "\":");
        if (start < 0) {
            return "-";
        }
        start += key.length() + 3;
        while (start < text.length() && text.charAt(start) == ' ') {
            start++;
        }
        int end = start;
        while (end < text.length() && "0123456789".indexOf(text.charAt(end)) >= 0) {
            end++;
        }
        return end > start ? text.substring(start, end) : "-";
    }

    /** 取一个 JSON 布尔字段：jsonBool("{\"success\":true}", "success") -> true。 */
    static boolean jsonBool(String text, String key) {
        int start = text.indexOf("\"" + key + "\":");
        if (start < 0) {
            return false;
        }
        start += key.length() + 3;
        while (start < text.length() && text.charAt(start) == ' ') {
            start++;
        }
        return text.startsWith("true", start);
    }

    /** 把 /data/fields 返回里的 "stats":{...} 抠成 "aweme 1 · comment 1" 这种短串。 */
    static String statsLine(String text) {
        int start = text.indexOf("\"stats\":");
        if (start < 0) {
            return "-";
        }
        int open = text.indexOf('{', start);
        int close = text.indexOf('}', open);
        if (open < 0 || close < 0) {
            return "-";
        }
        String[] parts = text.substring(open + 1, close).replace("\"", "").split(",");
        StringBuilder line = new StringBuilder();
        for (int i = 0; i < parts.length; i++) {
            line.append(parts[i].trim().replace(":", " "));
            if (i < parts.length - 1) {
                line.append(" · ");
            }
        }
        return line.length() > 0 ? line.toString() : "-";
    }

    /** 取一个 JSON 字符串数组，拼成 "a · b · c"：给「字段语言」预览用。 */
    static String jsonArray(String text, String key) {
        int start = text.indexOf("\"" + key + "\":");
        if (start < 0) {
            return "";
        }
        int open = text.indexOf('[', start);
        int close = text.indexOf(']', open);
        if (open < 0 || close < 0) {
            return "";
        }
        String[] parts = text.substring(open + 1, close).split(",");
        StringBuilder line = new StringBuilder();
        for (int i = 0; i < parts.length; i++) {
            line.append(parts[i].trim().replace("\"", ""));
            if (i < parts.length - 1) {
                line.append(" · ");
            }
        }
        return line.toString();
    }

    /** URL 参数编码（关键词可能有中文/空格）。 */
    static String encode(String value) {
        try {
            return URLEncoder.encode(value, "UTF-8");
        } catch (Exception e) {
            return value;
        }
    }

    /** 放进 JSON 字符串里的转义。 */
    static String esc(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
