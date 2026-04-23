"""
前端启动脚本
============
一键启动PyQt6桌面宠物客户端
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from frontend.main import main

if __name__ == "__main__":
    main()
