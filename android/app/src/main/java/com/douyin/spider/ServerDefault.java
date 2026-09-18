package com.douyin.spider;

/**
 * 编译进 APK 的默认服务地址。
 *
 * - Gradle 构建：用本文件里的值（可手改）。
 * - 免 Gradle 构建：`python android/build.py --server-url http://<本机IP>:8000` 会重写本文件。
 *
 * 模拟器访问宿主机用 10.0.2.2；真机填本机局域网 IP。
 */
public final class ServerDefault {
    public static final String URL = "http://192.168.3.67:8000";

    private ServerDefault() { }
}
