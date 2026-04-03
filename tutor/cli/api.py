"""CLI commands for running the Web API server."""

import typer
import uvicorn

app = typer.Typer(
    name="api",
    help="启动 Web API 服务器 (FastAPI + SSE)",
    no_args_is_help=True,
)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8000, "--port", "-p", help="监听端口"),
    reload: bool = typer.Option(False, "--reload", help="开发模式自动重载"),
    workers: int = typer.Option(1, "--workers", "-w", help="工作进程数 (生产环境)"),
):
    """
    启动 TUTOR Web API 服务器

    功能：
    - 提供 RESTful API 触发工作流运行
    - Server-Sent Events (SSE) 实时推送进度
    - 健康检查端点

    示例：
        tutor api serve --port 8000
        tutor api serve --host 0.0.0.0 --reload
    """
    from tutor.api.main import app as fastapi_app

    typer.echo(f"🚀 启动 TUTOR API 服务器 http://{host}:{port}")
    typer.echo("  端点：")
    typer.echo("    POST /api/v1/workflows/{name}/run")
    typer.echo("    GET  /api/v1/workflows/{run_id}")
    typer.echo("    GET  /api/v1/events (SSE)")
    typer.echo("    GET  /health")

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level="info",
    )


@app.command()
def openapi(
    output: str = typer.Option(None, "--output", "-o", help="输出 OpenAPI JSON 文件路径"),
):
    """生成 OpenAPI 规范 (JSON)"""
    from tutor.api.main import app as fastapi_app
    import json

    openapi_schema = fastapi_app.openapi()
    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
        typer.echo(f"✅ OpenAPI schema saved to {output}")
    else:
        typer.echo(json.dumps(openapi_schema, indent=2, ensure_ascii=False))
