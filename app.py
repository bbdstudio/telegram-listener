import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SendCodeUnavailableError,
    FloodWaitError,
    RPCError
)
import requests

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================
# ENV VARIABLES
# =========================

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# Validação
if not all([API_ID, API_HASH, CHANNEL_ID, WEBHOOK_URL]):
    raise ValueError("Variáveis de ambiente obrigatórias não definidas!")

# =========================
# STATE MANAGEMENT
# =========================

class AppState:
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.listener_started: bool = False
        self.listener_task: Optional[asyncio.Task] = None
        self.phone_cache: dict = {}
    
    async def initialize(self):
        """Inicializa o cliente Telegram"""
        if self.client is None:
            # IMPORTANTE: Usa /data para persistência
            session_path = "/data/session"
            self.client = TelegramClient(session_path, API_ID, API_HASH)
            await self.client.connect()
            logger.info("Cliente Telegram conectado")
            
            # Se já está autorizado, inicia listener
            if await self.client.is_user_authorized():
                await self.start_listener()
    
    async def cleanup(self):
        """Limpa recursos"""
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
        
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            logger.info("Cliente Telegram desconectado")
    
    async def start_listener(self):
        """Inicia o listener de mensagens"""
        if self.listener_started:
            logger.warning("Listener já está ativo")
            return
        
        self.listener_started = True
        
        @self.client.on(events.NewMessage(chats=CHANNEL_ID))
        async def handler(event):
            message_data = {
                "text": event.message.text or "",
                "message_id": event.message.id,
                "date": str(event.message.date),
                "channel_id": CHANNEL_ID
            }
            
            try:
                response = requests.post(
                    WEBHOOK_URL, 
                    json=message_data, 
                    timeout=10
                )
                logger.info(f"Webhook chamado: {response.status_code}")
            except requests.RequestException as e:
                logger.error(f"Erro ao chamar webhook: {e}")
        
        # Mantém o cliente rodando
        self.listener_task = asyncio.create_task(self.client.run_until_disconnected())
        logger.info("Listener iniciado com sucesso")

# =========================
# APP LIFECYCLE
# =========================

