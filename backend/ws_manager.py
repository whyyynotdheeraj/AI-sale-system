from typing import Dict, List
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Maps customer_id (int) to their WebSocket connection
        self.active_customers: Dict[int, WebSocket] = {}
        # List of connected admin dashboard WebSockets
        self.active_admins: List[WebSocket] = []

    async def connect_customer(self, websocket: WebSocket, customer_id: int):
        await websocket.accept()
        self.active_customers[customer_id] = websocket

    def disconnect_customer(self, customer_id: int):
        if customer_id in self.active_customers:
            del self.active_customers[customer_id]

    async def connect_admin(self, websocket: WebSocket):
        await websocket.accept()
        self.active_admins.append(websocket)

    def disconnect_admin(self, websocket: WebSocket):
        if websocket in self.active_admins:
            self.active_admins.remove(websocket)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast_to_admins(self, message: dict):
        for connection in self.active_admins:
            await connection.send_json(message)
            
    async def send_to_customer(self, customer_id: int, message: dict):
        if customer_id in self.active_customers:
            await self.active_customers[customer_id].send_json(message)

manager = ConnectionManager()
