package com.douyin.spider;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;

/**
 * Icons —— 底栏用的线性图标，全部**用代码画**。
 *
 * 为什么不用图片/vector xml：这个项目没有 res/ 资源目录（APK 里所有界面都是代码生成的），
 * 所以图标也照这个路子来 —— 按 0~1 的比例坐标画好形状，再按 dp 放大，
 * 以后想换大小/换颜色都不用改形状代码。
 */
final class Icons {

    private Icons() {
    }

    /** 形状绘制回调：s 是图标的像素边长，所有坐标都按 s 的比例算。 */
    private interface Painter {
        void paint(Canvas canvas, Paint paint, float s);
    }

    // ------------------------------------------------------------ 对外：四个图标
    /** 房子：主页。 */
    static Drawable home(Context ctx, int color, int sizeDp) {
        return render(ctx, color, sizeDp, new Painter() {
            public void paint(Canvas c, Paint p, float s) {
                Path path = new Path();
                path.moveTo(0.50f * s, 0.05f * s);      // 屋顶尖
                path.lineTo(0.99f * s, 0.48f * s);
                path.lineTo(0.86f * s, 0.48f * s);
                path.lineTo(0.86f * s, 0.95f * s);      // 右墙
                path.lineTo(0.62f * s, 0.95f * s);
                path.lineTo(0.62f * s, 0.66f * s);      // 门的右边
                path.lineTo(0.38f * s, 0.66f * s);      // 门的左边
                path.lineTo(0.38f * s, 0.95f * s);
                path.lineTo(0.14f * s, 0.95f * s);      // 左墙
                path.lineTo(0.14f * s, 0.48f * s);
                path.lineTo(0.01f * s, 0.48f * s);
                path.close();
                c.drawPath(path, p);
            }
        });
    }

    /** 柱状图：数据。 */
    static Drawable data(Context ctx, int color, int sizeDp) {
        return render(ctx, color, sizeDp, new Painter() {
            public void paint(Canvas c, Paint p, float s) {
                float r = 0.05f * s;
                c.drawRoundRect(new RectF(0.10f * s, 0.54f * s, 0.30f * s, 0.92f * s), r, r, p);
                c.drawRoundRect(new RectF(0.40f * s, 0.24f * s, 0.60f * s, 0.92f * s), r, r, p);
                c.drawRoundRect(new RectF(0.70f * s, 0.42f * s, 0.90f * s, 0.92f * s), r, r, p);
            }
        });
    }

    /** 数据库（圆柱 + 两道分隔）：存储。 */
    static Drawable storage(Context ctx, int color, int sizeDp) {
        return render(ctx, color, sizeDp, new Painter() {
            public void paint(Canvas c, Paint p, float s) {
                Paint line = new Paint(p);                  // 沿用同一个颜色，改成描边
                line.setStyle(Paint.Style.STROKE);
                line.setStrokeWidth(0.085f * s);
                line.setStrokeCap(Paint.Cap.ROUND);

                float cx = 0.50f * s;
                float rx = 0.33f * s;
                float ry = 0.135f * s;
                c.drawOval(new RectF(cx - rx, 0.16f * s - ry, cx + rx, 0.16f * s + ry), line);   // 顶盖
                c.drawLine(cx - rx, 0.16f * s, cx - rx, 0.82f * s, line);                       // 左右两条边
                c.drawLine(cx + rx, 0.16f * s, cx + rx, 0.82f * s, line);
                c.drawArc(new RectF(cx - rx, 0.82f * s - ry, cx + rx, 0.82f * s + ry), 0, 180, false, line);  // 底
                c.drawArc(new RectF(cx - rx, 0.40f * s - ry, cx + rx, 0.40f * s + ry), 0, 180, false, line);  // 分隔
                c.drawArc(new RectF(cx - rx, 0.61f * s - ry, cx + rx, 0.61f * s + ry), 0, 180, false, line);
            }
        });
    }

    /** 人像：我的。 */
    static Drawable person(Context ctx, int color, int sizeDp) {
        return render(ctx, color, sizeDp, new Painter() {
            public void paint(Canvas c, Paint p, float s) {
                c.drawCircle(0.50f * s, 0.31f * s, 0.175f * s, p);      // 头
                Path body = new Path();
                body.addArc(new RectF(0.14f * s, 0.53f * s, 0.86f * s, 1.05f * s), 180, 180);
                body.close();                                            // 肩膀（半椭圆）
                c.drawPath(body, p);
            }
        });
    }

    /** 按名字取图标，方便底栏用数组驱动。 */
    static Drawable byName(Context ctx, String name, int color, int sizeDp) {
        if ("home".equals(name)) {
            return home(ctx, color, sizeDp);
        }
        if ("data".equals(name)) {
            return data(ctx, color, sizeDp);
        }
        if ("storage".equals(name)) {
            return storage(ctx, color, sizeDp);
        }
        return person(ctx, color, sizeDp);
    }

    // ------------------------------------------------------------ 内部
    private static Drawable render(Context ctx, int color, int sizeDp, Painter painter) {
        int px = Math.max(1, Ui.dp(ctx, sizeDp));
        Bitmap bitmap = Bitmap.createBitmap(px, px, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(color);
        paint.setStyle(Paint.Style.FILL);
        painter.paint(canvas, paint, px);
        return new BitmapDrawable(ctx.getResources(), bitmap);
    }
}