state = AppState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação"""
    await state.initialize()
    yield
    await state.cleanup()

app = FastAPI(lifespan=lifespan)

# =========================
# HTML TEMPLATES
# =========================

def render_page(content: str, title: str = "Telegram Login") -> str:
    """Template base HTML"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 500px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            input {{
                width: 100%;
                padding: 10px;
                margin: 10px 0;
                border: 1px solid #ddd;
                border-radius: 5px;
                box-sizing: border-box;
            }}
            button {{
                width: 100%;
                padding: 12px;
                background: #0088cc;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
            }}
            button:hover {{
                background: #006699;
            }}
            .success {{ color: #28a745; }}
            .error {{ color: #dc3545; }}
            .warning {{ color: #ffc107; }}
            a {{
                color: #0088cc;
                text-decoration: none;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            {content}
        </div>
    </body>
    </html>
    """

# =========================
# ROUTES
# =========================

@app.get("/", response_class=HTMLResponse)
async def home():
    """Página inicial"""
    try:
        if await state.client.is_user_authorized():
            content = """
                <h2 class="success">✅ Autenticado</h2>
                <p>O listener está ativo e monitorando o canal.</p>
                <p><strong>Canal ID:</strong> {}</p>
                <p><strong>Webhook:</strong> {}</p>
                <hr>
                <p><a href="/health">Ver status do sistema</a></p>
            """.format(CHANNEL_ID, WEBHOOK_URL[:50] + "...")
            return render_page(content, "Status - Telegram")
        
        content = """
            <h2>🔐 Login Telegram</h2>
            <p>Digite seu número de telefone para receber o código:</p>
            <form action="/send_code" method="post">
                <input 
                    type="tel" 
                    name="phone" 
                    placeholder="+5511999999999"
                    pattern="\\+[0-9]{10,15}"
                    required
                />
                <button type="submit">Enviar Código</button>
            </form>
        """
        return render_page(content)
    
    except Exception as e:
        logger.error(f"Erro na home: {e}")
        raise HTTPException(status_code=500, detail="Erro interno")


@app.post("/send_code", response_class=HTMLResponse)
async def send_code(phone: str = Form(...)):
    """Envia código de verificação"""
    phone = phone.strip()
    
    # Valida formato básico
    if not phone.startswith('+') or len(phone) < 11:
        content = """
            <h3 class="error">❌ Número inválido</h3>
            <p>Use o formato: +5511999999999</p>
            <p><a href="/">← Voltar</a></p>
        """
        return render_page(content)
    
    try:
        if await state.client.is_user_authorized():
            content = '<h3 class="success">✅ Já autenticado</h3>'
            return render_page(content)
        
        await state.client.send_code_request(phone)
        
        # Salva telefone no cache
        state.phone_cache['last_phone'] = phone
        
        content = f"""
            <h2>📱 Código Enviado</h2>
            <p>Digite o código recebido no Telegram:</p>
            <form action="/verify_code" method="post">
                <input type="hidden" name="phone" value="{phone}"/>
                <input 
                    type="text" 
                    name="code" 
                    placeholder="12345"
                    maxlength="5"
                    pattern="[0-9]{{5}}"
                    required
                    autofocus
                />
                <button type="submit">Verificar</button>
            </form>
        """
        return render_page(content)
    
    except PhoneNumberInvalidError:
        content = """
            <h3 class="error">❌ Número inválido</h3>
            <p>Verifique o formato: +5511999999999</p>
            <p><a href="/">← Tentar novamente</a></p>
        """
        return render_page(content)
    
    except SendCodeUnavailableError:
        content = f"""
            <h3 class="warning">⚠️ Muitas tentativas</h3>
            <p>Você solicitou códigos recentemente. Aguarde alguns minutos.</p>
            <p>Se já recebeu o código, digite abaixo:</p>
            <form action="/verify_code" method="post">
                <input type="hidden" name="phone" value="{phone}"/>
                <input 
                    type="text" 
                    name="code" 
                    placeholder="12345"
                    required
                />
                <button type="submit">Verificar</button>
            </form>
            <p><a href="/">← Voltar</a></p>
        """
        return render_page(content)
    
    except FloodWaitError as e:
        wait_minutes = max(1, e.seconds // 60)
        content = f"""
            <h3 class="error">⏱️ Limite excedido</h3>
            <p>Aguarde <strong>{wait_minutes} minutos</strong> antes de tentar novamente.</p>
            <p><a href="/">← Voltar</a></p>
        """
        return render_page(content)
    
    except RPCError as e:
        logger.error(f"RPC Error: {e}")
        content = f"""
            <h3 class="error">❌ Erro do Telegram</h3>
            <p>{str(e)}</p>
            <p><a href="/">← Tentar novamente</a></p>
        """
        return render_page(content)
    
    except Exception as e:
        logger.exception(f"Erro inesperado em send_code: {e}")
        raise HTTPException(status_code=500, detail="Erro interno")


@app.post("/verify_code", response_class=HTMLResponse)
async def verify_code(phone: str = Form(...), code: str = Form(...)):
    """Verifica código de autenticação"""
    phone = phone.strip()
    code = code.strip()
    
    try:
        await state.client.sign_in(phone=phone, code=code)
        
        # Inicia o listener
        await state.start_listener()
        
        content = """
            <h2 class="success">✅ Login realizado!</h2>
            <p>O listener está ativo e monitorando mensagens.</p>
            <p><a href="/">Ver status</a></p>
        """
        return render_page(content, "Sucesso")
    
    except PhoneCodeInvalidError:
        content = f"""
            <h3 class="error">❌ Código inválido</h3>
            <p>Verifique o código e tente novamente.</p>
            <form action="/verify_code" method="post">
                <input type="hidden" name="phone" value="{phone}"/>
                <input 
                    type="text" 
                    name="code" 
                    placeholder="12345"
                    required
                    autofocus
                />
                <button type="submit">Tentar novamente</button>
            </form>
            <p><a href="/">← Voltar</a></p>
        """
        return render_page(content)
    
    except SessionPasswordNeededError:
        content = f"""
            <h2>🔒 Verificação em 2 etapas</h2>
            <p>Digite sua senha do Telegram:</p>
            <form action="/verify_password" method="post">
                <input type="hidden" name="phone" value="{phone}"/>
                <input 
                    type="password" 
                    name="password" 
                    placeholder="Senha 2FA"
                    required
                    autofocus
                />
                <button type="submit">Confirmar</button>
            </form>
        """
        return render_page(content)
    
    except Exception as e:
        logger.exception(f"Erro em verify_code: {e}")
        content = f"""
            <h3 class="error">❌ Erro: {str(e)}</h3>
            <p><a href="/">← Voltar</a></p>
        """
        return render_page(content)


@app.post("/verify_password", response_class=HTMLResponse)
async def verify_password(phone: str = Form(...), password: str = Form(...)):
    """Verifica senha 2FA"""
    try:
        await state.client.sign_in(password=password.strip())
        
        # Inicia o listener
        await state.start_listener()
        
        content = """
            <h2 class="success">✅ Login realizado com 2FA!</h2>
            <p>O listener está ativo e monitorando mensagens.</p>
            <p><a href="/">Ver status</a></p>
        """
        return render_page(content, "Sucesso")
    
    except Exception as e:
        logger.error(f"Erro 2FA: {e}")
        content = f"""
            <h3 class="error">❌ Senha incorreta</h3>
            <p>{str(e)}</p>
            <form action="/verify_password" method="post">
                <input type="hidden" name="phone" value="{phone}"/>
                <input 
                    type="password" 
                    name="password" 
                    placeholder="Senha 2FA"
                    required
                    autofocus
                />
                <button type="submit">Tentar novamente</button>
            </form>
            <p><a href="/">← Voltar</a></p>
        """
        return render_page(content)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        is_connected = state.client.is_connected() if state.client else False
        is_authorized = await state.client.is_user_authorized() if state.client else False
        
        return {
            "status": "healthy" if is_connected and is_authorized else "degraded",
            "telegram_connected": is_connected,
            "telegram_authorized": is_authorized,
            "listener_active": state.listener_started,
            "channel_id": CHANNEL_ID,
            "webhook_configured": bool(WEBHOOK_URL)
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }
