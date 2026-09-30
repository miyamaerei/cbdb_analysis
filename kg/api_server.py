#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CBDB 知识图谱 HTTP 接口（独立服务，端口 8799）

职责：把 kg_backend（检索 / 朝代 / 图谱清单）以 REST 形式暴露给前端，
从而把原先绑死在 Gradio 上的逻辑层接到 web 前端，统一进 Vue 查询台。

设计要点
--------
  * 仅依赖标准库 + kg_backend（kg_backend 本身只在函数内部懒加载 owlready2/zhconv），
    不污染 web/server.py 的零依赖纯净性。
  * 生产由 web/server.py 反向代理 /api/kg/* 到本服务（同源，前端无需跨域）。
  * 开发态由 web/frontend/vite.config.js 把 /api/kg 代理到本服务。

启动
----
  # 用托管 venv（含 zhconv / owlready2）
  python kg/api_server.py --port 8799
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# kg_backend 在 import 时就绪（仅标准库依赖；owlready2/zhconv 在其内部懒加载）
import kg_backend  # noqa: E402
# 专题调度层：复用 kg_query 纯函数，不依赖 Gradio
import topic_dispatcher  # noqa: E402
import kg_graph  # noqa: E402  (GraphIndex：专题查询底座)

DEFAULT_PORT = 8799
DEFAULT_HOST = "127.0.0.1"

# search_persons 的全部关键字 + 默认值（前端只给有的字段，其余走默认）
_SEARCH_DEFAULTS = {
    "dy": 19,
    "name": "",
    "pinyin": "",
    "gender": "全部",
    "birth_from": None,
    "birth_to": None,
    "death_from": None,
    "death_to": None,
    "index_from": None,
    "index_to": None,
    "jinshi_only": False,
    "official_only": False,
    "match_alt": False,
    "include_neighbors": False,
    "limit": 200,
    "order_by": "personid",
    "desc": False,
}


def _coerce(params: dict) -> dict:
    """把前端给的 JSON 字段收敛成 search_persons 的关键字（含类型安全）。"""
    out = {}
    for k, default in _SEARCH_DEFAULTS.items():
        v = params.get(k, default)
        # 数字类：空串 / None → 默认（None 对年份表示「未填」，避免 col>=0 AND col<=0）
        if k in ("birth_from", "birth_to", "death_from", "death_to",
                 "index_from", "index_to", "dy", "limit"):
            try:
                out[k] = int(v) if v not in (None, "", "null") else default
            except (TypeError, ValueError):
                out[k] = default
        elif isinstance(default, bool):
            out[k] = bool(v)
        else:
            out[k] = v if v is not None else default
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "CBDB-KG/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ------------------------------------------------------------ 响应
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        elif not isinstance(body, (bytes, bytearray)):
            body = str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, obj)

    def _err(self, code, msg):
        self._json(code, {"error": msg})

    # ------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        seg = [unquote(s) for s in u.path.split("/") if s]
        qs = parse_qs(u.query)
        try:
            if len(seg) < 2 or seg[0] != "api" or seg[1] != "kg":
                return self._err(404, "未知接口")
            if seg[2:] == ["health"] or len(seg) == 2:
                return self._json(200, {
                    "ok": True,
                    "service": "cbdb-kg",
                    "source_db": os.path.basename(kg_backend.DEFAULT_DB),
                    "quadstores": len(kg_backend.quadstores()),
                })
            if seg[2] == "dynasties":
                return self._json(200, {
                    "dynasties": [
                        {"label": label, "dy": dy}
                        for label, dy in kg_backend.dynasty_choices()
                    ]
                })
            if seg[2] == "quads":
                return self._json(200, {
                    "quads": [
                        {"label": q[0], "path": q[1]}
                        for q in kg_backend.quad_choices()
                        if q[1]
                    ]
                })
            if seg[2] == "topics":
                return self._json(200, {"topics": topic_dispatcher.TOPIC_SCHEMA})
            if seg[2] == "person" and len(seg) >= 4:
                pid = seg[3]
                try:
                    data, note, source = kg_backend.person_detail_auto(
                        kg_backend.DEFAULT_DB, pid)
                except Exception as e:  # noqa: BLE001
                    return self._err(500, f"{type(e).__name__}: {e}")
                if data is None:
                    return self._json(200, {"error": note})
                sections = {}
                for key in ("kin", "assoc", "tenure", "entry", "addr",
                            "status", "text", "source"):
                    sections[key] = {
                        "headers": kg_backend.SECTION_HEADERS[key],
                        "rows": data.get(key, []),
                    }
                return self._json(200, {
                    "personid": data["basic"]["personid"],
                    "basic": data["basic"],
                    "alts": data.get("alts", []),
                    "labels": data.get("labels", []),
                    "sections": sections,
                    "source": source,
                    "note": note,
                })
            return self._err(404, "未知接口")
        except Exception as e:  # noqa: BLE001
            return self._err(500, f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------ POST
    def do_POST(self):
        u = urlparse(self.path)
        seg = [unquote(s) for s in u.path.split("/") if s]
        if len(seg) < 3 or seg[0] != "api" or seg[1] != "kg":
            return self._err(404, "未知接口")
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            params = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            params = {}
        try:
            if seg[2] == "search":
                kw = _coerce(params)
                rows, total, note, used = kg_backend.search_persons_fallback(**kw)
                return self._json(200, {
                    "headers": kg_backend.RESULT_HEADERS,
                    "rows": rows,
                    "total": total,
                    "dyn_name": kg_backend.dynasty_name(kw["dy"]),
                    "truncated": total > kw["limit"],
                    # 回退链说明（原名 0 命中时自动改用别名/字号匹配）
                    "note": note,
                    "used_name": used,
                })
            if seg[2] == "topic":
                key = params.get("key")
                quad = params.get("quad")
                vals = params.get("vals") or []
                if not quad:
                    return self._err(400, "请选择一个知识图谱（quad）")
                try:
                    g = kg_graph.get_index(quad)
                except Exception as e:  # noqa: BLE001
                    return self._err(400, f"图谱加载失败：{type(e).__name__}: {e}")
                try:
                    res = topic_dispatcher.run_topic(key, g, vals)
                except Exception as e:  # noqa: BLE001
                    return self._err(400, f"{type(e).__name__}: {e}")
                return self._json(200, res)
            if seg[2] == "export":
                kw = _coerce(params)
                fmt = (params.get("format") or "csv").lower()
                rows, total, note, used = kg_backend.search_persons_fallback(**kw)
                import csv as _csv
                import io as _io
                buf = _io.StringIO()
                w = _csv.writer(buf)
                w.writerow(kg_backend.RESULT_HEADERS)
                w.writerows(rows)
                body = buf.getvalue().encode("utf-8-sig")
                # ⚠️ 文件名必须 ASCII（HTTP 头按 latin-1 编码，中文会抛 UnicodeEncodeError）
                fname = f"cbdb_kg_dy{kw['dy']}_{total}.csv"
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition",
                                 f"attachment; filename=\"{fname}\"")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if seg[2] == "build":
                dy = params.get("dy", 19)
                limit = params.get("limit", 0)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                # ⚠️ 必须显式关闭连接：请求是 HTTP/1.1，默认 keep-alive，
                # 不关的话上游永远不发 EOF，代理的分块循环读不到结束 → 前端流一直挂起。
                self.close_connection = True

                def _evt(obj):
                    chunk = ("data: " + json.dumps(obj, ensure_ascii=False, default=str)
                             + "\n\n").encode("utf-8")
                    try:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    except Exception:
                        pass

                try:
                    for buf in kg_backend.run_etl(kg_backend.DEFAULT_DB, dy, limit):
                        _evt({"log": buf})
                    _evt({"done": True})
                except Exception as e:  # noqa: BLE001
                    _evt({"error": f"{type(e).__name__}: {e}"})
                return
            return self._err(404, "未知接口")
        except Exception as e:  # noqa: BLE001
            return self._err(400, f"{type(e).__name__}: {e}")

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")


def main():
    ap = argparse.ArgumentParser(description="CBDB 知识图谱 API 服务")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default=DEFAULT_HOST)
    a = ap.parse_args()

    # 启动自检：kg_backend 能否导入、源库是否存在
    src = os.path.abspath(kg_backend.DEFAULT_DB)
    print(f"CBDB 知识图谱 API: http://{a.host}:{a.port}/")
    print(f"源库: {src}  （存在: {os.path.isfile(src)}）")
    if not os.path.isfile(src):
        print("警告：源库不存在，检索将失败", file=sys.stderr)
    print(f"可用图谱: {len(kg_backend.quadstores())} 个")
    print("提示：生产由 web/server.py 代理 /api/kg/*；开发由 vite 代理")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
