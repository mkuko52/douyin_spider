package com.douyin.spider;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Ui —— 所有"长相"相关的东西都放这里（颜色、圆角卡片、按钮、胶囊 chip、列表行）。
 *
 * 这样 {@link MainActivity} 只需要关心"有哪些控件、点了做什么"，读起来更像人话。
 * 全部用代码生成控件，不用 XML 布局，也不用 AndroidX。
 */
final class Ui {

    // -------- 配色（照参考图：淡蓝紫极光底 + 白色圆角卡片）--------
    static final int BG_TOP = 0xFFEAF3FF;
    static final int BG_MID = 0xFFF3ECFF;
    static final int BG_BOT = 0xFFE8FBF6;
    static final int PRIMARY_A = 0xFF6AA6F8;
    static final int PRIMARY_B = 0xFF9B8CF5;
    static final int MINT = 0xFF3FD0BE;
    static final int CORAL = 0xFFFF9AA0;
    static final int SAND = 0xFFFFC978;
    static final int LILAC = 0xFFB79CF6;
    static final int TEXT_MAIN = 0xFF20304A;
    static final int TEXT_MUTED = 0xFF8A94AC;
    static final int CARD = 0xFFFFFFFF;
    static final int FIELD_BG = 0xFFF4F7FD;

    // 登录页用的青绿配色（照参考图）
    static final int TEAL = 0xFF0F6E6B;
    static final int TEAL_DARK = 0xFF0A5654;
    static final int TEAL_SOFT = 0xFFE7F1F0;

    private Ui() {
    }

    /** dp 转像素（不同手机密度不一样，写 dp 才能看起来一样大）。 */
    static int dp(Context ctx, int value) {
        return (int) (value * ctx.getResources().getDisplayMetrics().density + 0.5f);
    }

