"""
Inicia o servidor MCP via HTTP (SSE ou Streamable-HTTP).

Uso:
    python run_mcp_http.py              # streamable-http na porta 8765
    python run_mcp_http.py --sse        # SSE na porta 8765 (compatível com VS Code Copilot)
    python run_mcp_http.py --port 9000  # porta customizada
"""
from __future__ import annotations

import argparse

from src.mcp.server import mcp

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor MCP HTTP para o Copiloto Espacial")
    parser.add_argument("--sse", action="store_true", help="Usar transporte SSE (padrão: streamable-http)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (padrão: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Porta (padrão: 8765)")
    args = parser.parse_args()

    transport = "sse" if args.sse else "streamable-http"
    print(f"\n🚀 Iniciando MCP Copiloto Espacial")
    print(f"   Transporte : {transport}")
    print(f"   Endereço   : http://{args.host}:{args.port}")
    if transport == "sse":
        print(f"   URL SSE    : http://{args.host}:{args.port}/sse")
        print(f"\n   → Para VS Code Copilot (.vscode/mcp.json):")
        print(f'     "url": "http://{args.host}:{args.port}/sse"')
    else:
        print(f"   URL MCP    : http://{args.host}:{args.port}/mcp")
        print(f"\n   → Para clientes streamable-http:")
        print(f'     "url": "http://{args.host}:{args.port}/mcp"')
    print()

    mcp.run(
        transport=transport,
        host=args.host,
        port=args.port,
    )
