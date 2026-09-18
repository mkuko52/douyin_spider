package com.douyin.spider;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.Base64;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/**
 * MainActivity — 纯 UI 前端
 *
 * 职责：
 *   1. 页面展示和用户交互
 *   2. 调用 Python 后端 API（通过 Api.java）
 *   3. 保存 JWT Token 到 SharedPreferences
 *
 * 不处理：协议签名（a_bogus / dtrait）、抖音请求 —— 都在 Python 后端。
 *
 * 四个页面共用一套青绿风格：
 *   青绿顶栏（白字标题 + 副标题）
 *     └─ 白色上圆角卡片（内容可滚动）
 *          └─ 小节标题（青绿）+ 浅青灰圆角块 + 青绿主按钮
 *   骨架统一走 {@link #tealPage}，内部块走 {@link #softBox} —— 新页面照这两个拼就行。
 *
 * 长相约定（重要）：
 *   - **所有尺寸都走 `Ui.dp(this, n)`**，绝不写裸像素。560dpi 屏上裸像素会被压成
 *     不到 1/3 的视觉尺寸，页面就会"挤成一坨"。
 *   - 控件用 `Ui.field / primaryButton / ghostButton / sectionTitle`，颜色从 `Ui.*` 取。
 */
public class MainActivity extends Activity {

    private static final String TAG = "DYSTEP";

    // 底栏四个 tab
    private static final String[] TABS = { "主页", "数据", "存储", "我的" };
    private static final String[] TAB_ICONS = { "home", "data", "storage", "person" };
    private static final int TAB_HOME = 0;
    private static final int TAB_DATA = 1;
    private static final int TAB_STORE = 2;
    private static final int TAB_MINE = 3;

    // 发码按钮尺寸（照 res/layout/page_login.xml：116x46；这里给"60s后发送"多留一点）
    private static final int SEND_BTN_W_DP = 130;
    private static final int SEND_BTN_H_DP = 46;

    // 服务器地址（从 ServerDefault 获取）
    private static final String SERVER_URL = ServerDefault.URL;

    // UI 组件
    private LinearLayout root;
    private LinearLayout[] navPills;
    private ImageView[] navIcons;
    private TextView[] navLabels;
    private View[] screens;

    // 登录相关
    private TextView loginStatus;
    private EditText phoneInput;
    private EditText codeInput;
    private Button sendCodeBtn;
    private Button logoutBtn;
    private LinearLayout formBox;       // 未登录时显示：手机号 / 验证码 / 登录
    private LinearLayout loggedBox;     // 已登录时显示：账号信息 / 退出登录
    private TextView loggedInfo;
    private TextView loggedUid;
    private TextView homeAuthTitle;     // 主页“快捷入口”里的登录块（随登录状态变文案）
    private TextView homeAuthSub;

    // 发码冷却（秒）。>0 = 冷却中。
    // 一个状态变量同时承担三件事：防重复点击、按钮禁用、倒计时文案 ——
    // （AGENTS.md 教训：别再用独立的 sendingInProgress 标志，那种多标志很容易漏清）
    private int sendCooldown = 0;
    private final Handler uiHandler = new Handler(Looper.getMainLooper());
    private final Runnable cooldownTick = new Runnable() {
        @Override
        public void run() {
            if (sendCooldown <= 0) return;
            sendCooldown--;
            if (sendCooldown > 0) {
                sendCodeBtn.setText(sendCooldown + "s后发送");
                uiHandler.postDelayed(this, 1000);
            } else {
                resetSendCodeBtn();
            }
        }
    };

