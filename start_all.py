"""
一键启动全部服务
================
同时启动后端API和前端桌面宠物

用法:
    python start_all.py
"""

import sys
import os
import subprocess
import time
import signal
from pathlib import Path


def start_backend():
    """启动后端服务"""
    print("=" * 55)
    print("启动后端API服务...")
    print("=" * 55)

    # 使用subprocess启动后端
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "backend.api_server"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
    )

    return backend_process


def start_frontend():
    """启动前端"""
    print("=" * 55)
    print("启动桌面宠物...")
    print("=" * 55)

    # 使用subprocess启动前端
    frontend_process = subprocess.Popen(
        [sys.executable, "-m", "frontend.main"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
    )

    return frontend_process


def main():
    """主函数"""
    print("\n" + "=" * 55)
    print("  桌面宠物 - 一键启动")
    print("=" * 55 + "\n")

    backend_process = None
    frontend_process = None

    try:
        # 启动后端
        backend_process = start_backend()
        print(f"后端进程PID: {backend_process.pid}")

        # 等待后端启动
        print("等待后端启动...")
        time.sleep(3)

        # 启动前端
        frontend_process = start_frontend()
        print(f"前端进程PID: {frontend_process.pid}")

        print("\n" + "=" * 55)
        print("  所有服务已启动！")
        print("=" * 55)
        print("\n操作说明:")
        print("  • 后端API运行在: http://127.0.0.1:8000")
        print("  • 前端宠物已显示在桌面")
        print("  • 按 Ctrl+C 停止所有服务")
        print("=" * 55 + "\n")

        # 等待中断
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n正在停止服务...")

        if frontend_process:
            frontend_process.terminate()
            print(f"前端进程 {frontend_process.pid} 已停止")

        if backend_process:
            backend_process.terminate()
            print(f"后端进程 {backend_process.pid} 已停止")

        print("\n所有服务已停止")


if __name__ == "__main__":
    main()
