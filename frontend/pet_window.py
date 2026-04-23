"""
桌面宠物主窗口
==============
悬浮在桌面的宠物窗口，支持拖动、点击交互。

功能:
    - 无边框、透明背景、置顶
    - 鼠标拖动
    - 点击打开聊天窗口
    - 右键菜单
    - 状态显示（空闲/思考/对话）
    - GIF动画支持
"""

import sys
import os
import requests
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QApplication, QMenu, QLabel, QVBoxLayout,
    QSystemTrayIcon, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QPixmap, QPainter, QColor, QCursor, QIcon, QAction
from PyQt6.QtGui import QMovie

from frontend.pet_state import PetStateManager, PetState
from frontend.chat_bubble import ChatBubbleWindow
from frontend.websocket_client import WebSocketClient


class ChatWorker(QThread):
    """
    聊天工作线程

    在后台线程中调用API，避免阻塞UI。
    """

    response_ready = pyqtSignal(str)  # 收到回复
    error_occurred = pyqtSignal(str)  # 发生错误

    def __init__(self, message: str, api_url: str = "http://127.0.0.1:8000"):
        super().__init__()
        self.message = message
        self.api_url = api_url

    def run(self):
        """执行API调用"""
        try:
            response = requests.post(
                f"{self.api_url}/api/chat",
                json={"message": self.message, "user_id": "default"},
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "success":
                self.response_ready.emit(data.get("response", ""))
            else:
                self.error_occurred.emit(data.get("error", "未知错误"))

        except requests.exceptions.ConnectionError:
            self.error_occurred.emit("无法连接到服务器，请检查后端是否启动")
        except requests.exceptions.Timeout:
            self.error_occurred.emit("请求超时，请稍后重试")
        except Exception as e:
            self.error_occurred.emit(f"请求错误: {str(e)}")


class PetWindow(QWidget):
    """
    桌面宠物窗口

    主悬浮窗口，显示宠物形象并处理交互。
    """

    def __init__(self):
        super().__init__()

        # 窗口设置
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 宠物尺寸
        self.pet_size = 150
        self.setFixedSize(self.pet_size, self.pet_size)

        # 拖动相关
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._window_start_pos = QPoint()

        # 状态管理
        self.state_manager = PetStateManager(self)
        self.state_manager.state_changed.connect(self._on_state_changed)

        # 聊天窗口
        self.chat_window = ChatBubbleWindow()
        self.chat_window.message_sent.connect(self._on_message_sent)
        # 连接聊天窗口移动信号
        self.chat_window.window_moved.connect(self._on_chat_window_moved)

        # WebSocket客户端（用于流式通信）
        self._ws_client = WebSocketClient()
        self._ws_client.message_chunk.connect(self._on_ws_chunk)
        self._ws_client.message_complete.connect(self._on_ws_complete)
        self._ws_client.message_queued.connect(self._on_ws_queued)
        self._ws_client.error_occurred.connect(self._on_ws_error)
        self._ws_client.connected.connect(self._on_ws_connected)
        self._ws_client.disconnected.connect(self._on_ws_disconnected)

        # 当前正在接收的消息
        self._current_streaming_message = None
        self._is_streaming = False

        # GIF动画
        self._movies = {}  # 存储不同状态的GIF
        self._current_movie = None
        self._load_gif_images()

        # 位置记忆
        self._settings_file = Path.home() / ".pet_desktop" / "position.txt"
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)

        # 相对位置（聊天窗口相对于宠物的位置）
        self._chat_relative_pos = None

        self._setup_ui()
        self._restore_position()
        self._setup_tray()

        # 启动WebSocket连接
        self._ws_client.connect()

        # 确保窗口显示在最前面
        self.raise_()
        self.activateWindow()

        # 初始状态设置为空闲
        self._switch_to_gif(PetState.IDLE)

    def _setup_ui(self):
        """初始化UI"""
        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 宠物标签（用于显示GIF）
        self.pet_label = QLabel(self)
        self.pet_label.setFixedSize(self.pet_size, self.pet_size)
        self.pet_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pet_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # 设置透明背景
        self.pet_label.setStyleSheet("QLabel { background-color: transparent; }")

        layout.addWidget(self.pet_label)

        # 状态指示器（小圆点）- 可选，可以隐藏
        self.status_dot = QLabel(self)
        self.status_dot.setFixedSize(12, 12)
        self.status_dot.move(self.pet_size - 20, 10)
        self.status_dot.hide()  # 隐藏状态点，因为GIF本身显示状态

    def _load_gif_images(self):
        """加载GIF图片"""
        assets_dir = Path(__file__).parent / "assets"

        # 加载三个状态的GIF
        gif_files = {
            PetState.IDLE: "pet_idle.gif",
            PetState.THINKING: "pet_thinking.gif",
            PetState.TALKING: "pet_talking.gif"
        }

        for state, filename in gif_files.items():
            gif_path = assets_dir / filename
            if gif_path.exists():
                movie = QMovie(str(gif_path))
                movie.setScaledSize(QSize(self.pet_size - 10, self.pet_size - 10))
                self._movies[state] = movie
                print(f"[PetWindow] 已加载GIF: {filename}")
            else:
                print(f"[PetWindow] 未找到GIF: {filename}")

        # 如果没有加载到任何GIF，使用默认表情
        if not self._movies:
            print("[PetWindow] 未找到任何GIF，使用默认表情")

    def _switch_to_gif(self, state: PetState):
        """切换到指定状态的GIF"""
        # 停止当前播放的GIF
        if self._current_movie:
            self._current_movie.stop()
            self._current_movie = None

        # 获取对应状态的GIF
        movie = self._movies.get(state)

        if movie:
            self._current_movie = movie
            self.pet_label.setMovie(movie)
            movie.start()
            print(f"[PetWindow] 切换到GIF状态: {state.value}")
        else:
            # 如果没有对应的GIF，使用默认表情
            self._show_default_emoji(state)

    def _show_default_emoji(self, state: PetState):
        """显示默认表情"""
        emoji_map = {
            PetState.IDLE: "🐱",
            PetState.THINKING: "🤔",
            PetState.TALKING: "💬"
        }
        emoji = emoji_map.get(state, "🐱")
        self.pet_label.setText(emoji)
        self.pet_label.setStyleSheet("""
            QLabel {
                font-size: 80px;
                background-color: transparent;
            }
        """)
        print(f"[PetWindow] 使用默认表情: {state.value}")

    def _on_state_changed(self, state: PetState):
        """状态变化处理"""
        # 切换到对应的GIF
        self._switch_to_gif(state)

    def _restore_position(self):
        """恢复上次位置"""
        try:
            if self._settings_file.exists():
                with open(self._settings_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        x, y = map(int, content.split(','))
                        # 检查位置是否在屏幕范围内
                        screen = QApplication.primaryScreen().availableGeometry()
                        if 0 <= x <= screen.width() - self.pet_size and 0 <= y <= screen.height() - self.pet_size:
                            self.move(x, y)
                            print(f"[PetWindow] 恢复位置: ({x}, {y})")
                            return
                        else:
                            print(f"[PetWindow] 保存的位置超出屏幕范围: ({x}, {y})，使用默认位置")
        except Exception as e:
            print(f"[PetWindow] 恢复位置失败: {e}")

        # 默认位置：右下角（考虑任务栏）
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - self.pet_size - 20
        y = screen.height() - self.pet_size - 20
        self.move(x, y)
        print(f"[PetWindow] 默认位置: ({x}, {y}), 屏幕可用区域: {screen.width()}x{screen.height()}")

    def _save_position(self):
        """保存当前位置"""
        try:
            with open(self._settings_file, 'w') as f:
                f.write(f"{self.x()},{self.y()}")
        except Exception as e:
            print(f"[PetWindow] 保存位置失败: {e}")

    def _setup_tray(self):
        """设置系统托盘"""
        self.tray_icon = QSystemTrayIcon(self)

        # 创建托盘图标（使用默认图标，确保始终可用）
        self._create_default_tray_icon()

        self.tray_icon.setToolTip("桌面宠物 - 点击显示")

        # 托盘菜单
        tray_menu = QMenu()

        show_action = QAction("显示宠物", self)
        show_action.triggered.connect(self._force_show)
        tray_menu.addAction(show_action)

        chat_action = QAction("打开对话", self)
        chat_action.triggered.connect(self._show_chat)
        tray_menu.addAction(chat_action)

        tray_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self._exit_app)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

        # 检查托盘是否可用
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("[WARNING] 系统托盘不可用")
        else:
            print("[INFO] 系统托盘已设置")
            print("[INFO] 提示：如果看不到托盘图标，请检查系统托盘设置或点击托盘区域的箭头")

    def _create_default_tray_icon(self):
        """创建默认托盘图标"""
        # 创建一个简单的蓝色圆形图标
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)  # 透明背景

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制蓝色圆形
        painter.setBrush(QColor(74, 144, 217))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 28, 28)

        # 绘制白色文字 "P"
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "P")

        painter.end()

        self.tray_icon.setIcon(QIcon(pixmap))
        print("[INFO] 托盘图标已创建")

    def _minimize_to_tray(self):
        """最小化到托盘"""
        self.hide()
        print("[INFO] 宠物已最小化到托盘")
        print("[INFO] 提示：点击系统托盘图标可以恢复显示")
        # 显示一个气泡提示
        if self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage(
                "桌面宠物",
                "宠物已最小化到托盘，点击图标恢复显示",
                QSystemTrayIcon.MessageIcon.Information,
                3000  # 显示3秒
            )

    def _force_show(self):
        """强制显示窗口"""
        self.show()
        self.raise_()
        self.activateWindow()
        # 重置到可见位置
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - self.pet_size - 20
        y = screen.height() - self.pet_size - 20
        self.move(x, y)
        print(f"[INFO] 强制显示宠物，位置: ({x}, {y})")

    def _on_tray_activated(self, reason):
        """托盘图标激活"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_chat()

    def _show_chat(self):
        """显示聊天窗口"""
        if not self.chat_window.isVisible():
            # 计算聊天窗口位置（在宠物上方居中）
            chat_x = self.x() - (self.chat_window.width() - self.pet_size) // 2
            chat_y = self.y() - self.chat_window.height() - 20

            # 确保不超出屏幕
            screen = QApplication.primaryScreen().geometry()
            chat_x = max(10, min(chat_x, screen.width() - self.chat_window.width() - 10))
            chat_y = max(10, chat_y)

            self.chat_window.move(chat_x, chat_y)
            self.chat_window.show()
            self.chat_window.raise_()
            self.chat_window.activateWindow()

            # 记录相对位置
            self._chat_relative_pos = (
                self.chat_window.x() - self.x(),
                self.chat_window.y() - self.y()
            )

            self.state_manager.start_talking()

    def _on_chat_window_moved(self, x, y):
        """聊天窗口移动时，更新宠物位置"""
        if self._chat_relative_pos:
            # 根据相对位置移动宠物
            new_pet_x = x - self._chat_relative_pos[0]
            new_pet_y = y - self._chat_relative_pos[1]
            self.move(new_pet_x, new_pet_y)
            # 更新拖动起始位置，避免跳跃
            self._window_start_pos = QPoint(new_pet_x, new_pet_y)

    def _on_message_sent(self, message: str):
        """用户发送消息"""
        # 检查WebSocket连接
        if not self._ws_client.is_connected():
            self.chat_window.add_message("[错误] 未连接到服务器，请检查后端是否启动", False)
            return
        
        # 发送消息到WebSocket
        self._ws_client.send_message(message)
        
        # 注意：思考状态和流式消息在收到第一个chunk或queued消息时创建
        # 这里不立即创建，避免消息排队时的显示问题
    
    def _on_ws_chunk(self, chunk: str):
        """收到WebSocket消息片段"""
        # 如果是第一个chunk，初始化流式消息
        if not self._is_streaming:
            self._is_streaming = True
            self.state_manager.start_thinking()
            self.chat_window.show_thinking()
            self._current_streaming_message = self.chat_window.add_streaming_message()
        
        if self._current_streaming_message:
            # 追加到当前流式消息
            self.chat_window.append_to_streaming_message(self._current_streaming_message, chunk)
    
    def _on_ws_complete(self, full_response: str):
        """WebSocket消息完成"""
        print("[PetWindow] WebSocket消息完成，准备切换状态")
        self._is_streaming = False
        self.chat_window.hide_thinking()
        
        if self._current_streaming_message:
            # 完成流式消息显示
            self.chat_window.finalize_streaming_message(self._current_streaming_message)
            self._current_streaming_message = None
        
        # 直接切换到对话状态（set_state会处理状态切换）
        print(f"[PetWindow] 当前状态: {self.state_manager.current_state.value}")
        self.state_manager.start_talking(5000)  # 对话状态持续5秒
        print(f"[PetWindow] 切换后状态: {self.state_manager.current_state.value}")
    
    def _on_ws_queued(self, position: int, message: str):
        """消息被加入队列"""
        # 显示排队提示
        self.chat_window.add_message(f"[系统] {message} (位置: {position})", False)
    
    def _on_ws_error(self, error: str):
        """WebSocket错误"""
        self._is_streaming = False
        self.chat_window.hide_thinking()
        self.chat_window.add_message(f"[错误] {error}", False)
        self.state_manager.stop_thinking()
        self._current_streaming_message = None
    
    def _on_ws_connected(self):
        """WebSocket连接成功"""
        print("[PetWindow] WebSocket已连接")
    
    def _on_ws_disconnected(self):
        """WebSocket断开连接"""
        print("[PetWindow] WebSocket已断开")

    def _exit_app(self):
        """退出应用"""
        # 断开WebSocket
        if self._ws_client:
            self._ws_client.disconnect()
        
        self._save_position()
        self.tray_icon.hide()
        QApplication.quit()

    # ========== 鼠标事件 ==========

    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._window_start_pos = self.frameGeometry().topLeft()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        """鼠标移动（拖动）"""
        if self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            new_pos = self._window_start_pos + delta
            self.move(new_pos)
            # 如果聊天窗口可见，同步移动聊天窗口
            if self.chat_window.isVisible() and self._chat_relative_pos:
                chat_new_x = new_pos.x() + self._chat_relative_pos[0]
                chat_new_y = new_pos.y() + self._chat_relative_pos[1]
                self.chat_window.move(chat_new_x, chat_new_y)

    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._save_position()

    def mouseDoubleClickEvent(self, event):
        """鼠标双击"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_chat()

    def _show_context_menu(self, pos):
        """显示右键菜单"""
        from PyQt6.QtCore import QPoint

        menu = QMenu(self)

        chat_action = QAction("打开对话", self)
        chat_action.triggered.connect(self._show_chat)
        menu.addAction(chat_action)

        menu.addSeparator()

        minimize_action = QAction("最小化到托盘", self)
        minimize_action.triggered.connect(self._minimize_to_tray)
        menu.addAction(minimize_action)

        menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self._exit_app)
        menu.addAction(exit_action)

        # 确保pos是QPoint类型
        if hasattr(pos, 'toPoint'):
            pos = pos.toPoint()
        menu.exec(pos)

    def closeEvent(self, event):
        """关闭事件"""
        self._save_position()
        self._exit_app()
        event.accept()


if __name__ == "__main__":
    # 测试代码
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = PetWindow()
    window.show()

    print("[PetWindow] 宠物窗口已启动")
    print("[PetWindow] 操作说明:")
    print("  - 左键拖动: 移动宠物")
    print("  - 左键双击: 打开聊天")
    print("  - 右键: 菜单")

    sys.exit(app.exec())
