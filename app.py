import os
import logging
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SendCodeUnavailableError,
    FloodWaitError,
)
import requests

# =========================
# LOG CONFIG
# =========================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================
# ENV VARIABLES
# =========================

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

WEBHOOK_USER = os.getenv("WEBHOOK_USER", "")
WEBHOOK_PASS = os.getenv("WEBHOOK_PASS", "")

if not all([API_ID, API_HASH, CHANNEL_ID, WEBHOOK_URL]):
    raise ValueError(
        "Configure: API_ID, API_HASH, CHANNEL_ID, WEBHOOK_URL"
    )

if not all([WEBHOOK_USER, WEBHOOK_PASS]):
    raise ValueError(
        "Configure: WEBHOOK_USER e WEBHOOK_PASS para Basic Auth"
    )

# =========================
# TELEGRAM CLIENT
# =========================

client = TelegramClient("/data/session", API_ID, API_HASH)
listener_started = False

app = FastAPI()

# =========================
# STARTUP / SHUTDOWN
# =========================

@app.on_event("startup")
async def startup():
    await client.connect()
    logger.info("✅ Conectado ao Telegram")

    if await client.is_user_authorized():
        logger.info("✅ Usuário autorizado")
        await start_listener()

@app.on_event("shutdown")
async def shutdown():
    if client.is_connected():
        await client.disconnect()
        logger.info("✅ Desconectado")

# =========================
# LISTENER
# =========================

async def start_listener():
    global listener_started

    if listener_started:
        return

    @client.on(events.NewMessage(chats=CHANNEL_ID))
    async def handler(event):
        data = {
            "text": event.message.text or "",
            "message_id": event.message.id,
            "date": str(event.message.date),
            "channel_id": CHANNEL_ID
        }

        try:
            response = requests.post(
                WEBHOOK_URL,
                json=data,
                auth=(WEBHOOK_USER, WEBHOOK_PASS),  # 🔐 Basic Auth
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"✅ Webhook enviado: msg {event.message.id}")
            else:
                logger.error(
                    f"❌ Webhook erro {response.status_code}: {response.text}"
                )

        except Exception as e:
            logger.error(f"❌ Erro webhook: {e}")

    listener_started = True
    logger.info("✅ Listener ativo")

# =========================
# HTML TEMPLATE
# =========================

def page(content):
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Telegram Listener</title>
<style>
body{{font-family:Arial;max-width:500px;margin:50px auto;padding:20px;background:#f5f5f5}}
.box{{background:#fff;padding:30px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}}
input{{width:100%;padding:10px;margin:10px 0;border:1px solid #ddd;border-radius:5px;box-sizing:border-box}}
button{{width:100%;padding:12px;background:#0088cc;color:#fff;border:none;border-radius:5px;cursor:pointer;font-size:16px}}
button:hover{{background:#006699}}
.success{{color:#28a745}}
.error{{color:#dc3545}}
a{{color:#0088cc;text-decoration:none}}
</style>
</head>
<body>
<div class="box">
{content}
</div>
</body>
</html>"""

# =========================
# ROUTES
# =========================

@app.get("/", response_class=HTMLResponse)
async def home():
    if await client.is_user_authorized():
        return page(
            f'<h2 class="success">✅ Conectado</h2>'
            f'<p>Monitorando canal {CHANNEL_ID}</p>'
            f'<p><a href="/health">Status</a></p>'
        )

    return page('''
        <h2>🔐 Login</h2>
        <form action="/send_code" method="post">
            <input type="tel" name="phone" placeholder="+5511999999999" required>
            <button>Enviar Código</button>
        </form>
    ''')

@app.post("/send_code", response_class=HTMLResponse)
async def send_code(phone: str = Form(...)):
    phone = phone.strip()

    try:
        await client.send_code_request(phone)

        return page(f'''
            <h2>📱 Código Enviado</h2>
            <form action="/verify_code" method="post">
                <input type="hidden" name="phone" value="{phone}">
                <input type="text" name="code" placeholder="12345" required autofocus>
                <button>Verificar</button>
            </form>
        ''')

    except PhoneNumberInvalidError:
        return page('<h3 class="error">❌ Número inválido</h3><a href="/">Voltar</a>')

    except SendCodeUnavailableError:
        return page('<h3 class="error">⚠️ Muitas tentativas. Aguarde.</h3><a href="/">Voltar</a>')

    except FloodWaitError as e:
        return page(f'<h3 class="error">⏱️ Aguarde {e.seconds//60} minutos</h3><a href="/">Voltar</a>')

    except Exception as e:
        return page(f'<h3 class="error">❌ {e}</h3><a href="/">Voltar</a>')

@app.post("/verify_code", response_class=HTMLResponse)
async def verify_code(phone: str = Form(...), code: str = Form(...)):
    try:
        await client.sign_in(phone=phone.strip(), code=code.strip())
        await start_listener()
        return page('<h2 class="success">✅ Login OK!</h2><a href="/">Status</a>')

    except PhoneCodeInvalidError:
        return page('<h3 class="error">❌ Código inválido</h3><a href="/">Voltar</a>')

    except SessionPasswordNeededError:
        return page(f'''
            <h2>🔒 Senha 2FA</h2>
            <form action="/verify_password" method="post">
                <input type="password" name="password" placeholder="Senha" required autofocus>
                <button>Confirmar</button>
            </form>
        ''')

    except Exception as e:
        return page(f'<h3 class="error">❌ {e}</h3><a href="/">Voltar</a>')

@app.post("/verify_password", response_class=HTMLResponse)
async def verify_password(password: str = Form(...)):
    try:
        await client.sign_in(password=password.strip())
        await start_listener()
        return page('<h2 class="success">✅ Login 2FA OK!</h2><a href="/">Status</a>')

    except Exception as e:
        return page(f'<h3 class="error">❌ {e}</h3><a href="/">Voltar</a>')

@app.get("/health")
async def health():
    try:
        return {
            "status": "healthy" if await client.is_user_authorized() else "degraded",
            "connected": client.is_connected(),
            "authorized": await client.is_user_authorized(),
            "listener": listener_started,
            "channel": CHANNEL_ID
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
