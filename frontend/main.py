"""
桌面宠物主程序入口
==================
启动桌面宠物客户端。

用法:
    python -m frontend.main
    python -m frontend.main --reset-position  # 重置位置到屏幕右下角
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from frontend.pet_window import PetWindow


def main():
    """主函数"""
    # 检查是否需要重置位置
    reset_position = "--reset-position" in sys.argv
    if reset_position:
        # 删除位置文件
        settings_file = Path.home() / ".pet_desktop" / "position.txt"
        if settings_file.exists():
            try:
                settings_file.unlink()
                print("[INFO] 已重置位置设置")
            except Exception as e:
                print(f"[WARNING] 无法删除位置文件: {e}")
        sys.argv.remove("--reset-position")

    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("桌面宠物")
    app.setApplicationVersion("1.0.0")

    # 设置应用不随最后一个窗口关闭而退出（因为有托盘图标）
    app.setQuitOnLastWindowClosed(False)

    print("=" * 55)
    print("  桌面宠物客户端启动中...")
    print("=" * 55)

    # 检查屏幕信息
    screen = QApplication.primaryScreen()
    print(f"[INFO] 屏幕: {screen.name()}")
    print(f"[INFO] 分辨率: {screen.size().width()}x{screen.size().height()}")
    print(f"[INFO] 可用区域: {screen.availableGeometry().width()}x{screen.availableGeometry().height()}")

    # 创建宠物窗口
    try:
        pet = PetWindow()
        pet.show()

        print(f"\n[INFO] 宠物窗口位置: ({pet.x()}, {pet.y()})")
        print(f"[INFO] 宠物窗口大小: {pet.width()}x{pet.height()}")
        print(f"[INFO] 宠物窗口可见: {pet.isVisible()}")

        print("\n✅ 宠物窗口已启动！")
        print("\n操作说明:")
        print("  • 左键拖动  - 移动宠物位置")
        print("  • 左键双击  - 打开聊天窗口")
        print("  • 右键点击  - 显示菜单")
        print("  • 托盘图标  - 右键可显示/隐藏")
        print("\n注意: 请确保后端API服务已启动")
        print("      启动命令: python -m backend.api_server")
        print("=" * 55)

        # 运行应用
        sys.exit(app.exec())

    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
