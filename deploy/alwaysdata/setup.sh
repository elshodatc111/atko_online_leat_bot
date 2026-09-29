#!/bin/bash
# =====================================================================
#  ATKO Lead platforma — alwaysdata serveriga o'rnatish / yangilash
#  SSH'da:  bash ~/atko_bot/deploy/alwaysdata/setup.sh
#  Bir necha marta ishga tushirish xavfsiz (ma'lumotlar va .env saqlanadi).
# =====================================================================
set -e
APP_DIR="$HOME/atko_bot"
ACCOUNT="${ATKO_ACCOUNT:-$USER}"
SITE_URL="https://${ACCOUNT}.alwaysdata.net"
cd "$APP_DIR"

echo "==> [1/5] Python 3.14 virtual muhit"
if [ ! -x .venv/bin/python ]; then
  if command -v python3.14 >/dev/null 2>&1; then
    python3.14 -m venv .venv
  else
    PYTHON_VERSION=3.14 python -m venv .venv
  fi
fi
PYV=$(.venv/bin/python -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "    Python: $PYV"
if [ "$PYV" != "3.14" ]; then
  echo "    XATO: Python 3.14 kerak. Admin panel → Environment → Python → 3.14 ni tanlang, so'ng:"
  echo "    rm -rf $APP_DIR/.venv && bash $0"
  exit 1
fi

echo "==> [2/5] Kutubxonalar (1-2 daqiqa)"
.venv/bin/python -m pip install --upgrade pip -q --no-cache-dir
.venv/bin/python -m pip install -r requirements.txt -q --no-cache-dir

echo "==> [3/5] Papkalar"
mkdir -p data
find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> [4/5] .env (server rejimi)"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    DIQQAT: .env yangi yaratildi — BOT_TOKEN, ADMIN_TG_IDS, OPENAI_API_KEY ni yozing: nano $APP_DIR/.env"
fi
set_kv() {  # .env da KEY=VALUE ni o'rnatadi (bor bo'lsa almashtiradi, yo'q bo'lsa qo'shadi)
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
rand() { head -c 64 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "$1"; }
set_kv BOT_MODE webhook
set_kv WEBHOOK_BASE_URL "$SITE_URL"
set_kv PANEL_URL "$SITE_URL"
set_kv HOST ""
set_kv PORT ""
set_kv DATA_DIR ""
grep -q "^WEBHOOK_SECRET=..*" .env || set_kv WEBHOOK_SECRET "$(rand 32)"
if ! grep -q "^SECRET_KEY=..*" .env || grep -q "^SECRET_KEY=bu-yerga" .env; then set_kv SECRET_KEY "$(rand 48)"; fi
chmod 600 .env
grep -q "^BOT_TOKEN=[0-9]\+:" .env || echo "    DIQQAT: .env da BOT_TOKEN yo'q yoki noto'g'ri!"
grep -q "^ADMIN_TG_IDS=[0-9]" .env || echo "    DIQQAT: .env da ADMIN_TG_IDS yo'q!"

echo "==> [5/5] Tekshiruv"
.venv/bin/python -c "import app.main" >/dev/null 2>&1 && echo "    Kod yuklandi: OK" || { .venv/bin/python -c "import app.main"; exit 1; }
du -sh "$APP_DIR" 2>/dev/null | awk '{print "    Egallagan joy: "$1}'

cat <<EOF

======================================================================
 TAYYOR. Endi admin panelda (admin.alwaysdata.com):

 1) Web → Sites → (eski saytni tahrirlang yoki Add a site):
      Addresses ........ ${ACCOUNT}.alwaysdata.net
      Type ............. User program
      Command .......... $APP_DIR/.venv/bin/python run.py
      Working directory  $APP_DIR
      Environment ...... MALLOC_ARENA_MAX=2
    SSL bo'limida: "Force HTTPS" ni yoqing.  Saqlang.

 2) Advanced → Scheduled tasks → Add:
      Type: Access an URL   URL: ${SITE_URL}/health
      Frequency: har 10 daqiqada  (sayt uxlab qolmasligi uchun)

 3) Tekshiring: ${SITE_URL}/health  →  {"ok":true}
    Panel:      ${SITE_URL}
    Payme Endpoint: ${SITE_URL}/payme

 Yangilash: cd $APP_DIR && git pull && bash deploy/alwaysdata/setup.sh
            so'ng Web → Sites → saytni «Restart» qiling.
 Loglar:   ~/admin/logs/sites/
======================================================================
EOF
