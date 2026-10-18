import asyncio
import time
from typing import Dict, Iterable, List, Set
from fastapi import WebSocket
from app.core.logging import logger


class ConnectionManager:
    """In-memory WebSocket connection and online presence manager.

    Maps user IDs to their active WebSocket connection(s), supporting multiple
    browser tabs/devices per user. Assumes a single Uvicorn server worker
    as specified in the architecture plan.
    """

    def __init__(self) -> None:
        # Maps user_id -> set of active WebSocket instances
        self._user_sockets: Dict[int, Set[WebSocket]] = {}
        # Maps conversation_id -> { user_id: last_typed_timestamp }
        self._typing_users: Dict[int, Dict[int, float]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> bool:
        """Register a new WebSocket connection for a user.

        Returns True if the user was previously offline (first active connection).
        """
        async with self._lock:
            is_newly_online = user_id not in self._user_sockets
            if is_newly_online:
                self._user_sockets[user_id] = set()

            self._user_sockets[user_id].add(websocket)
            logger.info(
                "WebSocket connected for user %d (total connections for user: %d)",
                user_id,
                len(self._user_sockets[user_id]),
            )
            return is_newly_online

    async def disconnect(self, user_id: int, websocket: WebSocket) -> bool:
        """Unregister a WebSocket connection for a user.

        Returns True if the user now has 0 remaining active connections (went offline).
        """
        async with self._lock:
            if user_id in self._user_sockets:
                self._user_sockets[user_id].discard(websocket)
                if len(self._user_sockets[user_id]) == 0:
                    del self._user_sockets[user_id]
                    logger.info("User %d went offline (no remaining sockets)", user_id)
                    return True
                else:
                    logger.info(
                        "User %d closed a connection (remaining sockets: %d)",
                        user_id,
                        len(self._user_sockets[user_id]),
                    )
            return False

    async def get_online_user_ids(self) -> List[int]:
        """Return list of all currently online user IDs."""
        async with self._lock:
            return sorted(list(self._user_sockets.keys()))

    async def is_user_online(self, user_id: int) -> bool:
        """Check if user has at least one active connection."""
        async with self._lock:
            return user_id in self._user_sockets

    async def send_json_to_user(self, user_id: int, data: dict) -> None:
        """Send JSON payload to all active sockets belonging to a user."""
        async with self._lock:
            sockets = list(self._user_sockets.get(user_id, set()))

        dead_sockets = []
        for ws in sockets:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.warning("Failed to send message to socket for user %d: %s", user_id, str(e))
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                if user_id in self._user_sockets:
                    for dead in dead_sockets:
                        self._user_sockets[user_id].discard(dead)
                    if len(self._user_sockets[user_id]) == 0:
                        del self._user_sockets[user_id]

    async def broadcast_to_users(self, user_ids: Iterable[int], data: dict) -> None:
        """Broadcast JSON payload to a specified set of users (e.g. conversation members)."""
        tasks = [self.send_json_to_user(uid, data) for uid in set(user_ids)]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_to_all(self, data: dict, exclude_user_id: int | None = None) -> None:
        """Broadcast JSON payload to all currently connected users."""
        async with self._lock:
            if exclude_user_id is not None:
                all_user_ids = [uid for uid in self._user_sockets.keys() if uid != exclude_user_id]
            else:
                all_user_ids = list(self._user_sockets.keys())

        tasks = [self.send_json_to_user(uid, data) for uid in all_user_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def start_typing(self, conversation_id: int, user_id: int) -> None:
        """Mark user as actively typing in a conversation."""
        async with self._lock:
            if conversation_id not in self._typing_users:
                self._typing_users[conversation_id] = {}
            self._typing_users[conversation_id][user_id] = time.time()

    async def stop_typing(self, conversation_id: int, user_id: int) -> None:
        """Mark user as stopped typing in a conversation."""
        async with self._lock:
            if conversation_id in self._typing_users:
                self._typing_users[conversation_id].pop(user_id, None)
                if not self._typing_users[conversation_id]:
                    del self._typing_users[conversation_id]

    async def clear_user_typing(self, user_id: int) -> List[int]:
        """Clear typing state across all conversations for a disconnected user."""
        conv_ids = []
        async with self._lock:
            for conv_id, users_dict in list(self._typing_users.items()):
                if user_id in users_dict:
                    del users_dict[user_id]
                    conv_ids.append(conv_id)
                    if not users_dict:
                        del self._typing_users[conv_id]
        return conv_ids


# Global connection manager instance
connection_manager = ConnectionManager()
