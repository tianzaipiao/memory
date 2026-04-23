"""
后台任务处理器
==============
处理消息队列中的任务，支持流式生成和后台存储。

功能:
    - 消费消息队列
    - 流式生成AI响应
    - 后台执行记忆存储
"""

import asyncio
import sys
import os
from typing import AsyncGenerator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

import config
from harness import build_harness, HarnessState
from memory import save_conversation_with_memory
from prompts import get_system_prompt
from backend.session_manager import session_manager, ConversationStatus, PendingMessage


class StreamingProcessor:
    """
    流式处理器
    
    处理单条消息，支持流式生成响应。
    """
    
    def __init__(self):
        self.llm = config.get_llm(config.MAIN_MODEL)
    
    async def process_stream(
        self, 
        user_id: str, 
        message: str
    ) -> AsyncGenerator[str, None]:
        """
        流式处理消息
        
        Yields:
            生成的文本片段
        """
        # 获取系统提示和记忆上下文
        system_prompt, memory_context, vector_memories = get_system_prompt(message)
        
        # 构建用户消息内容
        user_content = message
        if memory_context:
            user_content = f"{message}\n\n【相关记忆上下文】\n{memory_context}"
        
        # 组装消息
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ]
        
        # 流式调用
        full_response = ""
        try:
            # 使用 astream 方法进行流式调用
            async for chunk in self.llm.astream(messages):
                content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                if content:
                    full_response += content
                    yield content
        except Exception as e:
            print(f"[StreamingProcessor] 流式生成错误: {e}")
            # 如果流式失败，尝试非流式
            try:
                print("[StreamingProcessor] 尝试非流式调用...")
                response = self.llm.invoke(messages)
                content = response.content if hasattr(response, 'content') else str(response)
                full_response = content
                yield content
            except Exception as e2:
                print(f"[StreamingProcessor] 非流式调用也失败: {e2}")
                raise
        
        # 完成后，启动后台任务保存记忆
        asyncio.create_task(
            self._save_memory_background(user_id, message, full_response)
        )
    
    async def _save_memory_background(self, user_id: str, user_message: str, assistant_reply: str):
        """后台保存记忆（在单独线程中执行，不阻塞事件循环）"""
        try:
            print(f"[TaskProcessor] 后台保存记忆: {user_id}")
            # 使用 asyncio.to_thread 在单独线程中执行同步函数
            await asyncio.to_thread(save_conversation_with_memory, user_message, assistant_reply)
            print(f"[TaskProcessor] 记忆保存完成: {user_id}")
        except Exception as e:
            print(f"[TaskProcessor] 保存记忆失败: {e}")


class TaskConsumer:
    """
    任务消费者
    
    持续消费消息队列，处理用户消息。
    """
    
    def __init__(self):
        self.processor = StreamingProcessor()
        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}
    
    async def start(self):
        """启动任务消费者"""
        self._running = True
        print("[TaskConsumer] 任务消费者已启动")
        
        # 启动清理任务
        asyncio.create_task(self._cleanup_loop())
    
    async def stop(self):
        """停止任务消费者"""
        self._running = False
        # 取消所有正在运行的任务
        for task in self._tasks.values():
            task.cancel()
        print("[TaskConsumer] 任务消费者已停止")
    
    async def process_user_message(self, user_id: str, message: str):
        """
        处理单个用户消息
        
        这是主要的处理入口，会流式生成响应并推送到session_manager。
        注意：此方法不管理状态，由调用方负责状态管理
        """
        try:
            full_response = ""
            
            # 流式生成
            async for chunk in self.processor.process_stream(user_id, message):
                full_response += chunk
                # 推送片段到响应队列
                await session_manager.put_response_chunk(user_id, chunk)
            
            # 标记完成
            await session_manager.put_response_complete(user_id, full_response)
            
        except Exception as e:
            error_msg = f"处理消息时出错: {str(e)}"
            print(f"[TaskConsumer] {error_msg}")
            await session_manager.put_response_error(user_id, error_msg)
    
    async def submit_message(self, user_id: str, message: str) -> str:
        """
        提交消息处理
        
        将消息加入队列，如果会话空闲则立即开始处理。
        
        Returns:
            消息ID
        """
        # 获取会话
        session = await session_manager.get_or_create_session(user_id)
        
        # 生成消息ID
        import time
        message_id = f"{user_id}_{time.time()}"
        pending = PendingMessage(message_id=message_id, content=message)
        
        # 检查当前状态
        should_start_processing = session.status == ConversationStatus.IDLE
        
        # 将消息加入队列
        await session.pending_messages.put(pending)
        print(f"[TaskConsumer] 消息已加入队列: {user_id}, 消息长度: {len(message)}")
        
        # 更新状态
        if should_start_processing:
            await session_manager.set_status(user_id, ConversationStatus.GENERATING)
            # 启动处理任务
            task = asyncio.create_task(
                self._process_single_message(user_id, message)
            )
            self._tasks[user_id] = task
            print(f"[TaskConsumer] 立即开始处理: {user_id}")
        else:
            await session_manager.set_status(user_id, ConversationStatus.QUEUED)
            print(f"[TaskConsumer] 消息排队等待: {user_id}")
        
        return message_id
    
    async def _process_single_message(self, user_id: str, first_message: str):
        """处理单条消息（供 submit_message 直接调用）"""
        try:
            # 处理第一条消息
            await session_manager.set_status(user_id, ConversationStatus.GENERATING)
            await self.process_user_message(user_id, first_message)
            
            # 检查是否还有更多消息
            while await session_manager.has_pending_messages(user_id):
                pending = await session_manager.get_next_message(user_id)
                if pending:
                    await session_manager.set_status(user_id, ConversationStatus.GENERATING)
                    await self.process_user_message(user_id, pending.content)
        
        except asyncio.CancelledError:
            print(f"[TaskConsumer] 任务取消: {user_id}")
        
        finally:
            # 设置状态为空闲
            await session_manager.set_status(user_id, ConversationStatus.IDLE)
            # 清理任务引用
            if user_id in self._tasks:
                del self._tasks[user_id]
    
    async def _process_queue(self, user_id: str):
        """处理队列中的消息"""
        try:
            while self._running:
                # 获取下一条消息
                pending = await session_manager.get_next_message(user_id)
                
                if pending is None:
                    # 队列为空，退出
                    break
                
                # 处理消息
                await self.process_user_message(user_id, pending.content)
                
                # 检查是否还有更多消息
                has_more = await session_manager.has_pending_messages(user_id)
                if not has_more:
                    break
        
        except asyncio.CancelledError:
            print(f"[TaskConsumer] 任务取消: {user_id}")
        
        finally:
            # 清理任务引用
            if user_id in self._tasks:
                del self._tasks[user_id]
    
    async def _cleanup_loop(self):
        """定期清理不活跃会话"""
        while self._running:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                await session_manager.cleanup_inactive_sessions()
            except Exception as e:
                print(f"[TaskConsumer] 清理错误: {e}")


# 全局任务消费者实例
task_consumer = TaskConsumer()
