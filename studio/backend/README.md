# Studio Backend

`studio/backend/` 是 TwinMarket Studio 的 FastAPI 控制面：Run Registry、独立 Worker、RuntimeEvent 查询/SSE 和结果查询都在此目录。它不会在 HTTP 请求中执行模拟。

前端运行界面位于 `studio/frontend/`；模拟埋点的框架无关实现位于仓库根目录 `runtime/`。启动入口为 `uvicorn studio.backend.app:app --host 127.0.0.1 --port 8766`。
