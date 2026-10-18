from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import AppException
from app.core.logging import logger
from app.db.models import ConversationMember
from app.db.session import async_session_maker
from app.schemas.auth import UserResponse
from app.schemas.websocket import MessageSendPayload
from app.services.auth_service import AuthService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.permission_service import PermissionService
from app.services.presence_service import connection_manager

router = APIRouter(tags=["WebSocket"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def handle_websocket_connection(websocket: WebSocket):
    """Authenticate and manage a real-time WebSocket connection session."""
    # 1. Extract session token from cookie (handshake) or query param fallback
    token = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        token = websocket.query_params.get("token")

    if not token:
        logger.warning("WebSocket connection rejected: Missing session cookie/token")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return

    # 2. Authenticate session in database
    async with async_session_maker() as db:
        user = await AuthService.get_user_by_session_token(db, token)

    if user is None:
        logger.warning("WebSocket connection rejected: Invalid or expired session token")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid session")
        return

    # 3. Accept connection
    await websocket.accept()

    # 4. Register connection in manager
    is_newly_online = await connection_manager.connect(user.id, websocket)

    try:
        # 5. Send connection.ready with user info
        await websocket.send_json({
            "type": "connection.ready",
            "payload": {
                "user": UserResponse.model_validate(user).model_dump(mode="json"),
                "server_time": utc_now().isoformat(),
            },
        })

        # 6. Send initial presence snapshot to this client
        online_users = await connection_manager.get_online_user_ids()
        await websocket.send_json({
            "type": "presence.snapshot",
            "payload": {"online_users": online_users},
        })

        # 7. Broadcast presence change to other users if user newly transitioned from offline to online
        if is_newly_online:
            await connection_manager.broadcast_to_all(
                {
                    "type": "presence.changed",
                    "payload": {"user_id": user.id, "status": "online"},
                },
                exclude_user_id=user.id,
            )

        # 8. Main event loop
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue

            event_type = data.get("type")
            req_id = data.get("request_id")
            payload = data.get("payload", {})

            if event_type == "ping":
                await websocket.send_json({"type": "pong", "request_id": req_id})
                continue

            elif event_type == "message.send":
                await handle_message_send(websocket, user, req_id, payload)

            elif event_type == "message.read":
                await handle_message_read(websocket, user.id, req_id, payload)

            elif event_type == "typing.start":
                await handle_typing_event(user.id, user.username, user.display_name, payload, is_typing=True)

            elif event_type == "typing.stop":
                await handle_typing_event(user.id, user.username, user.display_name, payload, is_typing=False)

            elif event_type == "reaction.toggle":
                await handle_reaction_toggle(websocket, user.id, req_id, payload)

            else:
                await websocket.send_json({
                    "type": "error",
                    "request_id": req_id,
                    "payload": {
                        "code": "UNKNOWN_EVENT_TYPE",
                        "message": f"Unsupported event type: '{event_type}'",
                    },
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally for user %d", user.id)
    except Exception as e:
        logger.warning("WebSocket error for user %d: %s", user.id, str(e))
    finally:
        cleared_conv_ids = await connection_manager.clear_user_typing(user.id)
        if cleared_conv_ids:
            for cid in cleared_conv_ids:
                try:
                    async with async_session_maker() as db:
                        m_stmt = select(ConversationMember.user_id).where(
                            ConversationMember.conversation_id == cid,
                            ConversationMember.is_active == True,
                        )
                        uids = list((await db.execute(m_stmt)).scalars().all())
                    await connection_manager.broadcast_to_users(
                        uids,
                        {
                            "type": "typing.updated",
                            "payload": {
                                "conversation_id": cid,
                                "user_id": user.id,
                                "username": user.username,
                                "display_name": user.display_name,
                                "is_typing": False,
                            },
                        },
                    )
                except Exception:
                    pass

        is_now_offline = await connection_manager.disconnect(user.id, websocket)
        if is_now_offline:
            await connection_manager.broadcast_to_all({
                "type": "presence.changed",
                "payload": {"user_id": user.id, "status": "offline"},
            })


async def handle_message_send(
    websocket: WebSocket,
    sender_user,
    req_id: Optional[str],
    payload_data: dict,
):
    """Validate, persist to SQLite, acknowledge, and broadcast a chat message."""
    try:
        send_data = MessageSendPayload.model_validate(payload_data)
    except ValidationError as val_err:
        await websocket.send_json({
            "type": "error",
            "request_id": req_id,
            "payload": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid message payload",
                "details": val_err.errors(),
            },
        })
        return

    try:
        async with async_session_maker() as db:
            # 1. Authorize: verify sender is active member of conversation
            await PermissionService.get_active_membership(
                db, send_data.conversation_id, sender_user.id
            )

            # 2. Persist message to SQLite before announcing delivery
            msg = await MessageService.create_message(
                db=db,
                conversation_id=send_data.conversation_id,
                sender_id=sender_user.id,
                content=send_data.content,
                client_message_id=send_data.client_message_id,
                reply_to_message_id=send_data.reply_to_message_id,
            )

            # 3. Retrieve all active conversation members
            members_stmt = select(ConversationMember.user_id).where(
                ConversationMember.conversation_id == send_data.conversation_id,
                ConversationMember.is_active == True,
            )
            member_user_ids = (await db.execute(members_stmt)).scalars().all()

        # 4. Acknowledge receipt to the sender
        await websocket.send_json({
            "type": "message.ack",
            "request_id": req_id,
            "payload": {
                "message_id": msg.id,
                "client_message_id": msg.client_message_id,
                "conversation_id": msg.conversation_id,
                "created_at": msg.created_at.isoformat(),
            },
        })

        reply_to_payload = None
        if getattr(msg, "reply_to", None):
            reply_to_payload = {
                "id": msg.reply_to.id,
                "sender_username": msg.reply_to.sender.username if msg.reply_to.sender else None,
                "sender_display_name": msg.reply_to.sender.display_name if msg.reply_to.sender else None,
                "content": msg.reply_to.content if msg.reply_to.deleted_at is None else "[Message deleted]",
                "message_type": msg.reply_to.message_type,
            }
        elif msg.reply_to_message_id:
            reply_to_payload = {
                "id": msg.reply_to_message_id,
                "sender_username": None,
                "sender_display_name": None,
                "content": "[Replied message]",
                "message_type": "text",
            }

        # 5. Broadcast message.created to active conversation members ONLY
        broadcast_payload = {
            "message_id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender": {
                "id": sender_user.id,
                "username": sender_user.username,
                "display_name": sender_user.display_name,
            },
            "message_type": msg.message_type,
            "content": msg.content,
            "client_message_id": msg.client_message_id,
            "reply_to_message_id": msg.reply_to_message_id,
            "reply_to": reply_to_payload,
            "reactions": [],
            "created_at": msg.created_at.isoformat(),
            "attachments": [],
        }

        await connection_manager.broadcast_to_users(
            member_user_ids,
            {
                "type": "message.created",
                "payload": broadcast_payload,
            },
        )

    except AppException as app_err:
        await websocket.send_json({
            "type": "error",
            "request_id": req_id,
            "payload": {
                "code": app_err.code,
                "message": app_err.message,
            },
        })
    except Exception as exc:
        logger.exception("Unexpected error processing message.send: %s", str(exc))
        await websocket.send_json({
            "type": "error",
            "request_id": req_id,
            "payload": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Failed to process message",
            },
        })
    finally:
        # Clear sender typing state when a message is sent
        await connection_manager.stop_typing(send_data.conversation_id, sender_user.id)


async def handle_message_read(
    websocket: WebSocket,
    user_id: int,
    req_id: Optional[str],
    payload: dict,
):
    """Mark conversation messages as read and notify active conversation members."""
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        if req_id:
            await websocket.send_json({
                "type": "error",
                "request_id": req_id,
                "payload": {"code": "INVALID_PAYLOAD", "message": "conversation_id is required"},
            })
        return

    last_read_id = payload.get("last_read_message_id")
    try:
        conv_id = int(conversation_id)
        async with async_session_maker() as db:
            new_last_read = await ConversationService.mark_conversation_read(
                db, conv_id, user_id, last_read_id
            )
            members_stmt = select(ConversationMember.user_id).where(
                ConversationMember.conversation_id == conv_id,
                ConversationMember.is_active == True,
            )
            active_uids = list((await db.execute(members_stmt)).scalars().all())

        if req_id:
            await websocket.send_json({
                "type": "message.read.ack",
                "request_id": req_id,
                "payload": {
                    "conversation_id": conv_id,
                    "last_read_message_id": new_last_read,
                },
            })

        await connection_manager.broadcast_to_users(
            active_uids,
            {
                "type": "message.read.updated",
                "payload": {
                    "conversation_id": conv_id,
                    "user_id": user_id,
                    "last_read_message_id": new_last_read,
                },
            },
        )
    except Exception as exc:
        logger.error("Error processing message.read: %s", str(exc), exc_info=True)


async def handle_typing_event(
    user_id: int,
    username: str,
    display_name: str,
    payload: dict,
    is_typing: bool,
):
    """Handle typing.start / typing.stop events and broadcast to active conversation members."""
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        return

    try:
        conv_id = int(conversation_id)
        async with async_session_maker() as db:
            # Verify active membership
            await PermissionService.get_active_membership(db, conv_id, user_id)
            members_stmt = select(ConversationMember.user_id).where(
                ConversationMember.conversation_id == conv_id,
                ConversationMember.is_active == True,
            )
            active_uids = list((await db.execute(members_stmt)).scalars().all())

        if is_typing:
            await connection_manager.start_typing(conv_id, user_id)
        else:
            await connection_manager.stop_typing(conv_id, user_id)

        notify_uids = [uid for uid in active_uids if uid != user_id]
        await connection_manager.broadcast_to_users(
            notify_uids,
            {
                "type": "typing.updated",
                "payload": {
                    "conversation_id": conv_id,
                    "user_id": user_id,
                    "username": username,
                    "display_name": display_name,
                    "is_typing": is_typing,
                },
            },
        )
    except Exception as e:
        logger.error("Typing event error: %s", str(e), exc_info=True)


async def handle_reaction_toggle(
    websocket: WebSocket,
    user_id: int,
    req_id: Optional[str],
    payload_data: dict,
):
    """Toggle an emoji reaction on a message via WebSocket."""
    message_id = payload_data.get("message_id")
    emoji = payload_data.get("emoji")
    if not message_id or not emoji:
        await websocket.send_json({
            "type": "error",
            "request_id": req_id,
            "payload": {
                "code": "VALIDATION_ERROR",
                "message": "message_id and emoji are required",
            },
        })
        return

    try:
        async with async_session_maker() as db:
            msg, reactions, is_added = await MessageService.toggle_reaction(
                db, int(message_id), user_id, str(emoji)
            )
            members_stmt = select(ConversationMember.user_id).where(
                ConversationMember.conversation_id == msg.conversation_id,
                ConversationMember.is_active == True,
            )
            active_uids = list((await db.execute(members_stmt)).scalars().all())

        # Broadcast update to active conversation members
        await connection_manager.broadcast_to_users(
            active_uids,
            {
                "type": "message.reaction.updated",
                "payload": {
                    "conversation_id": msg.conversation_id,
                    "message_id": msg.id,
                    "reactions": [r.model_dump() for r in reactions],
                },
            },
        )

        if req_id:
            await websocket.send_json({
                "type": "reaction.ack",
                "request_id": req_id,
                "payload": {
                    "message_id": msg.id,
                    "conversation_id": msg.conversation_id,
                    "action": "added" if is_added else "removed",
                    "reactions": [r.model_dump() for r in reactions],
                },
            })
    except AppException as app_err:
        await websocket.send_json({
            "type": "error",
            "request_id": req_id,
            "payload": {"code": app_err.code, "message": app_err.message},
        })


@router.websocket("/ws")
async def websocket_root_endpoint(websocket: WebSocket):
    """Main authenticated WebSocket endpoint /ws."""
    await handle_websocket_connection(websocket)
