from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import threading
import json
from highrise import BaseBot
from highrise.models import SessionMetadata
import datetime
from config import *

app = FastAPI()

# Allow cross-origin access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can specify allowed origins here, or use "*" for all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.websocket_server = None  # Placeholder for the WebSocket server
        self.active_connections = {}

    async def on_start(self: BaseBot, session_metadata: SessionMetadata) -> None:
        print("Bot is live!")

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            print("WebSocket client connected")

            self.active_connections[websocket] = None  # Store connection
            
            while True:
                try:
                    data = await websocket.receive_json()
                    if data.get("action") == "fetch_conversations":
                        conversations = await self.fetch_conversations()
                        await websocket.send_json({"conversations": conversations})
                    elif data.get("action") == "fetch_messages":
                        conversation_id = data.get("conversation_id")
                        messages = await self.fetch_messages(conversation_id)
                        await websocket.send_json({"messages": messages})
                    elif data.get("action") == "get_user_info":
                        user_id = data.get("user_id")
                        username = await self.get_user_info(user_id)
                        await websocket.send_json({"username": username})
                    elif data.get("action") == "send_message_from_web":
                        conversation_id = data.get("conversation_id")
                        message = data.get("message")
                        await self.send_message_from_web(conversation_id, message)
                except Exception as e:
                    print(f"WebSocket error: {e}")
                    break
            del self.active_connections[websocket]  # Remove connection after disconnect
            print("WebSocket client disconnected")

        # Start FastAPI server in a separate thread
        def start_server():
            import uvicorn
            uvicorn.run(app, host="0.0.0.0", port=8000)

        self.websocket_server = threading.Thread(target=start_server, daemon=True)
        self.websocket_server.start()

    async def on_message(self: BaseBot, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        resp = await self.webapi.get_user(user_id)
        usernme = resp.user.username

        conversation = await self.highrise.get_messages(conversation_id)
        message_content = conversation.messages[0].content

        await self.send_notification(conversation_id, user_id, usernme, message_content)

    async def fetch_conversations(self):
        """Fetch conversations from Highrise API and format for frontend."""
        conversations = await self.highrise.get_conversations()

        # Serialize conversations into JSON-compatible format
        serialized_conversations = [
            {
                "id": conversation.id,
                # Add user info to the conversation's details
                "user_info": await self.extract_user_info(conversation.last_message.conversation_id),
                "last_message": {
                    "message_id": conversation.last_message.message_id,
                    "conversation_id": conversation.last_message.conversation_id,
                    "createdAt": conversation.last_message.createdAt.isoformat() 
                    if isinstance(conversation.last_message.createdAt, datetime.datetime) else str(conversation.last_message.createdAt),
                    "content": conversation.last_message.content,
                    "sender_id": conversation.last_message.sender_id,
                    "category": conversation.last_message.category,
                } if conversation.last_message else None,
                "muted": conversation.muted,
                "member_ids": conversation.member_ids,
                "name": conversation.name,
            }
            for conversation in conversations.conversations
        ]

        return serialized_conversations

    async def fetch_messages(self, conversation_id):
        """Fetch messages for a specific conversation."""
        messages = await self.highrise.get_messages(conversation_id)

        # Format and return messages
        return [
            {
                "message_id": message.message_id,
                "conversation_id": message.conversation_id,
                "content": message.content,
                "sender_id": message.sender_id,
                "sender_username": await self.get_user_info(message.sender_id),
                "createdAt": message.createdAt.isoformat()
            }
            for message in messages.messages
        ]
    
    async def get_user_info(self, user_id: str):
        """Fetch user information using webapi."""
        user_info = await self.webapi.get_user(user_id)
        return user_info.user.username  # Return the username from the response
    
    async def send_message_from_web(self, conversation_id: str, content: str):

        await self.highrise.send_message(conversation_id, content, "text", None, None)

    async def send_notification(self, conversation_id: str, user_id: str, username:str, message: str):

        notification_data = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "username": username,
            "message": message,
        }
        
        # Send notifications to all active WebSocket connections
        for websocket in list(self.active_connections):  # Convert set to list to avoid issues during iteration
            try:
                await websocket.send_text(json.dumps({"notification": notification_data}))
            except Exception as e:
                print(f"Failed to send notification to WebSocket: {e}")
                self.active_connections.remove(websocket)  # Remove WebSocket if it's broken

    async def extract_user_info(self, conversation_id):

        # Remove '1_on_1' prefix
        conversation_id = conversation_id.replace("1_on_1:", "")

        # Split by ':' and remove the botID
        parts = conversation_id.split(":")
        user_id = next(part for part in parts if part != config.botID)
        
        username = await self.get_user_info(user_id)  # Fetch username using the provided function
        if username:
            return {"id": user_id, "username": username}
        else:
            return None  # Return None if the format is invalid