    // SharedPreferences 键
    private static final String PREFS_NAME = "douyin_spider";
    private static final String KEY_JWT_TOKEN = "jwt_token";
    private static final String KEY_IS_LOGGED_IN = "is_logged_in";
    private static final String KEY_PHONE = "login_phone";
    private static final String KEY_USER_ID = "login_user_id";

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        requestWindowFeature(Window.FEATURE_NO_TITLE);

        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.TEAL);

        screens = new View[TABS.length];
        screens[TAB_HOME] = buildHome();
        screens[TAB_DATA] = buildData();
        screens[TAB_STORE] = buildStore();
        screens[TAB_MINE] = buildLogin();

        for (int i = 0; i < screens.length; i++) {
            screens[i].setVisibility(i == TAB_HOME ? View.VISIBLE : View.GONE);
            root.addView(screens[i], new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        }

        root.addView(buildNavBar());
        setContentView(root);
        selectTab(TAB_HOME);
    }

    @Override
    protected void onDestroy() {
        uiHandler.removeCallbacks(cooldownTick);
        super.onDestroy();
    }

    // ==================== 四页共用的青绿骨架 ====================

    private int dp(int value) {
        return Ui.dp(this, value);
    }

    /**
     * 页面骨架：青绿顶栏（白字大标题 + 两行副标题）+ 白色上圆角卡片。
     * 返回**卡片里的内容容器**（已套好 ScrollView，直接往里面 addView）。
     */
    private LinearLayout tealPage(LinearLayout page, String title, String sub1, String sub2) {
        page.setOrientation(LinearLayout.VERTICAL);
        page.setBackgroundColor(Ui.TEAL);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setPadding(dp(24), dp(30), dp(24), dp(20));

        TextView name = new TextView(this);
        name.setText(title);
        name.setTextSize(26f);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        name.setTextColor(0xFFFFFFFF);
        header.addView(name);

        if (sub1 != null) {
            TextView line = new TextView(this);
            line.setText(sub1);
            line.setTextSize(13f);
            line.setTextColor(0xCCFFFFFF);
            line.setPadding(0, dp(4), 0, 0);
            header.addView(line);
        }
        if (sub2 != null) {
            TextView line = new TextView(this);
            line.setText(sub2);
            line.setTextSize(11f);
            line.setTextColor(0x99FFFFFF);
            line.setPadding(0, dp(2), 0, 0);
            header.addView(line);
        }
        page.addView(header);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(Ui.roundedTop(Ui.CARD, 24, this));
        card.setPadding(dp(22), dp(18), dp(22), dp(14));
        page.addView(card, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        ScrollView scroll = new ScrollView(this);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(content);
        card.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return content;
    }

    /** 卡片里的内容块：浅青灰圆角块（和登录页输入框同款底色）。 */
    private LinearLayout softBox() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setBackground(Ui.rounded(Ui.FIELD_BG, 16, this));
        box.setPadding(dp(14), dp(12), dp(14), dp(12));
        return box;
    }

    /** 可点的整块入口（浅青灰块 + 标题 + 副标题 + 右箭头）。 */
    private View entryBox(String title, String sub, final Runnable onClick) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setBackground(Ui.rounded(Ui.FIELD_BG, 16, this));
        row.setPadding(dp(14), dp(12), dp(14), dp(12));
        row.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                onClick.run();
            }
        });

        LinearLayout texts = new LinearLayout(this);
        texts.setOrientation(LinearLayout.VERTICAL);
        TextView name = new TextView(this);
        name.setText(title);
        name.setTextSize(14f);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        name.setTextColor(Ui.TEXT_MAIN);
        TextView desc = new TextView(this);
        desc.setText(sub);
        desc.setTextSize(11f);
        desc.setTextColor(Ui.TEXT_MUTED);
        texts.addView(name);
        texts.addView(desc);
        row.addView(texts, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));

        TextView chevron = new TextView(this);
        chevron.setText("›");
        chevron.setTextSize(20f);
        chevron.setTextColor(Ui.TEAL);
        row.addView(chevron);

        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(8);
        row.setLayoutParams(lp);
        return row;
    }

    // ==================== 底栏导航 ====================

    private LinearLayout buildNavBar() {
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setBackground(Ui.roundedTop(Ui.CARD, 34, this));
        bar.setElevation(dp(14));
        bar.setPadding(dp(8), dp(8), dp(8), dp(8));

        navPills = new LinearLayout[TABS.length];
        navIcons = new ImageView[TABS.length];
        navLabels = new TextView[TABS.length];

        for (int i = 0; i < TABS.length; i++) {
            final int idx = i;

            LinearLayout slot = new LinearLayout(this);
            slot.setOrientation(LinearLayout.HORIZONTAL);
            slot.setGravity(Gravity.CENTER);

            LinearLayout pill = new LinearLayout(this);
            pill.setOrientation(LinearLayout.VERTICAL);
            pill.setGravity(Gravity.CENTER);
            pill.setPadding(dp(16), dp(7), dp(16), dp(7));

            // 图标始终可见：只有"选中"那颗药丸才换底色。
            // （别再 pill.setVisibility(INVISIBLE) —— 那会把未选中 tab 的图标一起藏掉）
            ImageView icon = new ImageView(this);
            icon.setImageDrawable(Icons.byName(this, TAB_ICONS[i], Ui.TEXT_MUTED, 24));

            TextView label = new TextView(this);
            label.setText(TABS[i]);
            label.setTextSize(10.5f);
            label.setGravity(Gravity.CENTER);
            label.setPadding(0, dp(3), 0, 0);
            label.setTextColor(Ui.TEXT_MUTED);

            pill.addView(icon);
            pill.addView(label);
            slot.addView(pill);
            bar.addView(slot, new LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.MATCH_PARENT, 1));

            navPills[i] = pill;
            navIcons[i] = icon;
            navLabels[i] = label;

            slot.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    selectTab(idx);
                }
            });
        }
        return bar;
    }

    private void selectTab(int idx) {
        if (idx < 0 || idx >= TABS.length) return;

        for (int i = 0; i < screens.length; i++) {
            screens[i].setVisibility(i == idx ? View.VISIBLE : View.GONE);
        }

        for (int i = 0; i < navPills.length; i++) {
            boolean selected = (i == idx);
            // 选中态也是青绿，和四页的主题色一致
            int color = selected ? Ui.TEAL : Ui.TEXT_MUTED;
            navIcons[i].setImageDrawable(Icons.byName(this, TAB_ICONS[i], color, 24));
            navLabels[i].setTextColor(color);
            navPills[i].setBackground(selected
                    ? Ui.rounded(Ui.TEAL_SOFT, 20, this)
                    : null);
        }
    }

    // ==================== 主页 ====================

    private View buildHome() {
        LinearLayout page = new LinearLayout(this);
        LinearLayout content = tealPage(page, "Douyin Spider",
                "抖音数据采集", "登录态由 Python 后端维护");

        content.addView(Ui.sectionTitle(this, "服务器", SERVER_URL, Ui.TEAL));

        LinearLayout statusBox = softBox();
        final TextView statusText = new TextView(this);
        statusText.setText("正在检测…");
        statusText.setTextSize(15f);
        statusText.setTypeface(Typeface.DEFAULT_BOLD);
        statusText.setTextColor(Ui.TEXT_MAIN);
        statusBox.addView(statusText);

        final TextView statusDetail = new TextView(this);
        statusDetail.setTextSize(11f);
        statusDetail.setTextColor(Ui.TEXT_MUTED);
        statusDetail.setPadding(0, dp(4), 0, 0);
        statusBox.addView(statusDetail);

        LinearLayout.LayoutParams statusLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        statusLp.bottomMargin = dp(8);
        content.addView(statusBox, statusLp);
        checkServerStatus(statusText, statusDetail);

        content.addView(Ui.sectionTitle(this, "快捷入口", null, Ui.TEAL));

        final LinearLayout left = softBoxTappable(new Runnable() {
            public void run() {
                selectTab(TAB_DATA);
            }
        }, "采集数据", "视频 / 评论 / 用户");

        // 第二个入口随登录状态变文案（登录后不再提示"手机号 + 验证码"）
        LinearLayout right = softBox();
        right.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                selectTab(TAB_MINE);
            }
        });
        homeAuthTitle = new TextView(this);
        homeAuthTitle.setTextSize(14f);
        homeAuthTitle.setTypeface(Typeface.DEFAULT_BOLD);
        homeAuthTitle.setTextColor(Ui.TEXT_MAIN);
        right.addView(homeAuthTitle);
        homeAuthSub = new TextView(this);
        homeAuthSub.setTextSize(11f);
        homeAuthSub.setTextColor(Ui.TEXT_MUTED);
        homeAuthSub.setPadding(0, dp(2), 0, 0);
        right.addView(homeAuthSub);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.addView(left, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        LinearLayout.LayoutParams gapLp = new LinearLayout.LayoutParams(dp(10), 1);
        row.addView(new View(this), gapLp);
        row.addView(right, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        content.addView(row);

        return page;
    }

    /** 主页快捷入口用的小块（浅青灰 + 标题 + 副标题）。 */
    private LinearLayout softBoxTappable(final Runnable onClick, String title, String sub) {
        LinearLayout box = softBox();
        box.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                onClick.run();
            }
        });
        TextView name = new TextView(this);
        name.setText(title);
        name.setTextSize(14f);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        name.setTextColor(Ui.TEXT_MAIN);
        box.addView(name);
        TextView desc = new TextView(this);
        desc.setText(sub);
        desc.setTextSize(11f);
        desc.setTextColor(Ui.TEXT_MUTED);
        desc.setPadding(0, dp(2), 0, 0);
        box.addView(desc);
        return box;
    }

    private void checkServerStatus(final TextView line, final TextView detail) {
        Api.getAsync(SERVER_URL + "/health", new Api.TextCb() {
            @Override
            public void onText(String text) {
                if (text.contains("HTTP 200")) {
                    line.setText("已连接");
                    line.setTextColor(Ui.MINT);
                    detail.setText(SERVER_URL);
                } else {
                    line.setText("连接失败");
                    line.setTextColor(Ui.CORAL);
                    detail.setText(text.length() > 60 ? text.substring(0, 60) : text);
                }
            }
        });
    }

    // ==================== 数据页 ====================

    private View buildData() {
        LinearLayout page = new LinearLayout(this);
        LinearLayout content = tealPage(page, "采集数据",
                "视频列表 / 详情 / 用户 / 评论", "Phase 2 开始接入");

        content.addView(Ui.sectionTitle(this, "采集目标", null, Ui.TEAL));

        final EditText target = Ui.field(this, content, "输入抖音链接或关键词", null,
                InputType.TYPE_CLASS_TEXT, 1);

        Button fetchBtn = Ui.primaryButton(this, "开始采集", Ui.TEAL, Ui.TEAL_DARK);
        fetchBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (target.getText().toString().trim().isEmpty()) {
                    Toast.makeText(MainActivity.this, "先填链接或关键词", Toast.LENGTH_SHORT).show();
                    return;
                }
                Toast.makeText(MainActivity.this, "Phase 2：后端采集接口还没做", Toast.LENGTH_SHORT).show();
            }
        });
        content.addView(fetchBtn);

        TextView hint = new TextView(this);
        hint.setText("这一页要等 Phase 2（视频 / 评论 / 用户接口）在后端落地后才会真正可用。");
        hint.setTextSize(11f);
        hint.setTextColor(Ui.TEXT_MUTED);
        hint.setPadding(0, dp(6), 0, 0);
        content.addView(hint);

        return page;
    }

    // ==================== 存储页 ====================

    private View buildStore() {
        LinearLayout page = new LinearLayout(this);
        LinearLayout content = tealPage(page, "存储管理",
                "数据导出与登录态", null);

        content.addView(Ui.sectionTitle(this, "数据", null, Ui.TEAL));
        content.addView(entryBox("导出数据", "CSV / JSON（Phase 3）", new Runnable() {
            public void run() {
                Toast.makeText(MainActivity.this, "Phase 3：还没做", Toast.LENGTH_SHORT).show();
            }
        }));
        content.addView(entryBox("登录态", isLoggedIn() ? "已保存到本机" : "尚未登录", new Runnable() {
            public void run() {
                selectTab(TAB_MINE);
            }
        }));

        content.addView(Ui.sectionTitle(this, "服务端", null, Ui.TEAL));
        LinearLayout box = softBox();
        TextView line = new TextView(this);
        line.setText("登录态缓存：后端进程内存（重启即失效）");
        line.setTextSize(12f);
        line.setTextColor(Ui.TEXT_MAIN);
        box.addView(line);
        TextView note = new TextView(this);
        note.setText("要持久化就把后端 core/cache.py 换成真 Redis。");
        note.setTextSize(11f);
        note.setTextColor(Ui.TEXT_MUTED);
        note.setPadding(0, dp(4), 0, 0);
        box.addView(note);
        content.addView(box);

        return page;
    }

    // ==================== 登录页 ====================

    private View buildLogin() {
        LinearLayout page = new LinearLayout(this);
        LinearLayout content = tealPage(page, "Hello!",
                "欢迎使用 Douyin Spider", "免安装 · 直接用抖音 Web 登录");

        TextView title = new TextView(this);
        title.setText("登录");
        title.setTextSize(20f);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(Ui.TEAL);
        content.addView(title);

        loginStatus = new TextView(this);
        loginStatus.setTextSize(11f);
        loginStatus.setPadding(0, dp(6), 0, dp(8));
        content.addView(loginStatus);

        // ---- 未登录：手机号 / 验证码 / 登录（登录成功后整块隐藏）----
        formBox = new LinearLayout(this);
        formBox.setOrientation(LinearLayout.VERTICAL);

        phoneInput = Ui.field(this, formBox, "手机号", null, InputType.TYPE_CLASS_NUMBER, 1);

        LinearLayout codeRow = new LinearLayout(this);
        codeRow.setOrientation(LinearLayout.HORIZONTAL);
        codeRow.setGravity(Gravity.CENTER_VERTICAL);
        codeRow.setPadding(0, dp(2), 0, dp(6));

        codeInput = Ui.field(this, null, "短信验证码", null, InputType.TYPE_CLASS_NUMBER, 1);
        codeRow.addView(codeInput, new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));

        sendCodeBtn = new Button(this);
        sendCodeBtn.setText("获取验证码");
        sendCodeBtn.setTextSize(12f);
        sendCodeBtn.setAllCaps(false);
        sendCodeBtn.setSingleLine(true);
        sendCodeBtn.setTextColor(0xFFFFFFFF);
        sendCodeBtn.setBackground(Ui.rounded(Ui.TEAL, 24, this));
        sendCodeBtn.setPadding(dp(6), 0, dp(6), 0);
        sendCodeBtn.setMinWidth(0);
        sendCodeBtn.setMinimumWidth(0);
        LinearLayout.LayoutParams sendLp = new LinearLayout.LayoutParams(
                dp(SEND_BTN_W_DP), dp(SEND_BTN_H_DP));
        sendLp.leftMargin = dp(8);
        sendCodeBtn.setLayoutParams(sendLp);
        sendCodeBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendVerificationCode();
            }
        });
        codeRow.addView(sendCodeBtn);
        formBox.addView(codeRow);

        Button loginBtn = Ui.primaryButton(this, "登录", Ui.TEAL, Ui.TEAL_DARK);
        loginBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                doLogin();
            }
        });
        formBox.addView(loginBtn);
        content.addView(formBox);

        // ---- 已登录：账号信息 + 退出（未登录时整块隐藏）----
        loggedBox = new LinearLayout(this);
        loggedBox.setOrientation(LinearLayout.VERTICAL);

        LinearLayout accountBox = softBox();
        loggedInfo = new TextView(this);
        loggedInfo.setTextSize(15f);
        loggedInfo.setTypeface(Typeface.DEFAULT_BOLD);
        loggedInfo.setTextColor(Ui.TEXT_MAIN);
        accountBox.addView(loggedInfo);

        loggedUid = new TextView(this);
        loggedUid.setTextSize(11f);
        loggedUid.setTextColor(Ui.TEXT_MUTED);
        loggedUid.setPadding(0, dp(4), 0, 0);
        accountBox.addView(loggedUid);
        loggedBox.addView(accountBox, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView note = new TextView(this);
        note.setText("登录态（抖音 cookie）存在 Python 后端，App 只保存后端 JWT。");
        note.setTextSize(11f);
        note.setTextColor(Ui.TEXT_MUTED);
        note.setPadding(0, dp(6), 0, dp(10));
        loggedBox.addView(note);

        logoutBtn = Ui.ghostButton(this, "退出登录");
        logoutBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                doLogout();
            }
        });
        loggedBox.addView(logoutBtn);
        content.addView(loggedBox);

        updateLoginStatus();
        return page;
    }

    // ==================== 登录逻辑（调用 Python 后端） ====================

    private void sendVerificationCode() {
        if (sendCooldown > 0) {
            Toast.makeText(this, sendCooldown + "s 后可重发", Toast.LENGTH_SHORT).show();
            return;
        }

        String phone = phoneInput.getText().toString().trim();
        if (!isValidPhone(phone)) {
            Toast.makeText(this, "请输入 11 位手机号", Toast.LENGTH_SHORT).show();
            return;
        }

        sendCodeBtn.setEnabled(false);
        sendCodeBtn.setText("发送中...");
        loginStatus.setTextColor(Ui.TEXT_MUTED);
        loginStatus.setText("正在发送验证码...");
        Log.i(TAG, "send_code start phone=" + phone);

        // 调用 Python 后端：POST /api/auth/send_code  {"phone": "..."}
        String body = "{\"phone\": \"" + Api.esc(phone) + "\"}";
        Api.postJsonAsync(SERVER_URL + "/api/auth/send_code", body, new Api.TextCb() {
            @Override
            public void onText(String text) {
                // 注意：业务失败也是 HTTP 200，必须看 success 字段
                if (Api.jsonBool(text, "success")) {
                    Log.i(TAG, "send_code ok retry_after=" + Api.jsonNumber(text, "retry_after"));
                    loginStatus.setTextColor(Ui.MINT);
                    loginStatus.setText("验证码已发送");
                    Toast.makeText(MainActivity.this, "验证码已发送", Toast.LENGTH_SHORT).show();
                    // 冷却秒数用后端的 retry_after（抖音 retry_time），拿不到就 60s
                    startCooldown(jsonInt(Api.jsonNumber(text, "retry_after"), 60));
                } else {
                    resetSendCodeBtn();          // 所有失败路径都要还原按钮
                    String msg = messageOf(text);
                    Log.i(TAG, "send_code fail: " + msg);
                    loginStatus.setTextColor(Ui.CORAL);
                    loginStatus.setText("发送失败: " + msg);
                    Toast.makeText(MainActivity.this, "发送失败: " + msg, Toast.LENGTH_LONG).show();
                }
            }
        });
    }

    /** 开始倒计时：按钮显示 "60s后发送" 并每秒 -1，到 0 自动恢复。 */
    private void startCooldown(int seconds) {
        sendCooldown = Math.max(1, seconds);
        uiHandler.removeCallbacks(cooldownTick);
        sendCodeBtn.setEnabled(false);
        sendCodeBtn.setText(sendCooldown + "s后发送");
        uiHandler.postDelayed(cooldownTick, 1000);
    }

    private void resetSendCodeBtn() {
        sendCooldown = 0;
        uiHandler.removeCallbacks(cooldownTick);
        sendCodeBtn.setEnabled(true);
        sendCodeBtn.setText("获取验证码");
    }

    private void doLogin() {
        String phone = phoneInput.getText().toString().trim();
        String code = codeInput.getText().toString().trim();

        if (!isValidPhone(phone)) {
            Toast.makeText(this, "请输入 11 位手机号", Toast.LENGTH_SHORT).show();
            return;
        }
        if (code.isEmpty()) {
            Toast.makeText(this, "请输入验证码", Toast.LENGTH_SHORT).show();
            return;
        }

        loginStatus.setTextColor(Ui.TEXT_MUTED);
        loginStatus.setText("正在登录...");
        Log.i(TAG, "sms_login start");

        // 调用 Python 后端：POST /api/auth/sms_login  {"phone": "...", "code": "..."}
        String body = "{\"phone\": \"" + Api.esc(phone) + "\", \"code\": \"" + Api.esc(code) + "\"}";
        Api.postJsonAsync(SERVER_URL + "/api/auth/sms_login", body, new Api.TextCb() {
            @Override
            public void onText(String text) {
                // 注意：业务失败（2156 系统繁忙 / 1203 码错 / 7 风控）也是 HTTP 200
                if (Api.jsonBool(text, "success")) {
                    String token = Api.jsonValue(text, "token");
                    String userId = Api.jsonValue(text, "user_id");
                    if (!"-".equals(token)) {
                        saveLoginState(token, phone, userId);
                    }
                    Log.i(TAG, "sms_login ok user_id=" + userId);
                    loginStatus.setTextColor(Ui.MINT);
                    loginStatus.setText("登录成功");
                    Toast.makeText(MainActivity.this, "登录成功", Toast.LENGTH_SHORT).show();
                } else {
                    String msg = messageOf(text);
                    Log.i(TAG, "sms_login fail: " + msg);
                    loginStatus.setTextColor(Ui.CORAL);
                    loginStatus.setText("登录失败: " + msg);
                    Toast.makeText(MainActivity.this, "登录失败: " + msg, Toast.LENGTH_LONG).show();
                }
            }
        });
    }

    private void doLogout() {
        clearLoginState();
        loginStatus.setTextColor(Ui.TEXT_MUTED);
        loginStatus.setText("已退出登录");
        Toast.makeText(this, "已退出登录", Toast.LENGTH_SHORT).show();
    }

    private static boolean isValidPhone(String phone) {
        if (phone.length() != 11) return false;
        for (int i = 0; i < phone.length(); i++) {
            if (!Character.isDigit(phone.charAt(i))) return false;
        }
        return true;
    }

    private static int jsonInt(String value, int fallback) {
        try {
            return Integer.parseInt(value.trim());
        } catch (Exception e) {
            return fallback;
        }
    }

    /** 从响应里取给用户看的一句话：业务 message -> 参数错误 detail -> 兵底。 */
    private static String messageOf(String text) {
        String msg = Api.jsonValue(text, "message");
        if ("-".equals(msg)) msg = Api.jsonValue(text, "detail");
        if ("-".equals(msg)) msg = "网络错误或服务未启动";
        return msg;
    }

    // ==================== 登录状态管理 ====================

    private void updateLoginStatus() {
        boolean logged = isLoggedIn() && !getJwtToken().isEmpty();

        if (loginStatus != null) {
            if (logged) {
                loginStatus.setTextColor(Ui.MINT);
                loginStatus.setText("已登录");
            } else {
                loginStatus.setTextColor(Ui.TEXT_MUTED);
                loginStatus.setText("未登录");
            }
        }

        // 登录之后就不该再看到"未登录"那些控件（手机号/验证码/获取验证码/登录）
        if (formBox != null) {
            formBox.setVisibility(logged ? View.GONE : View.VISIBLE);
        }
        if (loggedBox != null) {
            loggedBox.setVisibility(logged ? View.VISIBLE : View.GONE);
        }
        if (logged && loggedInfo != null) {
            String phone = prefs().getString(KEY_PHONE, "");
            String uid = prefs().getString(KEY_USER_ID, "");
            if (uid.length() == 0) {
                uid = userIdFromToken(getJwtToken());   // 旧版本登录只存了 token，从 JWT 里读回来
            }
            loggedInfo.setText(phone.length() > 0 ? maskPhone(phone) : "抖音账号");
            loggedUid.setText(uid.length() > 0 ? "用户 ID：" + uid : "用户 ID：—");
        }

        // 主页快捷入口也跟着变
        if (homeAuthTitle != null) {
            homeAuthTitle.setText(logged ? "账号" : "登录");
            homeAuthSub.setText(logged ? "已登录 · 可查看状态" : "手机号 + 短信验证码");
        }
    }

    /** 从 JWT 的 payload 里读出 user_id（只 base64 解码，签名始终由后端校验）。 */
    private static String userIdFromToken(String token) {
        try {
            String[] parts = token.split("\\.");
            if (parts.length < 2) return "";
            String payload = parts[1];
            while (payload.length() % 4 != 0) {
                payload += "=";
            }
            String json = new String(Base64.decode(payload,
                    Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING), "UTF-8");
            String uid = Api.jsonValue(json, "user_id");
            return "-".equals(uid) ? "" : uid;
        } catch (Exception e) {
            return "";
        }
    }

    /** 138****8000 */
    private static String maskPhone(String phone) {
        if (phone == null || phone.length() != 11) return phone;
        return phone.substring(0, 3) + "****" + phone.substring(7);
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
    }

    private void saveLoginState(String token, String phone, String userId) {
        prefs().edit()
                .putBoolean(KEY_IS_LOGGED_IN, true)
                .putString(KEY_JWT_TOKEN, token)
                .putString(KEY_PHONE, phone)
                .putString(KEY_USER_ID, "-".equals(userId) ? "" : userId)
                .apply();
        updateLoginStatus();
    }

    private void clearLoginState() {
        prefs().edit()
                .putBoolean(KEY_IS_LOGGED_IN, false)
                .putString(KEY_JWT_TOKEN, "")
                .putString(KEY_USER_ID, "")
                .apply();
        updateLoginStatus();
    }

    public String getJwtToken() {
        return prefs().getString(KEY_JWT_TOKEN, "");
    }

    public boolean isLoggedIn() {
        return prefs().getBoolean(KEY_IS_LOGGED_IN, false);
    }
}
