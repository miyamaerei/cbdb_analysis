# -*- coding: utf-8 -*-
"""端到端冒烟测试：跑一遍所有页面的关键链路，打印 PASS / FAIL。

用法（服务需先启动）：
    python kg/app_gradio.py --port 7860 --no-browser
    python kg/smoke_test.py                     # 默认 127.0.0.1:7860
    python kg/smoke_test.py --pid 25403 --quad cbdb_dy53   # 换人物/图谱

为什么单独有个文件：
  * 手动点界面测不出来「浏览器实际提交值」（如空 Number → 0）——必须走 HTTP
  * 页面按钮都有**显式 api_name**（Q2_run / detail_load / search_query …），
    自动编号的 `_run_1` 会随页面顺序漂移，不能用。

⚠️ 两条容易漏的更新点（改界面后同步这里）：
  * `search_query` 的参数列表要与 `handlers.do_query` 的签名**逐位对齐**，
    末尾四个是界面增强项：`order_by, desc, cols, dense`；
  * 组件返回的可能是 `gr.update(...)` 的 dict（外层 `value` 才是 Dataframe），
    所以判定行数/表头一律走 `_table()`，别直接 `x["data"]`。
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kg_backend as K                                    # noqa: E402


def _table(x):
    """Dataframe 输出 → (headers, data)。

    Gradio 返回的可能是 update 包装：
        {"headers":…, "value": {"headers":…, "data":[[…]]}, "elem_classes":[…]}
    也可能已经被拆平成 {"headers":…, "data":[[…]]}。两种都吃。
    """
    if isinstance(x, dict):
        inner = x.get("value")
        if isinstance(inner, dict):
            x = inner
        return list(x.get("headers") or []), list(x.get("data") or [])
    return [], ([] if x is None else list(x))


def _rows(x):
    """行数。"""
    return len(_table(x)[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:7860")
    ap.add_argument("--pid", default="30374", help="测试用 personid（默认王守仁）")
    ap.add_argument("--quad", default=None, help="图谱路径，默认取下拉第一项")
    ap.add_argument("--name", default="王守仁")
    args = ap.parse_args()

    from gradio_client import Client
    c = Client(args.url, verbose=False)
    quad = args.quad or K.quad_choices()[0][1]
    db = K.DEFAULT_DB
    print(f"服务 {args.url}　图谱 {os.path.basename(quad)}　pid {args.pid}")

    def call(api, *a, tries=4):
        """Gradio 偶发返回队列状态 dict，重试到拿到真结果。

        「真结果」的判据：tuple / str，或带 headers/value 的 Dataframe 输出。
        """
        last = None
        for _ in range(tries):
            r = c.predict(*a, api_name=api)
            if isinstance(r, (tuple, str)):
                return r
            if isinstance(r, dict) and ("value" in r or "headers" in r):
                return r
            last = r
            time.sleep(1.5)
        raise RuntimeError(f"{api} 返回异常: {str(last)[:200]}")

    # search_query 的位置参数（顺序 = page_search.build() 里的 inputs）
    def search(name="", **kw):
        a = dict(pinyin="", gender="全部", bf="", bt="", df_="", dt="", ifrom="", ito="",
                 jinshi=False, official=False, malt=False, nb=False, lim=200, dy=19,
                 quad=quad, order_by="personid", desc=False,
                 cols=K.RESULT_DEFAULT_COLS, dense=True)
        a.update(kw)
        return call("/search_query", name, *a.values())

    ok = fail = 0

    def check(label, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  PASS  {label}  {detail}")
        else:
            fail += 1
            print(f"  FAIL  {label}  {detail}")

    print("\n[1] 查询页 search_query（年份全空）")
    r = search(args.name)
    hd, dt = _table(r[0])
    check("姓名检索返回结果", len(dt) > 0, f"{len(dt)} 行，首行 {dt[0][:2] if dt else None}")
    check("条件栏不含「生年≥0」", "生年≥0" not in (r[2] or ""), r[2])
    check("命中提示含命中数与耗时", "命中" in r[1] and "s" in r[1],
          r[1].splitlines()[0][:60])
    check("提示第二行是已生效条件", "已生效条件" in r[1],
          [l for l in r[1].splitlines() if l.startswith("**已生效")][:1])
    check("表头为中文（personid → ID）", hd[:2] == ["ID", "姓名"], str(hd[:4]))

    print("\n[2] 排序 / 显示列 / 即时重绘（界面增强项）")
    r_s = search(name="王", order_by="birth", desc=True, lim=200)
    _h, dt_s = _table(r_s[0])
    yrs = [row[3] for row in dt_s if isinstance(row[3], int)]
    check("按生年降序生效", bool(yrs) and yrs[:5] == sorted(yrs[:5], reverse=True),
          f"前 5 生年 {yrs[:5]}")
    r_c = search(name="王", cols=["生年", "朝代"])
    hd_c, dt_c = _table(r_c[0])
    check("显示列裁剪（ID/姓名恒在最前）",
          hd_c == ["ID", "姓名", "生年", "朝代"], str(hd_c))
    check("裁剪后每行宽度与表头一致",
          all(len(row) == len(hd_c) for row in dt_c[:20]), f"宽度 {len(dt_c[0]) if dt_c else 0}")
    av = call("/apply_view", ["朝代"], False)
    hd_a, dt_a = _table(av)
    check("apply_view 用上次结果即时重绘（不查库）",
          hd_a == ["ID", "姓名", "朝代"] and len(dt_a) == len(dt_c), str(hd_a))

    print("\n[3] 详情页 detail_load")
    d = call("/detail_load", args.pid, quad, db)
    check("载入单人档案", "person/" in d[0], d[0].splitlines()[0][:50])
    check("分区表有数据", _rows(d[2]) + _rows(d[3]) > 0,
          f"亲属 {_rows(d[2])} / 交遊 {_rows(d[3])}")

    print("\n[4] 专题页 Q1~Q9")
    qcases = {
        "Q1_run": (quad, args.pid),                       # 完整档案（纯 Markdown）
        "Q2_run": (quad, args.pid, "双向"),               # 亲属称谓
        "Q3_run": (quad, args.pid, 2, False, "3000"),     # N 度家族网
        "Q4_run": (quad, args.pid, "求师(向上)", 2),      # 师承链
        "Q5_run": (quad, "", args.pid),                   # 同年进士（用人物反推年份）
        "Q6_run": (quad, args.pid),                       # 任职轨迹
        "Q7_run": (quad, "余姚", "明"),                   # 某县某朝（简体输入）
        "Q8_run": (quad, "传习录"),                       # 某书人物
        "Q9_run": (quad, "理學"),                         # 学派主题网
    }
    for api, a in qcases.items():
        out = call(f"/{api}", *a)
        head = out[0] if isinstance(out, tuple) else out
        body = str(head)
        check(f"{api} 不报错", "❌" not in body and "Traceback" not in body,
              body.splitlines()[0][:56] if body else "(空)")

    print("\n[5] 空输入 / 异常输入")
    q2_bad = call("/Q2_run", quad, "99999999", "双向")
    check("Q2 查不存在的人给提示", "未找到" in str(q2_bad[0]), str(q2_bad[0])[:40])
    q2_empty = call("/Q2_run", quad, "", "双向")
    check("Q2 空 pid 给提示", "personid" in str(q2_empty[0]), str(q2_empty[0])[:40])
    d_empty = call("/detail_load", "", quad, db)
    check("详情空 pid 给提示", "personid" in d_empty[0], d_empty[0][:40])

    print("\n[6] 导出")
    search(args.name)
    e = call("/export_run", ["CSV"], False, "50")
    check("导出页出文件", bool(e[1]), str(e[0])[:60].replace("\n", " "))
    e1 = call("/Q1_export", quad, args.pid)
    check("Q1 导出档案", bool(e1[1]), str(e1[0])[:60].replace("\n", " "))

    print(f"\n结果：PASS {ok}　FAIL {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
