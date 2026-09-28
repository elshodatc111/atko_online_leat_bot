"""Ishga tushirish: python run.py"""
import uvicorn

from app.config import config

if __name__ == "__main__":
    # Muhim: workers=1 — bot, WebSocket va fon vazifalari bitta jarayonda ishlaydi
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, workers=1, proxy_headers=True,
                forwarded_allow_ips="*", log_level="info")
