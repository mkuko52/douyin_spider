"""build.py —— 不依赖 Gradle 的最小 APK 构建（跨平台）。

工具链：Android SDK build-tools（aapt2 / d8 / zipalign / apksigner）+ JDK（javac / keytool）。
SDK 位置：``ANDROID_HOME`` 或 ``ANDROID_SDK_ROOT``；JDK 位置：``JAVA_HOME`` 或 PATH。

    python android/build.py            # 产出 android/douyin-spider.apk
    python android/build.py --install  # 顺带 adb install -r

产物：``android/douyin-spider.apk``（debug 签名，可直接安装）。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ANDROID = Path(__file__).resolve().parent
ROOT = ANDROID.parent
BUILD = ANDROID / "build"
MANIFEST = ANDROID / "app" / "src" / "main" / "AndroidManifest.xml"
JAVA_SRC = ANDROID / "app" / "src" / "main" / "java"
KEYSTORE = ANDROID / "debug.keystore"
APK = ANDROID / "douyin-spider.apk"

MIN_SDK = "21"
TARGET_SDK = "33"
APP_PACKAGE = "com.douyin.spider"
# 编译进 APK 的默认服务地址。不带 --server-url 时就是这个值（会写进 ServerDefault.java）。
# 当前后端就跑在这台机的 WLAN 上；换网络/IP 变了用：
#   python build.py --server-url http://<新IP>:8000
# （模拟器访问宿主机则是 http://10.0.2.2:8000）
DEFAULT_SERVER_URL = "http://192.168.3.67:8000"


def write_server_default(url: str) -> Path:
    """把默认服务地址写进源码（Gradle 与 build.py 共用这一份）。"""
    java = JAVA_SRC / "com" / "douyin" / "spider" / "ServerDefault.java"
    java.parent.mkdir(parents=True, exist_ok=True)
    escaped = url.replace("\\", "\\\\").replace('"', '\\"')
    content = (
        "package com.douyin.spider;\n\n"
        "/**\n"
        " * 编译进 APK 的默认服务地址。\n"
        " *\n"
        " * - Gradle 构建：用本文件里的值（可手改）。\n"
        " * - 免 Gradle 构建：`python android/build.py --server-url http://<本机IP>:8000` 会重写本文件。\n"
        " *\n"
        " * 模拟器访问宿主机用 10.0.2.2；真机填本机局域网 IP。\n"
        " */\n"
        "public final class ServerDefault {\n"
        f'    public static final String URL = "{escaped}";\n\n'
        "    private ServerDefault() { }\n"
        "}\n"
    )
    if not java.exists() or java.read_text(encoding="utf-8") != content:
        java.write_text(content, encoding="utf-8")
    return java


def find_sdk() -> Path:
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(name, "").strip()
        if value and Path(value).is_dir():
            return Path(value)
    raise SystemExit("Android SDK not found; set ANDROID_HOME or ANDROID_SDK_ROOT")


def newest_dir(parent: Path) -> Path:
    dirs = sorted((d for d in parent.iterdir() if d.is_dir()), key=lambda d: d.name)
    if not dirs:
        raise SystemExit(f"no subdirectory under {parent}")
    return dirs[-1]


def _tool(bindir: Path, name: str) -> Path | None:
    found = shutil.which(name, path=str(bindir))
    if found:
        return Path(found)
    for candidate in (bindir / name, bindir / f"{name}.exe", bindir / f"{name}.bat"):
        if candidate.exists():
            return candidate
    return None


def find_java() -> tuple[Path, Path, Path]:
    home = os.environ.get("JAVA_HOME", "").strip()
    candidates = [Path(home) / "bin"] if home else []
    found = shutil.which("javac")
    if found:
        candidates.append(Path(found).parent)
    for bindir in candidates:
        tools = tuple(_tool(bindir, name) for name in ("javac", "java", "keytool"))
        if all(tools):
            return tools  # type: ignore[return-value]
    raise SystemExit("JDK not found; set JAVA_HOME to a JDK (javac/java/keytool)")


def run(cmd: list[str], **kwargs) -> None:
    print("  $ " + " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def manifest_for_aapt2() -> Path:
    """Gradle/AGP 用 namespace（manifest 里不写 package）；aapt2 link 要求有 package。

    这里把 package 注入到 build/ 下的一份临时 manifest，源码只保留一份。
    """
    text = MANIFEST.read_text(encoding="utf-8")
    if "package=" not in text:
        text = text.replace(
            "<manifest xmlns:android=", f'<manifest package="{APP_PACKAGE}" xmlns:android=', 1
        )
    out = BUILD / "AndroidManifest.xml"
    out.write_text(text, encoding="utf-8")
    return out


def build(install: bool, server_url: str) -> int:
    sdk = find_sdk()
    build_tools = newest_dir(sdk / "build-tools")
    javac, java, keytool = find_java()

    android_jar = sdk / "platforms" / f"android-{TARGET_SDK}" / "android.jar"
    if not android_jar.exists():
        android_jar = newest_dir(sdk / "platforms") / "android.jar"
    aapt2 = build_tools / ("aapt2.exe" if os.name == "nt" else "aapt2")
    d8_jar = build_tools / "lib" / "d8.jar"
    apksigner_jar = build_tools / "lib" / "apksigner.jar"
    zipalign = build_tools / ("zipalign.exe" if os.name == "nt" else "zipalign")

    for tool in (aapt2, d8_jar, apksigner_jar, zipalign):
        if not tool.exists():
            raise SystemExit(f"missing build tool: {tool}")

    print(f"sdk         : {sdk}")
    print(f"build-tools : {build_tools}")
    print(f"android.jar : {android_jar}")

    if BUILD.exists():
        shutil.rmtree(BUILD)
    classes = BUILD / "classes"
    dex = BUILD / "dex"
    classes.mkdir(parents=True)
    dex.mkdir(parents=True)

    sources = sorted(str(p) for p in JAVA_SRC.rglob("*.java"))
    write_server_default(server_url)
    print(f"javac       : {len(sources)} file(s)  (server-url default = {server_url})")
    run([javac, "-nowarn", "-encoding", "UTF-8", "-source", "8", "-target", "8",
         "-classpath", android_jar, "-d", classes, *sources])

    print("d8")
    run([java, "-cp", d8_jar, "com.android.tools.r8.D8",
         "--lib", android_jar, "--min-api", MIN_SDK, "--output", dex,
         *sorted(str(p) for p in classes.rglob("*.class"))])

    print("aapt2 link")
    base_apk = BUILD / "base.apk"
    assets = ANDROID / "app" / "src" / "main" / "assets"
    res_dir = ANDROID / "app" / "src" / "main" / "res"

    # res/ -> aapt2 compile -> linked via -R（有 res 才做，保持向后兼容）
    res_args = []
    if res_dir.is_dir() and any(res_dir.rglob("*.xml")):
        compiled = BUILD / "res-compiled"
        compiled.mkdir(parents=True, exist_ok=True)
        res_xmls = sorted(str(p) for p in res_dir.rglob("*.xml"))
        print("aapt2 compile: %d file(s) in res/" % len(res_xmls))
        run([aapt2, "compile", "--dir", str(res_dir), "-o", str(compiled)])
        res_args = ["-R", str(compiled / "*.flat")]
        # 用通配符 aapt2 不展开，改为逐个文件
        flats = sorted(str(p) for p in compiled.rglob("*.flat"))
        res_args = []
        for f in flats:
            res_args += ["-R", f]

    link_cmd = [aapt2, "link", "-o", base_apk, "-I", android_jar,
                "--manifest", manifest_for_aapt2(),
                "--rename-manifest-package", APP_PACKAGE,
                "--min-sdk-version", MIN_SDK, "--target-sdk-version", TARGET_SDK,
                "--auto-add-overlay"]
    if assets.is_dir():
        link_cmd += ["-A", str(assets)]
    link_cmd += res_args
    run(link_cmd)

    with zipfile.ZipFile(base_apk, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.write(dex / "classes.dex", "classes.dex")

    print("zipalign")
    aligned = BUILD / "aligned.apk"
    run([zipalign, "-f", "4", base_apk, aligned])

    if not KEYSTORE.exists():
        print("keytool (debug keystore)")
        run([keytool, "-genkeypair", "-keystore", KEYSTORE, "-alias", "androiddebugkey",
             "-storepass", "android", "-keypass", "android", "-keyalg", "RSA",
             "-keysize", "2048", "-validity", "10000",
             "-dname", "CN=Android Debug,O=Android,C=US"])

    print("apksigner")
    run([java, "-jar", apksigner_jar, "sign",
         "--ks", KEYSTORE, "--ks-pass", "pass:android", "--key-pass", "pass:android",
         "--v4-signing-enabled", "false",
         "--out", APK, aligned])
    run([java, "-jar", apksigner_jar, "verify", "--print-certs", APK])

    print(f"\nAPK: {APK}  ({APK.stat().st_size} bytes)")
    if install:
        adb = sdk / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        run([adb, "install", "-r", APK])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="构建后用 adb install -r")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL,
                        help="编译进 APK 的默认服务地址，真机填本机局域网 IP，如 http://192.168.3.67:8000")
    args = parser.parse_args()
    return build(args.install, args.server_url)


if __name__ == "__main__":
    raise SystemExit(main())
