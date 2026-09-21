"""WebSocket connection manager for real-time progress updates."""
from __future__ import annotations
import asyncio
import json
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections and broadcasts download progress."""

    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self._subscriptions: dict[WebSocket, set[str]] = {}  # ws -> set of task_ids
        self._queue: asyncio.Queue = asyncio.Queue()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        self._subscriptions[websocket] = set()

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        self._subscriptions.pop(websocket, None)

    async def send_progress(self, task_id: str, data: dict):
        """Enqueue a progress update to be broadcast."""
        await self._queue.put({'task_id': task_id, **data})

    async def broadcast_loop(self):
        """Continuously drain the progress queue and send to subscribed clients."""
        while True:
            try:
                msg = await self._queue.get()
                task_id = msg.get('task_id')
                dead = []
                for ws in self.active_connections:
                    subs = self._subscriptions.get(ws, set())
                    # Send if subscribed to this task or subscribed to all ('*')
                    if not subs or task_id in subs or '*' in subs:
                        try:
                            await ws.send_json(msg)
                        except Exception:
                            dead.append(ws)
                for ws in dead:
                    self.disconnect(ws)
            except Exception:
                await asyncio.sleep(0.1)

    async def handle_client(self, websocket: WebSocket):
        """Handle incoming messages from a client (subscribe/unsubscribe)."""
        try:
            while True:
                data = await websocket.receive_json()
                subs = self._subscriptions.get(websocket, set())
                if 'subscribe' in data:
                    subs.update(data['subscribe'])
                if 'unsubscribe' in data:
                    subs -= set(data['unsubscribe'])
                if 'subscribe_all' in data and data['subscribe_all']:
                    subs.add('*')
                self._subscriptions[websocket] = subs
        except Exception:
            pass
        finally:
            self.disconnect(websocket)


# Global singleton
ws_manager = ConnectionManager()
