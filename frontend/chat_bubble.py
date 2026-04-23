"""
聊天气泡窗口
============
QQ风格的聊天气泡窗口，支持对话历史显示。
支持拖动移动，与宠物窗口联动。

功能:
    - 气泡样式消息显示
    - 用户消息左对齐，AI回复右对齐
    - 输入框和发送按钮
    - 思考中动画
    - 可拖动移动
"""

import sys
from datetime import datetime
from typing import Optional, Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QScrollArea,
    QFrame, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QColor, QPalette, QFont, QPainter, QPainterPath


class MessageBubble(QFrame):
    """
    消息气泡组件

    显示单条消息的气泡样式，支持长文本自动换行。
    """

    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # 创建布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        # 使用 QTextEdit 替代 QLabel，更好地处理长文本
        from PyQt6.QtWidgets import QTextEdit
        self.message_text = QTextEdit()
        self.message_text.setPlainText(text)
        self.message_text.setReadOnly(True)
        self.message_text.setFrameStyle(QFrame.Shape.NoFrame)

        # 设置样式
        if is_user:
            # 用户消息 - 蓝色气泡，左对齐
            self.message_text.setStyleSheet("""
                QTextEdit {
                    background-color: #4A90D9;
                    color: white;
                    border-radius: 12px;
                    padding: 10px 15px;
                    font-size: 13px;
                    border: none;
                }
            """)
            layout.addWidget(self.message_text)
            layout.addStretch()
        else:
            # AI消息 - 灰色气泡，右对齐
            self.message_text.setStyleSheet("""
                QTextEdit {
                    background-color: #F0F0F0;
                    color: #333333;
                    border-radius: 12px;
                    padding: 10px 15px;
                    font-size: 13px;
                    border: none;
                }
            """)
            layout.addStretch()
            layout.addWidget(self.message_text)

        # 设置最大宽度（留出边距避免超出窗口）
        self.message_text.setMaximumWidth(260)
        self.message_text.setMinimumWidth(80)

        # 自适应高度
        self.message_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 计算并设置合适的高度
        # 考虑样式表中的 padding: 10px 15px（垂直padding 20px，水平padding 30px）
        doc = self.message_text.document()
        doc.setTextWidth(220)  # 260 - 30(水平padding) - 10(边距)
        height = doc.size().height() + 22  # 加上垂直padding 20px + 2px缓冲
        self.message_text.setFixedHeight(int(height))


