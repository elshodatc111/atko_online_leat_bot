"""FastAPI ilovasi: veb-panel + Telegram bot + fon vazifalari — hammasi bitta jarayonda."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import config
from .db import init_db
from .seed import seed
from .services import scheduler, settings, worktime
from .web.deps import WEB_DIR, LoginRequired, render

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("atko")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .bot.setup import start_bot, stop_bot

    await init_db()
    await seed()
    await settings.load()
    await worktime.reload_holidays()
    await start_bot()
    scheduler.start_all()
    log.info("ATKO panel ishga tushdi: %s", config.PANEL_URL)
    yield
    await scheduler.stop_all()
    await stop_bot()


app = FastAPI(title="ATKO Lead Platform", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, session_cookie="atko_session",
                   max_age=60 * 60 * 24 * 14, same_site="lax", https_only=config.PANEL_URL.startswith("https"))
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, exc: LoginRequired):
    if request.url.path.startswith("/api/") or request.headers.get("hx-request"):
        return JSONResponse({"ok": False, "error": "Avtorizatsiya kerak"}, status_code=401)
    return RedirectResponse("/login", 303)


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"ok": False, "error": exc.detail}, status_code=exc.status_code)
    resp = render(request, "error.html", None, code=exc.status_code, detail=exc.detail)
    resp.status_code = exc.status_code
    return resp


@app.post("/tg/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    from aiogram.types import Update

    from .bot.instance import get_bot
    from .bot.setup import dp

    if secret != config.WEBHOOK_SECRET:
        return JSONResponse({"ok": False}, status_code=403)
    bot = get_bot()
    update = Update.model_validate(await request.json(), context={"bot": bot})
    # AI javobi bir necha soniya olishi mumkin — Telegramga darhol javob qaytarib, fonda qayta ishlaymiz
    task = asyncio.create_task(dp.feed_update(bot, update))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return {"ok": True}


_bg_tasks: set = set()


@app.get("/health")
async def health():
    return {"ok": True}


from .web.routes import admin, auth, chats, content, dashboard, leads  # noqa: E402

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(chats.router)
app.include_router(leads.router)
app.include_router(admin.router)
app.include_router(content.router)
