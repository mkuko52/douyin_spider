# 抖音爬虫 Android 项目指南

## 项目结构

```
android/
├── build.py                          # 构建脚本（Python 编译 APK）
├── debug.keystore                    # 签名证书
├── douyin-spider.apk                 # 编译输出
│
└── app/src/main/
    ├── AndroidManifest.xml           # App 配置文件
    │
    ├── java/com/douyin/spider/
    │   ├── MainActivity.java         # 主界面（所有页面）
    │   ├── Api.java                  # 网络请求（调用后端）
    │   ├── Ui.java                   # UI 工具（样式、组件）
    │   ├── Icons.java                # 图标绘制
    │   └── ServerDefault.java        # 服务器地址配置
    │
    └── res/                          # XML 资源（设计 token 在这里；布局仍由代码生成）
        ├── drawable/                 # bg_card / bg_field / bg_btn_teal / bg_pill …
        ├── layout/                   # 仅供对照的设计稿（page_login.xml / nav_bar.xml…）
        └── values/                   # colors.xml（dy_* 配色）/ styles.xml（DyField / DyButtonTeal）
```

---

## 界面约定（改 UI 前先读这段）

设计系统在 `Ui.java` + `res/values/` 里已经写好，页面只负责“拼”：

| 要什么 | 用什么 |
|--------|--------|
| 尺寸 / 间距 | **`Ui.dp(this, n)`** |
| 输入框 | `Ui.field(this, parent, hint, value, inputType, lines)` |
| 主按钮 / 次按钮 | `Ui.primaryButton(...)` / `Ui.ghostButton(...)` |
| 白色圆角卡片 | `Ui.card(this)` |
| 小节标题 / 列表行 / 两种卡片 | `Ui.sectionTitle` / `Ui.listRow` / `Ui.gridCard` / `Ui.cardRow` |
| 颜色 | `Ui.TEXT_MAIN` `Ui.TEXT_MUTED` `Ui.CARD` `Ui.FIELD_BG` `Ui.PRIMARY_A/B` `Ui.TEAL` … |
| 图标 | `Icons.byName(ctx, name, color, 24)` |

**三条铁律**（踩过的坑）：

1. **绝不写裸像素**。`setPadding(20,20,20,20)` 在 560dpi 屏上只有 `≈5.7dp`，页面会“挤成一坨”。
   一切尺寸走 `Ui.dp()`。
2. **不要自己 `setBackgroundColor` / `new Button`**。底栏那个灰方角按钮就是这么来的。
3. **底部导航的图标不要在选中时才显示**。图标放在 `pill` 里，若用 `pill.setVisibility(INVISIBLE)`
   控制选中，未选中 tab 的图标会一起消失 —— 正确做法：图标始终可见，只切 `pill` 的背景和文字颜色。

---

## 新手学习路径（按顺序）

### 第 1 步：配置文件

#### AndroidManifest.xml（22 行）

```xml
<manifest>
    <uses-permission android:name="android.permission.INTERNET" />
    <application android:label="Douyin Spider">
        <activity android:name=".MainActivity">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

**作用**：
- 声明需要网络权限（INTERNET）
- 定义 App 名称（Douyin Spider）
- 指定启动界面（MainActivity）

---

### 第 2 步：最简单的文件

#### ServerDefault.java（15 行）

```java
public final class ServerDefault {
    public static final String URL = "http://10.0.2.2:8000";   // 模拟器访问宿主机；真机填局域网 IP
}
```

**作用**：
- 存储 Python 后端服务器地址
- 编译时可通过 `build.py --server-url` 修改

---

### 第 3 步：网络层

#### Api.java（219 行）

**核心接口**：

```java
// 回调接口（请求完成后执行）
interface TextCb {
    void onText(String text);
}

// 异步 GET 请求
static void getAsync(String url, TextCb cb)

// 异步 POST JSON 请求
static void postJsonAsync(String url, String body, TextCb cb)
```

**使用示例**：

```java
// 发送 GET 请求
Api.getAsync("http://10.0.2.2:8000/health", new Api.TextCb() {
    @Override
    public void onText(String text) {
        // text = "HTTP 200\n{...}"
        // 这里更新界面
    }
});

// 发送 POST 请求
String body = "{\"phone\": \"13800138000\"}";
Api.postJsonAsync("http://10.0.2.2:8000/api/auth/send_code", body, new Api.TextCb() {
    @Override
    public void onText(String text) {
        // 处理响应
    }
});
```

**辅助方法**：

| 方法 | 作用 | 示例 |
|------|------|------|
| `jsonValue(text, key)` | 取 JSON 字符串值 | `jsonValue("{\"token\":\"abc\"}", "token")` → `"abc"` |
| `jsonNumber(text, key)` | 取 JSON 数字值 | `jsonNumber("{\"count\":5}", "count")` → `"5"` |
| `esc(value)` | 转义字符串 | `esc("a\"b")` → `"a\\\"b"` |
| `encode(value)` | URL 编码 | `encode("你好")` → `"%E4%BD%A0%E5%A5%BD"` |

---

### 第 4 步：UI 工具

#### Ui.java（429 行）

**颜色常量**：

```java
static final int PRIMARY_A = 0xFF6AA6F8;   // 主色 A（蓝）
static final int PRIMARY_B = 0xFF9B8CF5;   // 主色 B（紫）
static final int CARD = 0xFFFFFFFF;         // 卡片背景（白）
static final int TEXT_MAIN = 0xFF20304A;    // 主文字色
static final int TEXT_MUTED = 0xFF8A94AC;   // 次文字色
```

**常用组件**：

```java
// 圆角背景
Ui.rounded(0xFFFFFFFF, 12, context)  // 白色背景，12dp 圆角

