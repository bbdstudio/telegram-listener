import os
import requests
from telethon import TelegramClient, events

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
channel_id = int(os.getenv("CHANNEL_ID"))
webhook = os.getenv("WEBHOOK_URL")
phone = os.getenv("PHONE_NUMBER")

client = TelegramClient('session', api_id, api_hash)

async def main():
    await client.start(phone=phone)
    print("Escutando canal...")

    @client.on(events.NewMessage(chats=channel_id))
    async def handler(event):
        data = {
            "text": event.message.text,
            "message_id": event.message.id,
            "date": str(event.message.date)
        }
        requests.post(webhook, json=data)

    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())
