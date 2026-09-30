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
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kg_backend as K                                    # noqa: E402


def _rows(x):
    """Dataframe 组件的值是 dict（headers/data/metadata），行数看 data。"""
    if isinstance(x, dict):
        return len(x.get("data") or [])
    return 0 if x is None else len(x)


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
        """Gradio 偶发返回 dict（队列状态），重试到拿到 tuple/str。"""
        last = None
        for _ in range(tries):
            r = c.predict(*a, api_name=api)
            if isinstance(r, (tuple, str)):
                return r
            last = r
            time.sleep(1.5)
        raise RuntimeError(f"{api} 返回异常: {str(last)[:200]}")

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
    r = call("/search_query", args.name, "", "全部", "", "", "", "", "", "",
             False, False, False, False, 200, 19, quad)
    rows, count_md, cond_md = r[0], r[1], r[2]
    check("姓名检索返回结果", _rows(rows) > 0, f"{_rows(rows)} 行，首行 "
          f"{rows['data'][0][:2] if _rows(rows) else None}")
    check("条件栏不含「生年≥0」", "生年≥0" not in (cond_md or ""), cond_md)
    check("命中提示正确", "命中" in count_md, count_md.split("|")[0].strip()[:40])

    print("\n[2] 详情页 detail_load")
    d = call("/detail_load", args.pid, quad, db)
    check("载入单人档案", "person/" in d[0], d[0].splitlines()[0][:50])
    check("分区表有数据", _rows(d[2]) + _rows(d[3]) > 0,
          f"亲属 {_rows(d[2])} / 交遊 {_rows(d[3])}")

    print("\n[3] 专题页 Q1~Q9")
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

    print("\n[4] 空输入 / 异常输入")
    q2_bad = call("/Q2_run", quad, "99999999", "双向")
    check("Q2 查不存在的人给提示", "未找到" in str(q2_bad[0]), str(q2_bad[0])[:40])
    q2_empty = call("/Q2_run", quad, "", "双向")
    check("Q2 空 pid 给提示", "personid" in str(q2_empty[0]), str(q2_empty[0])[:40])
    d_empty = call("/detail_load", "", quad, db)
    check("详情空 pid 给提示", "personid" in d_empty[0], d_empty[0][:40])

    print("\n[5] 导出")
    call("/search_query", args.name, "", "全部", "", "", "", "", "", "",
         False, False, False, False, 200, 19, quad)
    e = call("/export_run", ["CSV"], False, "50")
    check("导出页出文件", bool(e[1]), str(e[0])[:60].replace("\n", " "))
    e1 = call("/Q1_export", quad, args.pid)
    check("Q1 导出档案", bool(e1[1]), str(e1[0])[:60].replace("\n", " "))

    print(f"\n结果：PASS {ok}　FAIL {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