// 主按钮（蓝紫渐变）
Button btn = Ui.primaryButton(context, "点击我");

// 次要按钮（白底描边）
Button btn = Ui.ghostButton(context, "取消");

// 卡片容器
LinearLayout card = Ui.card(context);

// 列表行
View row = Ui.listRow(context, 0xFF4CAF50, "标题", "描述", () -> {
    // 点击事件
});

// 胶囊选择器
LinearLayout chips = Ui.chipRow(context, new String[]{"选项1", "选项2"}, 0, (index) -> {
    // 选择事件
});
```

---

### 第 5 步：图标

#### Icons.java（124 行）

**内置图标**：

| 名称 | 图标 | 方法 |
|------|------|------|
| home | 🏠 房子 | `Icons.home(ctx, color, sizeDp)` |
| data | 📊 柱状图 | `Icons.data(ctx, color, sizeDp)` |
| storage | 💾 数据库 | `Icons.storage(ctx, color, sizeDp)` |
| person | 👤 人像 | `Icons.person(ctx, color, sizeDp)` |

**使用**：

```java
// 按名称获取
Drawable icon = Icons.byName(context, "home", 0xFF666666, 24);

// 设置到 TextView
TextView tv = new TextView(context);
tv.setCompoundDrawablesWithIntrinsicBounds(icon, null, null, null);
```

---

### 第 6 步：主界面（最重要）

#### MainActivity.java（~500 行）

**页面结构**：

```java
// 4 个 tab
private static final String[] TABS = { "主页", "数据", "存储", "我的" };

// 对应的 View
private View[] screens = new View[4];
screens[0] = buildHome();    // 主页
screens[1] = buildData();    // 数据页
screens[2] = buildStore();   // 存储页
screens[3] = buildLogin();   // 登录页
```

**核心方法**：

| 方法 | 作用 |
|------|------|
| `onCreate()` | App 启动时执行，初始化界面 |
| `buildNavBar()` | 构建底部导航栏 |
| `selectTab(int idx)` | 切换 tab |
| `buildHome()` | 构建主页 |
| `buildLogin()` | 构建登录页 |
| `sendVerificationCode()` | 调用后端发验证码 |
| `doLogin()` | 调用后端登录 |
| `saveLoginState()` | 保存 JWT Token |
| `getJwtToken()` | 获取 JWT Token |

**登录流程**：

```
用户输入手机号
     ↓
点击"获取验证码"
     ↓
sendVerificationCode()
     ↓
Api.postJsonAsync(SERVER_URL + "/api/auth/send_code", ...)
     ↓
用户输入验证码
     ↓
点击"登录"
     ↓
doLogin()
     ↓
Api.postJsonAsync(SERVER_URL + "/api/auth/sms_login", ...)
     ↓
saveLoginState(token)  // 保存到 SharedPreferences
```

---

## 代码执行流程

```
App 启动
  ↓
onCreate()
  ↓
创建 4 个页面（主页/数据/存储/我的）
  ↓
显示主页（默认选中 tab 0）
  ↓
用户点击底栏
  ↓
selectTab(idx) 切换页面
  ↓
用户操作（如点击"获取验证码"）
  ↓
调用 Api.postJsonAsync() 发请求到 Python 后端
  ↓
后端处理后返回结果
  ↓
在回调中更新界面显示
```

---

## 构建和运行

### 编译 APK

```bash
python build.py
```

### 编译并安装到手机

```bash
python build.py --install
```

### 修改服务器地址

```bash
python build.py --server-url http://192.168.1.100:8000
```

---

## 与 Python 后端的接口

App 调用的后端 API：

| 接口 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/health` | GET | 无 | 检查服务器状态 |
| `/api/auth/send_code` | POST | `{"phone": "..."}` | 发送验证码（会真发短信） |
| `/api/auth/sms_login` | POST | `{"phone": "...", "code": "..."}` | 短信登录（返回 JWT + 抖音 cookie） |

---

## 开发工具推荐

1. **Android Studio** - 查看代码、调试
2. **adb logcat** - 查看日志
3. **Postman** - 测试后端 API

---

## 常见问题

### Q: 如何查看日志？
```bash
adb logcat -s DYSTEP
```

### Q: 如何修改 App 名称？
编辑 `AndroidManifest.xml` 中的 `android:label`

### Q: 如何添加新页面？
1. 在 `MainActivity.java` 中添加 `buildXxx()` 方法
2. 在 `onCreate()` 中添加到 `screens` 数组
3. 在 `TABS` 数组中添加 tab 名称

### Q: 如何与后端通信？
使用 `Api.postJsonAsync()` 或 `Api.getAsync()`
