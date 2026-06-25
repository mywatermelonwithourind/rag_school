#!/usr/bin/env python3
"""
数据库连通性自检 — 读取 backend/.env，探测 MySQL + Milvus 是否可达。

用法（在 backend 目录）:
    python scripts/check_connectivity.py

退出码: 0=全部通过, 1=至少一项失败
"""

from __future__ import annotations

import sys


def main() -> int:
    from app.core.config import get_settings
    from app.core.database import ping_mysql

    settings = get_settings()
    ok = True

    print("=== RAG 数据库连通性自检 ===")
    print(f"读取配置: backend/.env (RAG_* 前缀)\n")

    # HOST 提醒
    if settings.mysql_host in ("127.0.0.1", "localhost") or settings.milvus_host in (
        "127.0.0.1",
        "localhost",
    ):
        print(
            "⚠️  当前 HOST 含 127.0.0.1/localhost。"
            "若数据库部署在远程服务器，请先把 RAG_MYSQL_HOST / RAG_MILVUS_HOST 改成服务器 IP。\n"
        )

    # MySQL
    target = f"{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    print(f"MySQL  {target} ... ", end="", flush=True)
    try:
        mysql_ok = ping_mysql()
        print("OK" if mysql_ok else "FAIL")
        if not mysql_ok:
            ok = False
    except Exception as exc:
        print(f"FAIL ({exc})")
        ok = False

    # Milvus
    mv_target = f"{settings.milvus_host}:{settings.milvus_port}"
    print(f"Milvus {mv_target} ... ", end="", flush=True)
    try:
        from pymilvus import connections

        connections.connect(
            alias="rag_check",
            host=settings.milvus_host,
            port=str(settings.milvus_port),
            timeout=10,
        )
        connections.disconnect("rag_check")
        print("OK")
    except Exception as exc:
        print(f"FAIL ({exc})")
        ok = False

    print()
    if ok:
        print("✅ 全部通过，可以启动后端: uvicorn app.main:app --reload --port 8000")
        return 0

    print("❌ 连通失败。请检查: HOST 是否为服务器 IP、防火墙端口、密码、容器是否 healthy")
    print("   详见 docs/DEPLOY.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())
