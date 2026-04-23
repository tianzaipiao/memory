"""
宠物状态管理模块
================
管理宠物的各种状态和动画。

状态:
    - IDLE: 空闲状态
    - THINKING: 思考中
    - TALKING: 对话中
"""

from enum import Enum, auto
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class PetState(Enum):
    """宠物状态枚举"""
    IDLE = "idle"           # 空闲
    THINKING = "thinking"   # 思考中
    TALKING = "talking"     # 对话中


class PetStateManager(QObject):
    """
    宠物状态管理器

    管理宠物的当前状态，并提供状态切换信号。
    """

    # 状态变化信号
    state_changed = pyqtSignal(PetState)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = PetState.IDLE
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._on_state_timeout)

    @property
    def current_state(self) -> PetState:
        """获取当前状态"""
        return self._state

    def set_state(self, state: PetState, duration_ms: int = 0):
        """
        设置宠物状态

        Args:
            state: 目标状态
            duration_ms: 状态持续时间（毫秒），0表示永久
        """
        if self._state != state:
            self._state = state
            self.state_changed.emit(state)
            print(f"[PetState] 状态切换: {state.value}")

        # 设置自动恢复定时器
        self._state_timer.stop()
        if duration_ms > 0 and state != PetState.IDLE:
            self._state_timer.start(duration_ms)

    def _on_state_timeout(self):
        """状态超时，恢复到空闲"""
        self._state_timer.stop()
        if self._state != PetState.IDLE:
            self.set_state(PetState.IDLE)

    def start_thinking(self):
        """开始思考（无超时，需手动结束）"""
        self.set_state(PetState.THINKING)

    def stop_thinking(self):
        """结束思考，恢复空闲"""
        # 无论当前是什么状态，都强制恢复到空闲
        self.set_state(PetState.IDLE)

    def start_talking(self, duration_ms: int = 3000):
        """
        开始对话

        Args:
            duration_ms: 对话状态持续时间，默认3秒
        """
        self.set_state(PetState.TALKING, duration_ms)

    def is_idle(self) -> bool:
        """是否空闲"""
        return self._state == PetState.IDLE

    def is_thinking(self) -> bool:
        """是否思考中"""
        return self._state == PetState.THINKING

    def is_talking(self) -> bool:
        """是否对话中"""
        return self._state == PetState.TALKING