class ChatBubbleWindow(QWidget):
    """
    聊天气泡窗口

    主聊天窗口，包含消息历史和输入区域。
    支持拖动移动，与宠物窗口联动。
    """

    # 信号
    message_sent = pyqtSignal(str)  # 用户发送消息
    window_closed = pyqtSignal()     # 窗口关闭
    window_moved = pyqtSignal(int, int)  # 窗口移动信号 (x, y)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(380, 500)
        self.setMaximumSize(500, 700)

        self._is_thinking = False
        self._thinking_dots = 0

        # 拖动相关
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._window_start_pos = QPoint()

        self._setup_ui()
        self._setup_styles()

    def _setup_ui(self):
        """初始化UI"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # 标题栏（可拖动区域）
        title_layout = QHBoxLayout()
        self.title_label = QLabel("和宠物聊天")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #333333;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        # 标题栏支持拖动
        self.title_label.setCursor(Qt.CursorShape.OpenHandCursor)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        # 关闭按钮
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(25, 25)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.hide)
        title_layout.addWidget(self.close_btn)

        main_layout.addLayout(title_layout)

        # 消息区域（滚动）
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: rgba(255, 255, 255, 0.95);
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #CCCCCC;
                border-radius: 4px;
                min-height: 30px;
            }
        """)

        # 消息容器
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.messages_layout.setSpacing(8)
        self.messages_layout.setContentsMargins(5, 5, 5, 5)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        main_layout.addWidget(self.scroll_area)

        # 思考中标签
        self.thinking_label = QLabel("思考中")
        self.thinking_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thinking_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 12px;
                padding: 5px;
            }
        """)
        self.thinking_label.hide()
        main_layout.addWidget(self.thinking_label)

        # 输入区域
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入消息...")
        self.input_field.setMinimumHeight(35)
        self.input_field.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedSize(60, 35)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        main_layout.addLayout(input_layout)

        # 思考动画定时器
        self._thinking_timer = QTimer(self)
        self._thinking_timer.timeout.connect(self._update_thinking_animation)

    def _setup_styles(self):
        """设置窗口样式"""
        self.setStyleSheet("""
            QWidget {
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
            }
            QLineEdit {
                border: 2px solid #E0E0E0;
                border-radius: 18px;
                padding: 5px 15px;
                font-size: 13px;
                background-color: white;
                color: #333333;
            }
            QLineEdit:focus {
                border-color: #4A90D9;
                color: #333333;
            }
            QPushButton {
                background-color: #4A90D9;
                color: white;
                border: none;
                border-radius: 17px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3A7BC8;
            }
            QPushButton:pressed {
                background-color: #2A6BB8;
            }
            QPushButton#close_btn {
                background-color: transparent;
                color: #888888;
                font-size: 18px;
            }
            QPushButton#close_btn:hover {
                color: #FF4444;
            }
        """)
        self.close_btn.setObjectName("close_btn")

    def paintEvent(self, event):
        """绘制圆角背景"""
        from PyQt6.QtCore import QRectF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制白色圆角背景
        path = QPainterPath()
        # 使用QRectF替代QRect
        rect = QRectF(self.rect())
        path.addRoundedRect(rect, 15, 15)
        painter.fillPath(path, QColor(255, 255, 255, 245))

        # 绘制边框
        painter.setPen(QColor(200, 200, 200, 150))
        painter.drawPath(path)

        super().paintEvent(event)

    def mousePressEvent(self, event):
        """鼠标按下 - 支持拖动"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否在标题栏区域
            if event.position().y() < 40:  # 标题栏高度约40像素
                self._dragging = True
                self._drag_start_pos = event.globalPosition().toPoint()
                self._window_start_pos = self.frameGeometry().topLeft()
                self.title_label.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖动窗口"""
        if self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            new_pos = self._window_start_pos + delta
            self.move(new_pos)
            # 发射移动信号，通知宠物窗口跟随
            self.window_moved.emit(new_pos.x(), new_pos.y())

    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.title_label.setCursor(Qt.CursorShape.OpenHandCursor)

    def _send_message(self):
        """发送消息"""
        text = self.input_field.text().strip()
        if text:
            self.add_message(text, True)
            self.input_field.clear()
            self.message_sent.emit(text)

    def add_message(self, text: str, is_user: bool) -> 'MessageBubble':
        """
        添加消息到聊天窗口

        Args:
            text: 消息内容
            is_user: 是否用户发送
        
        Returns:
            消息气泡组件
        """
        bubble = MessageBubble(text, is_user)
        # 插入到 stretch 之前
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1,
            bubble
        )

        # 滚动到底部
        QTimer.singleShot(100, self._scroll_to_bottom)
        
        return bubble
    
    def add_streaming_message(self) -> 'MessageBubble':
        """
        添加一个流式消息（用于接收片段）
        
        Returns:
            消息气泡组件
        """
        bubble = MessageBubble("", False)
        # 插入到 stretch 之前
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1,
            bubble
        )
        
        # 滚动到底部
        QTimer.singleShot(100, self._scroll_to_bottom)
        
        return bubble
    
    def append_to_streaming_message(self, bubble: 'MessageBubble', chunk: str):
        """
        追加内容到流式消息
        
        Args:
            bubble: 消息气泡组件
            chunk: 要追加的文本片段
        """
        if bubble and bubble.message_text:
            current_text = bubble.message_text.toPlainText()
            bubble.message_text.setPlainText(current_text + chunk)
            
            # 更新高度（使用与初始化一致的参数）
            doc = bubble.message_text.document()
            doc.setTextWidth(220)  # 与初始化一致
            height = doc.size().height() + 22
            bubble.message_text.setFixedHeight(int(height))
            
            # 滚动到底部
            self._scroll_to_bottom()
    
    def finalize_streaming_message(self, bubble: 'MessageBubble'):
        """
        完成流式消息显示
        
        Args:
            bubble: 消息气泡组件
        """
        if bubble:
            # 最终调整高度（使用与初始化一致的参数）
            doc = bubble.message_text.document()
            doc.setTextWidth(220)  # 与初始化一致
            height = doc.size().height() + 22
            bubble.message_text.setFixedHeight(int(height))

    def _scroll_to_bottom(self):
        """滚动到最新消息"""
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def show_thinking(self):
        """显示思考中动画"""
        self._is_thinking = True
        self._thinking_dots = 0
        self.thinking_label.show()
        self._thinking_timer.start(500)
        # 只禁用发送按钮，不禁用输入框，让用户可以继续输入
        self.send_btn.setEnabled(False)
        # 输入框保持启用，但显示提示
        self.input_field.setPlaceholderText("AI正在回答，可以继续输入...")

    def hide_thinking(self):
        """隐藏思考中动画"""
        self._is_thinking = False
        self._thinking_timer.stop()
        self.thinking_label.hide()
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.input_field.setPlaceholderText("输入消息...")
        self.input_field.setFocus()

    def _update_thinking_animation(self):
        """更新思考动画"""
        self._thinking_dots = (self._thinking_dots + 1) % 4
        dots = "." * self._thinking_dots
        self.thinking_label.setText(f"思考中{dots}")

    def clear_messages(self):
        """清空所有消息"""
        while self.messages_layout.count() > 1:  # 保留 stretch
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def closeEvent(self, event):
        """关闭事件"""
        self.window_closed.emit()
        event.ignore()
        self.hide()


if __name__ == "__main__":
    # 测试代码
    app = QApplication(sys.argv)
    window = ChatBubbleWindow()
    window.show()

    # 添加测试消息
    window.add_message("你好!", True)
    window.add_message("你好呀!我是你的桌面宠物,很高兴见到你~", False)

    sys.exit(app.exec())
