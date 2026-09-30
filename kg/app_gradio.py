# -*- coding: utf-8 -*-
"""CBDB 知识图谱查询台 · 启动入口（瘦）。

只做三件事：解析命令行参数 → 调 app.build_ui() 组装界面 → launch。
所有页面代码在 `kg/app/` 下按页拆分，查询实现在 `kg/kg_query.py`。

启动：
    python kg/app_gradio.py [--port 7860] [--share]

文件结构见 `kg/app/README.md`。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gradio as gr                    # noqa: E402

from app import build_ui               # noqa: E402


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
    demo.launch(server_name=args.host, server_port=args.port, share=args.share,
                inbrowser=not args.no_browser, theme=gr.themes.Soft(),
                show_error=True)


if __name__ == "__main__":
    main()
