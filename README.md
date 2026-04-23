# 桌面宠物 - 带记忆的AI聊天助手

一个类似QQ宠物的悬浮桌面宠物，支持带记忆的AI对话功能。

## 功能特性

- **悬浮宠物**: 无边框透明窗口，常驻桌面右下角
- **鼠标交互**: 支持拖动、双击打开聊天、右键菜单
- **聊天气泡**: QQ风格的气泡对话界面
- **AI记忆**: 基于LangGraph的双层记忆系统（短期+长期）
- **系统托盘**: 最小化到托盘，随时唤起

## 项目结构

```
myagent/
├── backend/                    # FastAPI 后端
│   ├── api_server.py          # API服务主文件
│   └── __init__.py
├── frontend/                   # PyQt6 前端
│   ├── main.py                # 前端入口
│   ├── pet_window.py          # 宠物主窗口
│   ├── chat_bubble.py         # 聊天气泡窗口
│   ├── pet_state.py           # 状态管理
│   └── assets/                # 资源文件
│       └── pet.svg            # 宠物图片
├── memory/                    # 记忆系统（已有）
├── harness.py                 # AI核心（已有）
├── config.py                  # 配置（已有）
├── start_backend.py           # 后端启动脚本
├── start_frontend.py          # 前端启动脚本
├── start_all.py               # 一键启动全部
├── requirements.txt           # 依赖
└── README.md                  # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API密钥

确保 `.env` 文件已配置：

```
PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_api_key_here
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
MAIN_MODEL=deepseek-chat
MEMORY_MODEL=deepseek-chat
```

### 3. 启动服务

#### 方式一：一键启动（推荐）

```bash
python start_all.py
```

#### 方式二：分别启动

**启动后端：**
```bash
python start_backend.py
```

**启动前端（在另一个终端）：**
```bash
python start_frontend.py
```

## 使用说明

### 宠物交互

| 操作 | 功能 |
|------|------|
| 左键拖动 | 移动宠物位置 |
| 左键双击 | 打开聊天窗口 |
| 右键点击 | 显示菜单（对话/最小化/退出） |
| 托盘图标 | 右键显示/隐藏 |

### 状态指示

- **绿色圆点**: 空闲状态
- **黄色圆点**: 思考中
- **蓝色圆点**: 对话中

### 聊天功能

1. 双击宠物或点击"打开对话"打开聊天窗口
2. 在输入框输入消息，按回车或点击发送
3. 等待AI回复（显示"思考中..."动画）
4. 对话历史会自动保存到记忆系统

## API接口

### POST /api/chat

请求：
```json
{
    "message": "你好",
    "user_id": "default"
}
```

响应：
```json
{
    "response": "你好！很高兴见到你~",
    "status": "success",
    "error": null
}
```

### GET /health

健康检查：
```json
{
    "status": "healthy",
    "harness_ready": true
}
```

## 自定义宠物图片

将 `pet.png` 放入 `frontend/assets/` 目录即可替换默认宠物形象。

图片要求：
- 格式：PNG（支持透明背景）
- 尺寸：建议 256x256 像素
- 风格：圆形或方形都可以

## 技术栈

- **前端**: Python + PyQt6
- **后端**: Python + FastAPI
- **通信**: HTTP POST JSON API
- **AI**: LangGraph + LangChain
- **记忆**: ChromaDB 向量数据库

## 跨平台支持

- Windows: 完全支持
- macOS: 需要安装 PyQt6
- Linux: 需要安装 PyQt6 和 X11 支持

## 常见问题

### Q: 启动报错 "No module named 'PyQt6'"

A: 安装 PyQt6：
```bash
pip install PyQt6
```

### Q: 后端启动失败 "OPENAI_COMPATIBLE_API_KEY is not set"

A: 检查 `.env` 文件是否存在并包含API密钥

### Q: 前端无法连接到后端

A: 确保后端已启动并运行在 http://127.0.0.1:8000

### Q: 宠物窗口不显示

A: 检查是否有其他窗口遮挡，或查看系统托盘图标

## 更新日志

### v1.0.0 (2026-04-22)
- 初始版本发布
- 实现悬浮宠物窗口
- 实现聊天气泡界面
- 集成AI记忆系统
- 支持系统托盘

## License

MIT License
