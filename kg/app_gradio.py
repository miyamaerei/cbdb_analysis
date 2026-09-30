# -*- coding: utf-8 -*-
"""CBDB 知识图谱查询台 · 启动入口（瘦）。

只做三件事：解析命令行参数 → 调 app.build_ui() 组装界面 → launch。
所有页面代码在 `kg/app/` 下按页拆分，查询实现在 `kg/kg_query.py`。

启动：
    python kg/app_gradio.py [--port 7860] [--share]

文件结构见 `kg/app/README.md`。
"""
import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---- 依赖自检：缺包时给出可操作的提示，而不是裸 ModuleNotFoundError ----
# 最常见的坑：装依赖用的 python 和运行本脚本的 python 不是同一个解释器。
_MISSING = [m for m in ("gradio", "owlready2", "zhconv")
            if importlib.util.find_spec(m) is None]
if _MISSING:
    sys.exit(
        f"[依赖缺失] 当前解释器缺少：{', '.join(_MISSING)}\n"
        f"  当前 python：{sys.executable}\n"
        "  常见原因：「运行用的 python」不是「装依赖的那个 python」。\n"
        "  解决办法：\n"
        "    1) 先在仓库根目录装依赖：  pip install -r requirements.txt\n"
        "    2) 或直接用装了依赖的解释器运行：\n"
        "         Windows    : <venv>\\Scripts\\python.exe kg\\app_gradio.py --port 7860\n"
        "         macOS/Linux: <venv>/bin/python kg/app_gradio.py --port 7860\n"
        "  查当前解释器路径： python -c \"import sys; print(sys.executable)\"\n"
    )

import gradio as gr                    # noqa: E402

from app import build_ui               # noqa: E402
from app.theme import CSS as KG_CSS    # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--share", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    demo = build_ui()
    demo.queue()
    print(f"CBDB KG 查询台: http://{args.host}:{args.port}")
    # ⚠️ Gradio 6 的 css 只能给 launch（Blocks 已移除该参数）；
    # 另在 build_ui() 里用 gr.HTML 注入了一份，两条路互为兜底。
    demo.launch(server_name=args.host, server_port=args.port, share=args.share,
                inbrowser=not args.no_browser, theme=gr.themes.Soft(),
                css=KG_CSS, show_error=True)


if __name__ == "__main__":
    main()
