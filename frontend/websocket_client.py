"""
WebSocket客户端
===============
管理与服务器的WebSocket连接，支持流式接收消息。

功能:
    - WebSocket连接管理
    - 自动重连
    - 流式消息接收
    - 消息队列状态通知
"""

import json
import asyncio
from typing import Callable, Optional
from PyQt6.QtCore import QObject, pyqtSignal, QThread
import websocket


class WebSocketWorker(QThread):
    """
    WebSocket工作线程
    
    在后台线程中运行WebSocket连接，避免阻塞UI。
    """
    
    # 信号
    message_chunk = pyqtSignal(str)           # 收到消息片段
    message_complete = pyqtSignal(str)        # 消息完成
    message_queued = pyqtSignal(int, str)     # 消息排队 (位置, 提示信息)
    error_occurred = pyqtSignal(str)          # 发生错误
    connected = pyqtSignal()                  # 连接成功
    disconnected = pyqtSignal()               # 断开连接
    
    def __init__(self, url: str = "ws://127.0.0.1:8000/ws/chat"):
        super().__init__()
        self.url = url
        self.ws: Optional[websocket.WebSocketApp] = None
        self._running = False
        self._message_queue: list[dict] = []  # 待发送消息队列
        self._current_response = ""  # 当前正在接收的完整响应
    
    def run(self):
        """运行WebSocket连接"""
        self._running = True
        
        while self._running:
            try:
                self._connect()
                # 连接建立后，处理消息循环
                self.ws.run_forever()
            except Exception as e:
                print(f"[WebSocketWorker] 连接错误: {e}")
                self.error_occurred.emit(f"连接错误: {e}")
            
            if self._running:
                # 自动重连，等待3秒
                print("[WebSocketWorker] 3秒后重连...")
                self.disconnected.emit()
                import time
                time.sleep(3)
    
    def _connect(self):
        """建立WebSocket连接"""
        print(f"[WebSocketWorker] 连接到 {self.url}")
        
        self.ws = websocket.WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
    
    def _on_open(self, ws):
        """连接建立"""
        print("[WebSocketWorker] WebSocket连接已建立")
        self.connected.emit()
        
        # 发送队列中的消息
        while self._message_queue:
            msg = self._message_queue.pop(0)
            self._send_message_internal(msg)
    
    def _on_message(self, ws, message):
        """收到消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            content = data.get("content", "")
            
            if msg_type == "chunk":
                # 流式片段
                self._current_response += content
                self.message_chunk.emit(content)
            
            elif msg_type == "complete":
                # 完成
                full_response = self._current_response
                self._current_response = ""  # 重置
                self.message_complete.emit(full_response)
            
            elif msg_type == "error":
                # 错误
                self._current_response = ""  # 重置
                self.error_occurred.emit(content)
            
            elif msg_type == "queued":
                # 消息排队
                position = data.get("position", 1)
                msg = data.get("message", "消息已加入队列")
                self.message_queued.emit(position, msg)
        
        except json.JSONDecodeError:
            print(f"[WebSocketWorker] 收到非JSON消息: {message}")
        except Exception as e:
            print(f"[WebSocketWorker] 处理消息错误: {e}")
    
    def _on_error(self, ws, error):
        """发生错误"""
        print(f"[WebSocketWorker] WebSocket错误: {error}")
        self.error_occurred.emit(str(error))
    
    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭"""
        print(f"[WebSocketWorker] WebSocket连接关闭: {close_status_code} - {close_msg}")
        self.disconnected.emit()
    
    def send_message(self, content: str, user_id: str = "default"):
        """发送消息"""
        msg = {
            "type": "message",
            "content": content,
            "user_id": user_id
        }
        
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self._send_message_internal(msg)
        else:
            # 连接未建立，加入队列
            print("[WebSocketWorker] 连接未建立，消息加入队列")
            self._message_queue.append(msg)
    
    def _send_message_internal(self, msg: dict):
        """内部发送消息"""
        try:
            self.ws.send(json.dumps(msg))
            print(f"[WebSocketWorker] 消息已发送: {msg['content'][:50]}...")
        except Exception as e:
            print(f"[WebSocketWorker] 发送失败: {e}")
            self.error_occurred.emit(f"发送失败: {e}")
    
    def stop(self):
        """停止连接"""
        self._running = False
        if self.ws:
            self.ws.close()


class WebSocketClient(QObject):
    """
    WebSocket客户端
    
    对外提供的WebSocket接口，管理连接和消息处理。
    """
    
    # 信号
    message_chunk = pyqtSignal(str)           # 收到消息片段
    message_complete = pyqtSignal(str)        # 消息完成
    message_queued = pyqtSignal(int, str)     # 消息排队
    error_occurred = pyqtSignal(str)          # 发生错误
    connected = pyqtSignal()                  # 连接成功
    disconnected = pyqtSignal()               # 断开连接
    
    def __init__(self, url: str = "ws://127.0.0.1:8000/ws/chat"):
        super().__init__()
        self.url = url
        self.worker: Optional[WebSocketWorker] = None
        self._is_connected = False
    
    def connect(self):
        """建立连接"""
        if self.worker and self.worker.isRunning():
            return
        
        self.worker = WebSocketWorker(self.url)
        
        # 转发信号
        self.worker.message_chunk.connect(self.message_chunk)
        self.worker.message_complete.connect(self.message_complete)
        self.worker.message_queued.connect(self.message_queued)
        self.worker.error_occurred.connect(self.error_occurred)
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        
        self.worker.start()
    
    def disconnect(self):
        """断开连接"""
        if self.worker:
            self.worker.stop()
            self.worker.wait(3000)  # 等待3秒
            self.worker = None
        self._is_connected = False
    
    def send_message(self, content: str, user_id: str = "default"):
        """发送消息"""
        if self.worker:
            self.worker.send_message(content, user_id)
        else:
            self.error_occurred.emit("WebSocket未连接")
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._is_connected
    
    def _on_connected(self):
        """连接成功"""
        self._is_connected = True
        self.connected.emit()
    
    def _on_disconnected(self):
        """断开连接"""
        self._is_connected = False
        self.disconnected.emit()
