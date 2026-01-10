"""
WebSocket Broadcaster for Market Events

Receives normalized market events from collector and broadcasts to UI clients.
Per specification: real-time streaming, not REST polling.
"""

import asyncio
import json
from typing import Set
from fastapi import WebSocket


class MarketEventBroadcaster:
    """
    Manages WebSocket connections and broadcasts market events.
    Connects market_event_collector → API → UI.
    """
    
    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._event_queue = asyncio.Queue()
    
    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection."""
        await websocket.accept()
        self._connections.add(websocket)
        print(f"[BROADCAST] Client connected. Total: {len(self._connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove disconnected client."""
        self._connections.discard(websocket)
        print(f"[BROADCAST] Client disconnected. Total: {len(self._connections)}")
    
    async def broadcast_event(self, event: dict):
        """Broadcast normalized market event to all connected clients."""
        if not self._connections:
            return
        
        disconnected = set()
        
        for ws in self._connections:
            try:
                await ws.send_json(event)
            except Exception as e:
                print(f"[BROADCAST] Error sending to client: {e}")
                disconnected.add(ws)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws)
    
    async def enqueue_event(self, event: dict):
        """Add event to broadcast queue."""
        await self._event_queue.put(event)
    
    async def broadcast_loop(self):
        """Continuous broadcast loop."""
        while True:
            event = await self._event_queue.get()
            await self.broadcast_event(event)


# Global broadcaster instance
broadcaster = MarketEventBroadcaster()
