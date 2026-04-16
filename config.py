"""
Config Module
=============
统一从 .env 文件加载所有配置，并根据 PROVIDER 构建对应的 LangChain LLM 实例。

支持的 Provider：
  openai     → ChatOpenAI (api.openai.com)
  deepseek   → ChatOpenAI + base_url (api.deepseek.com)
  kimi       → ChatOpenAI + base_url (api.moonshot.cn/v1)
  minimax    → ChatOpenAI + base_url (api.minimax.chat/v1)
  qwen       → ChatOpenAI + base_url (dashscope.aliyuncs.com/...)
  glm        → ChatOpenAI + base_url (open.bigmodel.cn/...)

用法：
  from config import get_llm, MAIN_MODEL, MEMORY_MODEL, MAX_STEPS
  llm = get_llm(MAIN_MODEL)
"""

import os
from pathlib import Path

# ── 加载 .env ──────────────────────────────────────────────────────
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    with open(_env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key not in os.environ:
                os.environ[key] = value

# ── 读取配置项 ─────────────────────────────────────────────────────
PROVIDER: str = os.environ.get("PROVIDER", "openai").lower()

OPENAI_COMPATIBLE_API_KEY: str = os.environ.get("OPENAI_COMPATIBLE_API_KEY", "")
OPENAI_COMPATIBLE_BASE_URL: str = os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "")

MAIN_MODEL: str = os.environ.get("MAIN_MODEL", "gpt-4o")
MEMORY_MODEL: str = os.environ.get("MEMORY_MODEL", "gpt-4o-mini")
RERANK_MODEL: str = os.environ.get("RERANK_MODEL", "gpt-4o-mini")  # 专门用于Rerank重排序的模型
MAX_STEPS: int = int(os.environ.get("MAX_STEPS", "10"))

# 记忆系统重排序配置
MEMORY_SIMILARITY_THRESHOLD: float = float(os.environ.get("MEMORY_SIMILARITY_THRESHOLD", "0.5"))
USE_LLM_RERANK: bool = os.environ.get("USE_LLM_RERANK", "false").lower() == "true"

# OpenAI 兼容 provider 的默认 base_url
_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai":   "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "kimi":     "https://api.moonshot.cn/v1",
    "minimax":  "https://api.minimax.chat/v1",
    "qwen":     "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm":      "https://open.bigmodel.cn/api/paas/v4",
    "xiaomi":   "https://api.xiaomimimo.com/v1"
}


# ── LLM 工厂函数 ───────────────────────────────────────────────────
def get_llm(model: str):
    """
    根据 PROVIDER 返回对应的 LangChain LLM 实例。

    Args:
        model: 模型名，从 MAIN_MODEL 或 MEMORY_MODEL 传入

    Returns:
        LangChain BaseChatModel 实例
    """
    from langchain_openai import ChatOpenAI

    # base_url 优先用 .env 里的显式配置，没有则用内置默认值
    base_url = (
        OPENAI_COMPATIBLE_BASE_URL
        or _DEFAULT_BASE_URLS.get(PROVIDER, "")
    )

    if not base_url:
        raise ValueError(
            f"Unknown provider '{PROVIDER}'. "
            f"Please set OPENAI_COMPATIBLE_BASE_URL in .env, "
            f"or use one of: {list(_DEFAULT_BASE_URLS.keys())}"
        )

    return ChatOpenAI(
        model=model,
        api_key=OPENAI_COMPATIBLE_API_KEY,
        base_url=base_url,
    )


# ── 启动校验 ───────────────────────────────────────────────────────
def validate():
    """启动时校验必填配置，缺失则提前报错并给出提示"""
    if not OPENAI_COMPATIBLE_API_KEY:
        raise EnvironmentError(
            f"\n❌ OPENAI_COMPATIBLE_API_KEY is not set (provider={PROVIDER}).\n"
            f"   Edit .env: OPENAI_COMPATIBLE_API_KEY=your_key_here\n"
        )
    base_url = OPENAI_COMPATIBLE_BASE_URL or _DEFAULT_BASE_URLS.get(PROVIDER, "")
    if not base_url:
        raise EnvironmentError(
            f"\n❌ Cannot resolve base_url for provider '{PROVIDER}'.\n"
            f"   Edit .env: OPENAI_COMPATIBLE_BASE_URL=https://...\n"
        )

    # 检查 langchain-openai 是否安装
    try:
        import langchain_openai  # noqa: F401
    except ImportError:
        raise ImportError(
            "\n❌ langchain-openai is not installed.\n"
            "   Run: pip install langchain-openai\n"
        )
