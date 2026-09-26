import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from web.api import ApiError, api_error_response, store
from web.api import router as api_router
from web.config import APP_VERSION, CLEANUP_INTERVAL_SECONDS
from web.routes import router as page_router

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    stop_cleanup = asyncio.Event()

    async def cleanup_loop():
        while True:
            try:
                await asyncio.wait_for(stop_cleanup.wait(), timeout=CLEANUP_INTERVAL_SECONDS)
                return
            except asyncio.TimeoutError:
                await run_in_threadpool(store.cleanup)

    await run_in_threadpool(store.cleanup)
    cleanup_task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        stop_cleanup.set()
        await cleanup_task
        await run_in_threadpool(store.cleanup)


app = FastAPI(
    title="Hidden Watermark",
    description="DWT + DCT 频域图片隐藏水印工具",
    version=APP_VERSION,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")
app.include_router(page_router)
app.include_router(api_router)


@app.exception_handler(ApiError)
async def handle_api_error(_request: Request, exc: ApiError):
    return api_error_response(exc)
