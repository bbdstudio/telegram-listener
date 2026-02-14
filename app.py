import os
import asyncio
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError
)
import requests

# =========================
# ENV VARIABLES
# =========================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
channel_id = int(os.getenv("CHANNEL_ID"))
webhook = os.getenv("WEBHOOK_URL")

# =========================
# APP + TELEGRAM CLIENT
# =========================

app = FastAPI()
client = TelegramClient("session", api_id, api_hash)

listener_started = False


# =========================
# HOME
# =========================

@app.get("/", response_class=HTMLResponse)
async def home():
    await client.connect()

    if await client.is_user_authorized():
        return HTMLResponse("""
        <h3>✅ Já autenticado! Listener ativo.</h3>
        """)

    return HTMLResponse("""
    <h2>Login Telegram</h2>
    <form action="/send_code" method="post">
        Telefone (com +55): <input name="phone"/>
        <button type="submit">Enviar Código</button>
    </form>
    """)


# =========================
# SEND CODE
# =========================

@app.post("/send_code")
async def send_code(phone: str = Form(...)):
    phone = phone.strip()

    await client.connect()

    if await client.is_user_authorized():
        return HTMLResponse("<h3>Já autenticado.</h3>")

    try:
        await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        return HTMLResponse("<h3>Número inválido. Use formato +5511999999999</h3>")
    except Exception as e:
        return HTMLResponse(f"<h3>Erro ao enviar código: {str(e)}</h3>")

    return HTMLResponse(f"""
    <h2>Digite o código recebido</h2>
    <form action="/verify_code" method="post">
        <input type="hidden" name="phone" value="{phone}"/>
        Código: <input name="code"/>
        <button type="submit">Confirmar</button>
    </form>
    """)


# =========================
# VERIFY CODE
# =========================

@app.post("/verify_code")
async def verify_code(phone: str = Form(...), code: str = Form(...)):
    phone = phone.strip()
    code = code.strip()

    try:
        await client.sign_in(phone=phone, code=code)
    except PhoneCodeInvalidError:
        return HTMLResponse("<h3>Código inválido. Tente novamente.</h3>")
    except SessionPasswordNeededError:
        return HTMLResponse(f"""
        <h2>Digite sua senha 2FA</h2>
        <form action="/verify_password" method="post">
            <input type="hidden" name="phone" value="{phone}"/>
            Senha: <input name="password"/>
            <button type="submit">Confirmar</button>
        </form>
        """)
    except Exception as e:
        return HTMLResponse(f"<h3>Erro: {str(e)}</h3>")

    await start_listener()
    return HTMLResponse("<h3>✅ Login realizado! Listener ativo.</h3>")


# =========================
# VERIFY 2FA PASSWORD
# =========================

@app.post("/verify_password")
async def verify_password(password: str = Form(...)):
    try:
        await client.sign_in(password=password.strip())
    except Exception:
        return HTMLResponse("<h3>Senha incorreta.</h3>")

    await start_listener()
    return HTMLResponse("<h3>✅ Login realizado com 2FA! Listener ativo.</h3>")


# =========================
# LISTENER
# =========================

async def start_listener():
    global listener_started

    if listener_started:
        return

    listener_started = True

    @client.on(events.NewMessage(chats=channel_id))
    async def handler(event):
        data = {
            "text": event.message.text,
            "message_id": event.message.id,
            "date": str(event.message.date)
        }
        try:
            requests.post(webhook, json=data, timeout=10)
        except:
            pass

    asyncio.create_task(client.run_until_disconnected())