    // -------- 背景形状 --------
    static GradientDrawable gradient(int start, int end) {
        return new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[] { start, end });
    }

    static GradientDrawable gradient3(int top, int mid, int bottom) {
        return new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[] { top, mid, bottom });
    }

    static GradientDrawable rounded(int color, int radiusDp, Context ctx) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(ctx, radiusDp));
        return drawable;
    }

    static GradientDrawable rounded(GradientDrawable drawable, int radiusDp, Context ctx) {
        drawable.setCornerRadius(dp(ctx, radiusDp));
        return drawable;
    }

    static GradientDrawable bordered(int color, int radiusDp, int strokeColor, Context ctx) {
        GradientDrawable drawable = rounded(color, radiusDp, ctx);
        drawable.setStroke(dp(ctx, 1), strokeColor);
        return drawable;
    }

    static GradientDrawable oval(int color) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setShape(GradientDrawable.OVAL);
        drawable.setColor(color);
        return drawable;
    }

    static GradientDrawable oval(GradientDrawable drawable) {
        drawable.setShape(GradientDrawable.OVAL);
        return drawable;
    }

    /** 只有上面两个角是圆的（参考图里那种白色卡片从下方"顶"上来的效果）。 */
    static GradientDrawable roundedTop(int color, int radiusDp, Context ctx) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        float r = dp(ctx, radiusDp);
        drawable.setCornerRadii(new float[] { r, r, r, r, 0, 0, 0, 0 });
        return drawable;
    }

    /** 指定颜色的主按钮（登录页用青绿色）。 */
    static Button primaryButton(Context ctx, String label, int colorA, int colorB) {
        Button button = primaryButton(ctx, label);
        button.setBackground(rounded(gradient(colorA, colorB), 24, ctx));
        return button;
    }

    /** 背景上那几个柔光圆斑（纯装饰，参考图里的极光感）。 */
    static View blob(Context ctx, int color, int size) {
        View view = new View(ctx);
        GradientDrawable shape = new GradientDrawable();
        shape.setShape(GradientDrawable.OVAL);
        shape.setGradientType(GradientDrawable.RADIAL_GRADIENT);
        shape.setGradientRadius(dp(ctx, size / 2));
        shape.setColors(new int[] { color, 0x00FFFFFF });
        view.setBackground(shape);
        return view;
    }

    // -------- 常用控件 --------
    /** 小节标题：粗体大字 + 右边小灰字。 */
    static View sectionTitle(Context ctx, String title, String subtitle) {
        return sectionTitle(ctx, title, subtitle, TEXT_MAIN);
    }

    /** 小节标题（自定义标题颜色，比如青绿主题传 Ui.TEAL）。 */
    static View sectionTitle(Context ctx, String title, String subtitle, int titleColor) {
        LinearLayout holder = new LinearLayout(ctx);
        holder.setOrientation(LinearLayout.HORIZONTAL);
        holder.setGravity(Gravity.BOTTOM);
        holder.setPadding(0, dp(ctx, 4), 0, dp(ctx, 10));

        TextView name = new TextView(ctx);
        name.setText(title);
        name.setTextSize(17f);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        name.setTextColor(titleColor);
        holder.addView(name);

        if (subtitle != null && subtitle.length() > 0) {
            TextView sub = new TextView(ctx);
            sub.setText("   " + subtitle);
            sub.setTextSize(11f);
            sub.setTextColor(TEXT_MUTED);
            holder.addView(sub, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        }
        return holder;
    }

    /** 白色大圆角卡片（内容容器）。 */
    static LinearLayout card(Context ctx) {
        LinearLayout card = new LinearLayout(ctx);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(rounded(CARD, 24, ctx));
        card.setElevation(dp(ctx, 6));
        card.setPadding(dp(ctx, 16), dp(ctx, 16), dp(ctx, 16), dp(ctx, 16));
        return card;
    }

    /** 一行放两个卡片（左 + 右，各占一半）。 */
    static LinearLayout cardRow(Context ctx, View left, View right) {
        LinearLayout row = new LinearLayout(ctx);
        row.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(ctx, 10);
        row.setLayoutParams(lp);
        row.addView(left, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        row.addView(new View(ctx), new LinearLayout.LayoutParams(dp(ctx, 10), 1));
        row.addView(right, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        return row;
    }

    /** 快捷入口小卡（带彩色圆点）。 */
    static View gridCard(Context ctx, String title, String subtitle, int color, final Runnable onClick) {
        LinearLayout card = new LinearLayout(ctx);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(rounded(CARD, 22, ctx));
        card.setElevation(dp(ctx, 5));
        card.setPadding(dp(ctx, 14), dp(ctx, 14), dp(ctx, 14), dp(ctx, 14));
        card.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                onClick.run();
            }
        });

        View dot = new View(ctx);
        dot.setBackground(oval(gradient(color, 0xFFE9F0FF)));
        LinearLayout.LayoutParams dotParams = new LinearLayout.LayoutParams(dp(ctx, 26), dp(ctx, 26));
        dotParams.bottomMargin = dp(ctx, 8);
        dot.setLayoutParams(dotParams);
        card.addView(dot);

        TextView name = new TextView(ctx);
        name.setText(title);
        name.setTextSize(14f);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        name.setTextColor(TEXT_MAIN);
        card.addView(name);

        TextView desc = new TextView(ctx);
        desc.setText(subtitle);
        desc.setTextSize(10f);
        desc.setTextColor(TEXT_MUTED);
        desc.setPadding(0, dp(ctx, 2), 0, 0);
        card.addView(desc);
        return card;
    }

    /** 列表行（彩色圆徽章 + 标题 + 副标题 + 右箭头 ›）。 */
    static View listRow(Context ctx, int color, String title, String subtitle, final Runnable onClick) {
        LinearLayout row = new LinearLayout(ctx);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setBackground(rounded(CARD, 20, ctx));
        row.setElevation(dp(ctx, 4));
        row.setPadding(dp(ctx, 14), dp(ctx, 12), dp(ctx, 14), dp(ctx, 12));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(ctx, 10);
        row.setLayoutParams(lp);
        row.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                onClick.run();
            }
        });

        View badge = new View(ctx);
        badge.setBackground(oval(gradient(color, 0xFFEDF3FF)));
        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(dp(ctx, 30), dp(ctx, 30));
        bp.rightMargin = dp(ctx, 12);
        badge.setLayoutParams(bp);
        row.addView(badge);

        LinearLayout texts = new LinearLayout(ctx);
        texts.setOrientation(LinearLayout.VERTICAL);
        TextView name = new TextView(ctx);
        name.setText(title);
        name.setTextSize(14f);
        name.setTypeface(Typeface.DEFAULT_BOLD);
        name.setTextColor(TEXT_MAIN);
        TextView desc = new TextView(ctx);
        desc.setText(subtitle);
        desc.setTextSize(10f);
        desc.setTextColor(TEXT_MUTED);
        texts.addView(name);
        texts.addView(desc);
        row.addView(texts, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        TextView chevron = new TextView(ctx);
        chevron.setText("›");
        chevron.setTextSize(20f);
        chevron.setTextColor(TEXT_MUTED);
        row.addView(chevron);
        return row;
    }

    /** 胶囊选择器（参考图里那种一排小圆角标签）。 */
    interface ChipCb {
        void onPick(int index);
    }

    static LinearLayout chipRow(Context ctx, final String[] labels, int selected, final ChipCb cb) {
        HorizontalScrollView scroll = new HorizontalScrollView(ctx);
        scroll.setHorizontalScrollBarEnabled(false);

        final LinearLayout row = new LinearLayout(ctx);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, 0, 0, dp(ctx, 8));
        for (int i = 0; i < labels.length; i++) {
            final int index = i;
            TextView chip = new TextView(ctx);
            chip.setText(labels[i]);
            chip.setTextSize(12f);
            chip.setPadding(dp(ctx, 16), dp(ctx, 8), dp(ctx, 16), dp(ctx, 8));
            chip.setLayoutParams(new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT));
            ((LinearLayout.LayoutParams) chip.getLayoutParams()).rightMargin = dp(ctx, 8);
            chip.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) {
                    cb.onPick(index);
                    paintChips(ctx, row, index);
                }
            });
            row.addView(chip);
        }
        scroll.addView(row);
        paintChips(ctx, row, selected);

        LinearLayout holder = new LinearLayout(ctx);
        holder.setOrientation(LinearLayout.VERTICAL);
        holder.addView(scroll);
        holder.setTag(row);
        return holder;
    }

    private static void paintChips(Context ctx, LinearLayout row, int selected) {
        for (int i = 0; i < row.getChildCount(); i++) {
            TextView chip = (TextView) row.getChildAt(i);
            boolean active = i == selected;
            chip.setTextColor(active ? Color.WHITE : TEXT_MUTED);
            chip.setBackground(active
                    ? rounded(gradient(PRIMARY_A, PRIMARY_B), 18, ctx)
                    : bordered(0xFFFFFFFF, 18, 0x22000000, ctx));
        }
    }

    /** 把某个 chipRow 的选中项切到 index（多个页面共用一个设置时，用来保持显示一致）。 */
    static void selectChip(Context ctx, LinearLayout holder, int index) {
        if (holder == null) {
            return;
        }
        Object tag = holder.getTag();
        if (tag instanceof LinearLayout) {
            paintChips(ctx, (LinearLayout) tag, index);
        }
    }

    /** 输入框：浅底圆角，带 hint。``parent`` 传 null 就只返回控件、不挂进容器。 */
    static EditText field(Context ctx, LinearLayout parent, String hint, String value, int inputType, int lines) {
        EditText edit = new EditText(ctx);
        edit.setHint(hint);
        if (value != null && value.length() > 0) {
            edit.setText(value);
        }
        edit.setInputType(inputType);
        edit.setTextSize(14f);
        edit.setTextColor(TEXT_MAIN);
        edit.setHintTextColor(TEXT_MUTED);
        edit.setBackground(rounded(FIELD_BG, 16, ctx));
        edit.setPadding(dp(ctx, 14), dp(ctx, 12), dp(ctx, 14), dp(ctx, 12));
        if (lines > 1) {
            edit.setSingleLine(false);
            edit.setMinLines(lines);
        }
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(ctx, 10);
        edit.setLayoutParams(lp);
        if (parent != null) {
            parent.addView(edit);
        }
        return edit;
    }

    /** 主按钮：蓝紫渐变 + 白字。 */
    static Button primaryButton(Context ctx, String label) {
        Button button = new Button(ctx);
        button.setText(label);
        button.setTextColor(Color.WHITE);
        button.setTextSize(15f);
        button.setTypeface(Typeface.DEFAULT_BOLD);
        button.setAllCaps(false);
        button.setBackground(rounded(gradient(PRIMARY_A, PRIMARY_B), 24, ctx));
        button.setElevation(dp(ctx, 6));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(ctx, 48));
        lp.topMargin = dp(ctx, 4);
        lp.bottomMargin = dp(ctx, 8);
        button.setLayoutParams(lp);
        return button;
    }

    /** 次要按钮：白底描边。 */
    static Button ghostButton(Context ctx, String label) {
        Button button = new Button(ctx);
        button.setText(label);
        button.setTextColor(PRIMARY_B);
        button.setTextSize(13f);
        button.setAllCaps(false);
        button.setBackground(bordered(0xFFFFFFFF, 24, 0x335B8DEF, ctx));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(ctx, 44));
        lp.bottomMargin = dp(ctx, 6);
        button.setLayoutParams(lp);
        return button;
    }

    /** 一条记录的卡片：标题（#1）+ 若干「字段 | 值」行。给「数据」页展示用。 */
    static View recordCard(Context ctx, String title, String[] pairs) {
        LinearLayout card = new LinearLayout(ctx);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackground(rounded(CARD, 18, ctx));
        card.setElevation(dp(ctx, 3));
        card.setPadding(dp(ctx, 14), dp(ctx, 12), dp(ctx, 14), dp(ctx, 12));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(ctx, 10);
        card.setLayoutParams(lp);

        TextView head = new TextView(ctx);
        head.setText(title);
        head.setTextSize(11f);
        head.setTypeface(Typeface.DEFAULT_BOLD);
        head.setTextColor(PRIMARY_B);
        head.setPadding(0, 0, 0, dp(ctx, 6));
        card.addView(head);

        for (String pair : pairs) {
            String[] kv = pair.split("\\|", 2);
            if (kv.length < 2) {
                continue;
            }
            LinearLayout row = new LinearLayout(ctx);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setPadding(0, dp(ctx, 2), 0, dp(ctx, 2));

            TextView label = new TextView(ctx);
            label.setText(kv[0].trim());
            label.setTextSize(11f);
            label.setTextColor(TEXT_MUTED);
            label.setWidth(dp(ctx, 78));
            row.addView(label);

            TextView value = new TextView(ctx);
            value.setText(kv[1].trim());
            value.setTextSize(12f);
            value.setTextColor(TEXT_MAIN);
            row.addView(value, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
            card.addView(row);
        }
        return card;
    }

    /** 居中大圆（首页那个"登录态"球）。 */
    static LinearLayout heroCircle(Context ctx, TextView title, TextView subtitle) {
        LinearLayout hero = new LinearLayout(ctx);
        hero.setOrientation(LinearLayout.VERTICAL);
        hero.setGravity(Gravity.CENTER);
        hero.setBackground(oval(gradient(PRIMARY_A, PRIMARY_B)));
        hero.setElevation(dp(ctx, 10));
        hero.addView(title);
        hero.addView(subtitle);
        return hero;
    }
}
