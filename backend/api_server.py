"""
桌面宠物后端API服务
===================
基于FastAPI的HTTP JSON API + WebSocket，提供带记忆的聊天功能。

接口:
    POST /api/chat - 聊天接口（兼容旧版）
    WS /ws/chat - WebSocket流式聊天接口

启动:
    python -m backend.api_server
"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

import config
from harness import build_harness, process_single_conversation
from backend.session_manager import session_manager, ConversationStatus
from backend.task_processor import task_consumer

# 创建FastAPI应用
app = FastAPI(
    title="桌面宠物API",
    description="带记忆功能的AI聊天API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局harness实例
harness = None


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str
    user_id: Optional[str] = "default"


class ChatResponse(BaseModel):
    """聊天响应模型"""
    response: str
    status: str
    error: Optional[str] = None


@app.on_event("startup")
async def startup_event():
    """启动时初始化harness和任务消费者"""
    global harness
    try:
        config.validate()
        harness = build_harness()
        # 启动任务消费者
        await task_consumer.start()
        print("=" * 55)
        print("  桌面宠物API服务已启动")
        print(f"  Provider: {config.PROVIDER}")
        print(f"  Model: {config.MAIN_MODEL}")
        print("  支持WebSocket流式响应")
        print("=" * 55)
    except Exception as e:
        print(f"启动失败: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理资源"""
    await task_consumer.stop()
    print("[API] 服务已关闭")


@app.get("/")
async def root():
    """根路径 - 服务状态检查"""
    return {
        "status": "running",
        "service": "桌面宠物API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "harness_ready": harness is not None
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    聊天接口

    接收用户消息，调用AI生成回复，并保存到记忆系统。
    """
    global harness

    if not harness:
        raise HTTPException(status_code=503, detail="服务未就绪")

    if not request.message or not request.message.strip():
        return ChatResponse(
            response="",
            status="error",
            error="消息不能为空"
        )

    try:
        # 处理对话
        reply = process_single_conversation(harness, request.message.strip())

        return ChatResponse(
            response=reply,
            status="success"
        )

    except Exception as e:
        print(f"聊天处理错误: {e}")
        return ChatResponse(
            response="",
            status="error",
            error=str(e)
        )


@app.post("/api/clear_memory")
async def clear_memory():
    """清空记忆接口（调试用）"""
    from memory import clear_all_memory
    try:
        clear_all_memory()
        return {"status": "success", "message": "记忆已清空"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket流式聊天接口
    
    支持实时流式响应，用户可连续发送消息。
    协议:
        客户端发送: {"type": "message", "content": "...", "user_id": "..."}
        服务端推送: {"type": "chunk", "content": "..."}
        服务端推送: {"type": "complete", "content": "..."}
        服务端推送: {"type": "error", "content": "..."}
        服务端推送: {"type": "queued", "position": N}  # 消息在队列中的位置
    """
    await websocket.accept()
    user_id = None
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            
            if data.get("type") != "message":
                continue
            
            message = data.get("content", "").strip()
            user_id = data.get("user_id", "default")
            
            if not message:
                await websocket.send_json({
                    "type": "error",
                    "content": "消息不能为空"
                })
                continue
            
            # 获取会话状态
            session = await session_manager.get_or_create_session(user_id)
            
            # 检查当前状态
            if session.status == ConversationStatus.GENERATING:
                # 正在生成中，消息将排队
                position = session.pending_messages.qsize() + 1
                await websocket.send_json({
                    "type": "queued",
                    "position": position,
                    "message": "消息已加入队列，当前正在处理前一条消息"
                })
            
            # 提交消息到任务处理器
            message_id = await task_consumer.submit_message(user_id, message)
            
            # 等待并流式返回响应
            full_response = ""
            while True:
                # 获取响应（带超时）
                try:
                    response = await asyncio.wait_for(
                        session_manager.get_response(user_id),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    response = None
                
                if response:
                    msg_type = response.get("type")
                    content = response.get("content", "")
                    
                    if msg_type == "chunk":
                        # 流式片段
                        await websocket.send_json({
                            "type": "chunk",
                            "content": content
                        })
                        full_response += content
                    
                    elif msg_type == "complete":
                        # 完成
                        await websocket.send_json({
                            "type": "complete",
                            "content": full_response
                        })
                        break
                    
                    elif msg_type == "error":
                        # 错误
                        await websocket.send_json({
                            "type": "error",
                            "content": content
                        })
                        break
                
                # 短暂休眠避免CPU占用过高
                await asyncio.sleep(0.01)
    
    except WebSocketDisconnect:
        print(f"[WebSocket] 客户端断开连接: {user_id}")
    except Exception as e:
        print(f"[WebSocket] 错误: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"服务器错误: {str(e)}"
            })
        except:
            pass
    finally:
        print(f"[WebSocket] 连接关闭: {user_id}")


def main():
    """主函数 - 启动API服务"""
    uvicorn.run(
        "backend.api_server:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
