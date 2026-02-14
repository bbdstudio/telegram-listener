import os
import asyncio
from flask import Flask, request
from telethon import TelegramClient, events
import requests

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
channel_id = int(os.getenv("CHANNEL_ID"))
webhook = os.getenv("WEBHOOK_URL")

app = Flask(__name__)
client = TelegramClient("session", api_id, api_hash)

loop = asyncio.get_event_loop()

@app.route("/")
def home():
    return '''
        <h2>Login Telegram</h2>
        <form method="post" action="/login">
            Telefone: <input name="phone"><br><br>
            <button type="submit">Enviar Código</button>
        </form>
    '''

@app.route("/login", methods=["POST"])
def login():
    phone = request.form["phone"]
    loop.run_until_complete(client.connect())
    loop.run_until_complete(client.send_code_request(phone))
    return '''
        <h2>Digite o código recebido</h2>
        <form method="post" action="/code">
            Telefone: <input name="phone"><br>
            Código: <input name="code"><br><br>
            <button type="submit">Confirmar</button>
        </form>
    '''

@app.route("/code", methods=["POST"])
def code():
    phone = request.form["phone"]
    code = request.form["code"]
    loop.run_until_complete(client.sign_in(phone, code))

    @client.on(events.NewMessage(chats=channel_id))
    async def handler(event):
        data = {
            "text": event.message.text,
            "message_id": event.message.id
        }
        requests.post(webhook, json=data)

    loop.create_task(client.run_until_disconnected())

    return "<h3>Login feito com sucesso! Listener ativo.</h3>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
