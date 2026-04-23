"""
会话状态管理器
==============
管理用户会话状态，支持消息队列和并发控制。

功能:
    - 会话状态跟踪 (IDLE/GENERATING/QUEUED)
    - 消息队列管理
    - 流式响应支持
"""

import asyncio
from enum import Enum
from typing import Optional, Dict, Any

from datetime import datetime


class ConversationStatus(Enum):
    """会话状态枚举"""
    IDLE = "idle"           # 空闲状态
    GENERATING = "generating"  # 正在生成回答
    QUEUED = "queued"       # 有消息在队列中等待处理


class PendingMessage:
    """待处理消息"""
    
    def __init__(self, message_id: str, content: str):
        self.message_id = message_id
        self.content = content
        self.timestamp = datetime.now()


class SessionState:
    """会话状态"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.status = ConversationStatus.IDLE
        self.current_task: Optional[str] = None
        self.pending_messages: asyncio.Queue = asyncio.Queue()
        self.response_queue: asyncio.Queue = asyncio.Queue()
        self.last_activity: datetime = datetime.now()


class SessionManager:
    """
    会话管理器
    
    管理所有用户会话的状态和消息队列。
    """
    
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create_session(self, user_id: str) -> SessionState:
        """获取或创建会话"""
        async with self._lock:
            if user_id not in self._sessions:
                self._sessions[user_id] = SessionState(user_id=user_id)
            return self._sessions[user_id]
    
    async def get_session(self, user_id: str) -> Optional[SessionState]:
        """获取会话状态"""
        return self._sessions.get(user_id)
    
    async def set_status(self, user_id: str, status: ConversationStatus):
        """设置会话状态"""
        async with self._lock:
            if user_id in self._sessions:
                self._sessions[user_id].status = status
                self._sessions[user_id].last_activity = datetime.now()
    
    async def queue_message(self, user_id: str, message: str) -> tuple[bool, str]:
        """
        将消息加入队列
        
        Returns:
            (是否成功加入队列, 消息ID或错误信息)
        """
        session = await self.get_or_create_session(user_id)
        
        # 生成消息ID
        message_id = f"{user_id}_{datetime.now().timestamp()}"
        pending = PendingMessage(message_id=message_id, content=message)
        
        # 将消息加入队列
        await session.pending_messages.put(pending)
        
        # 更新状态
        if session.status == ConversationStatus.IDLE:
            await self.set_status(user_id, ConversationStatus.QUEUED)
            return True, message_id
        else:
            # 已经在处理中，消息已在队列
            return True, message_id
    
    async def get_next_message(self, user_id: str) -> Optional[PendingMessage]:
        """获取下一个待处理消息"""
        session = await self.get_session(user_id)
        if not session:
            return None
        
        try:
            # 非阻塞获取
            message = session.pending_messages.get_nowait()
            return message
        except asyncio.QueueEmpty:
            return None
    
    async def has_pending_messages(self, user_id: str) -> bool:
        """检查是否有待处理消息"""
        session = await self.get_session(user_id)
        if not session:
            return False
        return not session.pending_messages.empty()
    
    async def put_response_chunk(self, user_id: str, chunk: str):
        """推送响应片段到队列"""
        session = await self.get_session(user_id)
        if session:
            await session.response_queue.put({
                "type": "chunk",
                "content": chunk,
                "timestamp": datetime.now().isoformat()
            })
    
    async def put_response_complete(self, user_id: str, full_response: str):
        """标记响应完成"""
        session = await self.get_session(user_id)
        if session:
            await session.response_queue.put({
                "type": "complete",
                "content": full_response,
                "timestamp": datetime.now().isoformat()
            })
    
    async def put_response_error(self, user_id: str, error: str):
        """推送错误信息"""
        session = await self.get_session(user_id)
        if session:
            await session.response_queue.put({
                "type": "error",
                "content": error,
                "timestamp": datetime.now().isoformat()
            })
    
    async def get_response(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取响应（非阻塞）"""
        session = await self.get_session(user_id)
        if not session:
            return None
        
        try:
            return session.response_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    async def cleanup_inactive_sessions(self, max_idle_minutes: int = 30):
        """清理不活跃的会话"""
        async with self._lock:
            now = datetime.now()
            to_remove = []
            for user_id, session in self._sessions.items():
                idle_time = (now - session.last_activity).total_seconds() / 60
                if idle_time > max_idle_minutes and session.status == ConversationStatus.IDLE:
                    to_remove.append(user_id)
            
            for user_id in to_remove:
                del self._sessions[user_id]
                print(f"[SessionManager] 清理不活跃会话: {user_id}")


# 全局会话管理器实例
session_manager = SessionManager()
