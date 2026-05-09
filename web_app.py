"""
API Model Tester - Web Application
FastAPI backend with SSE streaming for real-time results
Supports dynamic model list from config file and OpenRouter sync
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="API Model Tester")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Config file path
CONFIG_FILE = Path(__file__).parent / "models.json"

# Default models if config file doesn't exist
DEFAULT_CHAT_MODELS = [
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
    "claude-3-5-sonnet-20241022", "claude-3-opus-20240229",
    "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash",
    "deepseek-chat", "deepseek-reasoner",
]

DEFAULT_IMAGE_MODELS = ["dall-e-3", "dall-e-2", "gpt-image-1", "gpt-image-2"]


def load_models():
    """Load models from config file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return (
                data.get("chat_models", DEFAULT_CHAT_MODELS),
                data.get("image_models", DEFAULT_IMAGE_MODELS),
            )
    return DEFAULT_CHAT_MODELS, DEFAULT_IMAGE_MODELS


def save_models(chat_models: list, image_models: list):
    """Save models to config file."""
    data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "source": "openrouter",
        "chat_models": chat_models,
        "image_models": image_models,
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# Load models at startup
CHAT_MODELS, IMAGE_MODELS = load_models()


async def sync_from_openrouter() -> dict:
    """Sync models from OpenRouter API."""
    url = "https://openrouter.ai/api/v1/models"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return {"success": False, "error": f"HTTP {response.status}"}

                data = await response.json()
                models = data.get("data", [])

                # Filter and categorize models
                chat_models = set()
                image_models = set()

                # Popular prefixes to include
                popular_prefixes = [
                    "openai/", "anthropic/", "google/", "meta-llama/",
                    "deepseek/", "qwen/", "mistral/", "01-ai/",
                    "moonshot", "baichuan/", "thududin/",
                ]

                for model in models:
                    model_id = model.get("id", "")
                    model_name = model.get("name", "").lower()

                    # Check if it's an image model
                    if any(x in model_id for x in ["dall-e", "stable-diffusion", "midjourney", "imagen", "gpt-image", "image"]):
                        image_models.add(model_id)
                    else:
                        # Include popular models
                        if any(model_id.startswith(prefix) for prefix in popular_prefixes):
                            chat_models.add(model_id)

                # Also add some commonly used short names
                short_names = [
                    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
                    "claude-3-5-sonnet-20241022", "claude-3-opus-20240229",
                    "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash",
                    "deepseek-chat", "deepseek-reasoner", "deepseek-v3", "deepseek-r1",
                    "dall-e-3", "dall-e-2",
                ]
                for name in short_names:
                    if name not in chat_models and name not in image_models:
                        if any(x in name for x in ["dall", "image", "diffusion"]):
                            image_models.add(name)
                        else:
                            chat_models.add(name)

                # Sort and save
                chat_list = sorted(chat_models)
                image_list = sorted(image_models)
                save_models(chat_list, image_list)

                global CHAT_MODELS, IMAGE_MODELS
                CHAT_MODELS = chat_list
                IMAGE_MODELS = image_list

                return {
                    "success": True,
                    "chat_count": len(chat_list),
                    "image_count": len(image_list),
                }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_model_name_variants(model: str) -> list[str]:
    """
    生成模型名称的多种变体形式，用于测速重试。

    示例:
    - google/gemini-2.5-flash -> [google/gemini-2.5-flash, gemini-2.5-flash]
    - openai/gpt-4o -> [openai/gpt-4o, gpt-4o]
    - gpt-4o -> [gpt-4o]  (无前缀，无需变体)
    """
    variants = [model]

    if "/" in model:
        short_name = model.split("/", 1)[1]
        variants.append(short_name)

    return variants


def normalize_model_name(model: str) -> str:
    """
    标准化模型名称，去掉前缀。
    用于去重：google/gemini-2.5-flash 和 gemini-2.5-flash 视为同一模型。
    """
    if "/" in model:
        return model.split("/", 1)[1]
    return model


# 全局缓存：记录成功的URL路径格式
URL_PATH_CACHE: dict[str, str] = {}  # {base_url: successful_path_suffix}


# 平台规则配置：各聚合平台的URL格式规则
PLATFORM_RULES = {
    "tencent_codingplan": {
        "patterns": ["api.lkeap.cloud.tencent.com/coding"],
        "openai_suffix": "/v3",
        "anthropic_suffix": "/anthropic",
        "model_list_endpoint": "/v3/models",
        "cross_format": True,
        "format_detection": {
            "openai": ["/v3"],
            "anthropic": ["/anthropic"],
        },
    },
    "anthropic_official": {
        "patterns": ["api.anthropic.com"],
        "anthropic_suffix": "/v1/messages",
        "no_model_list_api": True,
        "default_models": [
            "claude-3-haiku-20240307",
            "claude-3-sonnet-20240229",
            "claude-3-opus-20240229",
            "claude-3-5-haiku-20241022",
            "claude-3-5-sonnet-20241022",
            "claude-3-7-sonnet-20250219",
            "claude-opus-4-20250514",
        ],
    },
    "openai_official": {
        "patterns": ["api.openai.com"],
        "openai_suffix": "/v1/chat/completions",
        "model_list_endpoint": "/v1/models",
    },
    "deepseek": {
        "patterns": ["api.deepseek.com"],
        "openai_suffix": "/v1/chat/completions",
        "model_list_endpoint": "/v1/models",
    },
    "groq": {
        "patterns": ["api.groq.com"],
        "openai_suffix": "/openai/v1/chat/completions",
        "model_list_endpoint": "/openai/v1/models",
    },
    "openrouter": {
        "patterns": ["openrouter.ai"],
        "openai_suffix": "/api/v1/chat/completions",
        "model_list_endpoint": "/api/v1/models",
    },
    "moonshot": {
        "patterns": ["api.moonshot.cn"],
        "openai_suffix": "/v1/chat/completions",
        "model_list_endpoint": "/v1/models",
    },
    "zhipu": {
        "patterns": ["open.bigmodel.cn"],
        "openai_suffix": "/api/paas/v4/chat/completions",
        "model_list_endpoint": "/api/paas/v4/models",
    },
    "volces_codingplan": {
        "patterns": ["ark.cn-beijing.volces.com/api/coding"],
        "anthropic_suffix": "/v1/messages",
        "openai_suffix": "/v3/chat/completions",
        "model_list_endpoint": "/v3/models",
        "cross_format": True,
        "format_detection": {
            "openai": ["/v3"],
            "anthropic": [],
        },
    },
}


def detect_platform(base_url: str) -> str | None:
    """根据URL检测平台类型"""
    for platform, rules in PLATFORM_RULES.items():
        for pattern in rules.get("patterns", []):
            if pattern in base_url:
                return platform
    return None


def detect_format_from_url(base_url: str, platform: str) -> str | None:
    """根据平台规则从 URL 判断 API 格式"""
    rules = PLATFORM_RULES.get(platform, {})
    detection = rules.get("format_detection")
    if not detection:
        return rules.get("default_format")

    base = base_url.rstrip('/')

    # 检查 OpenAI 模式
    for pattern in detection.get("openai", []):
        if pattern and pattern in base:
            return "openai"

    # 检查 Anthropic 模式
    for pattern in detection.get("anthropic", []):
        if pattern and pattern in base:
            return "anthropic"

    # 如果有 format_detection 但没匹配到明确模式
    # 聚合平台通常：含 openai 模式 → 已检测，否则看 anthropic 是否为空
    if detection.get("anthropic") == []:
        return "anthropic"

    return None


def build_model_list_urls(base_url: str) -> list[str]:
    """生成可能的模型列表API URL"""
    base = base_url.rstrip('/')
    return [
        f"{base}/models",
        f"{base}/v1/models",
        f"{base}/api/v1/models",
        f"{base}/openai/v1/models",
    ]


async def fetch_platform_models(base_url: str, api_key: str) -> list[str]:
    """从用户指定的平台获取模型列表，使用平台规则"""
    import aiohttp

    async def fetch_from_url(url: str, headers: dict) -> list[str]:
        """从指定URL获取模型列表"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get("data", [])
                        return [m.get("id") for m in models if m.get("id")]
        except Exception:
            pass
        return []

    headers = {"Authorization": f"Bearer {api_key}"}
    base = base_url.rstrip('/')
    platform = detect_platform(base_url)

    # 1. 如果平台没有模型列表API，返回默认模型
    if platform:
        rules = PLATFORM_RULES.get(platform, {})
        if rules.get("no_model_list_api"):
            return rules.get("default_models", [])

        # 2. 使用平台指定的模型列表endpoint
        if rules.get("model_list_endpoint"):
            endpoint = rules["model_list_endpoint"]
            # 如果URL已经有suffix，需要替换
            if rules.get("openai_suffix") and base.endswith(rules["openai_suffix"]):
                model_url = base + endpoint
            elif rules.get("anthropic_suffix") and base.endswith(rules["anthropic_suffix"]):
                # 跨格式：从OpenAI格式获取模型列表
                if rules.get("cross_format"):
                    openai_base = base.replace(rules["anthropic_suffix"], rules["openai_suffix"])
                    model_url = openai_base + endpoint
                else:
                    model_url = base + endpoint
            else:
                model_url = base + endpoint

            models = await fetch_from_url(model_url, headers)
            if models:
                return models

    # 3. 通用探测：尝试常见的模型列表URL
    urls = build_model_list_urls(base_url)
    # DEBUG
    import json
    print(f"[DEBUG] Trying URLs: {urls}")
    for url in urls:
        models = await fetch_from_url(url, headers)
        print(f"[DEBUG] URL {url} returned: {models[:3] if models else 'empty'}...")
        if models:
            return models

    # 4. 跨格式探测：尝试同平台其他格式的endpoint
    if platform:
        rules = PLATFORM_RULES.get(platform, {})
        if rules.get("cross_format") and rules.get("anthropic_suffix") and rules.get("openai_suffix"):
            if base.endswith(rules["anthropic_suffix"]):
                openai_base = base.replace(rules["anthropic_suffix"], rules["openai_suffix"])
                openai_urls = build_model_list_urls(openai_base)
                for url in openai_urls:
                    models = await fetch_from_url(url, headers)
                    if models:
                        return models

    return []


def build_api_urls(base_url: str, endpoint: str) -> list[str]:
    """
    生成多种可能的API URL，用于探测。
    返回按优先级排序的URL列表。
    """
    base = base_url.rstrip('/')
    urls = []

    # 1. 检查缓存中是否有成功的路径
    cached_path = URL_PATH_CACHE.get(base_url)
    if cached_path:
        urls.append(f"{base}{cached_path}")

    # 2. 用户已提供完整路径
    if base.endswith(f"/{endpoint}") or base.endswith("/messages"):
        if base not in urls:
            urls.append(base)
        return urls

    # 3. 尝试不同的路径组合（按常见程度排序）
    path_variants = [
        f"/v1/{endpoint}",          # 标准OpenAI格式
        f"/{endpoint}",              # 直接加路径（腾讯v3等）
        f"/openai/v1/{endpoint}",    # Groq格式
        f"/api/v1/{endpoint}",       # OpenRouter格式
        f"/v2/{endpoint}",           # 某些平台用v2
        f"/v3/{endpoint}",           # 腾讯云等
    ]

    for path in path_variants:
        url = f"{base}{path}"
        if url not in urls:
            urls.append(url)

    return urls


async def _test_single_chat_model(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    model: str,
    start_time: float,
) -> dict:
    """Test a single model variant with URL path detection."""
    urls = build_api_urls(base_url, "chat/completions")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
    }

    last_result = None
    for url in urls:
        try:
            async with session.post(
                url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                raw_data = await response.read()
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                try:
                    result = json.loads(raw_data)
                except json.JSONDecodeError:
                    text = raw_data.decode("utf-8", errors="replace")
                    last_result = {
                        "model": model,
                        "type": "chat",
                        "available": False,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": f"HTTP {response.status}: {text[:100]}",
                    }
                    # 404说明路径不对，尝试下一个
                    if response.status == 404:
                        continue
                    return last_result

                if "error" in result:
                    # 标准OpenAI错误格式
                    error_obj = result["error"]
                    if isinstance(error_obj, dict):
                        error_msg = error_obj.get("message", "Unknown error")
                    else:
                        error_msg = str(error_obj)
                    last_result = {
                        "model": model,
                        "type": "chat",
                        "available": False,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": error_msg,
                    }
                    return last_result

                # 处理其他错误格式
                if "msg" in result:
                    last_result = {
                        "model": model,
                        "type": "chat",
                        "available": False,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": result.get("msg", "Unknown error"),
                    }
                    return last_result

                if "message" in result and "choices" not in result:
                    last_result = {
                        "model": model,
                        "type": "chat",
                        "available": False,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": result.get("message", "Unknown error"),
                    }
                    return last_result

                if "choices" in result and len(result["choices"]) > 0:
                    # 成功！缓存这个URL路径
                    URL_PATH_CACHE[base_url] = url.replace(base_url, "")
                    return {
                        "model": model,
                        "type": "chat",
                        "available": True,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": None,
                    }

                last_result = {
                    "model": model,
                    "type": "chat",
                    "available": False,
                    "response_time_ms": round(elapsed_ms, 0),
                    "error": "No choices in response",
                }

        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            last_result = {
                "model": model,
                "type": "chat",
                "available": False,
                "response_time_ms": round(elapsed_ms, 0),
                "error": "Timeout (>30s)",
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            last_result = {
                "model": model,
                "type": "chat",
                "available": False,
                "response_time_ms": round(elapsed_ms, 0),
                "error": str(e),
            }

    return last_result if last_result else {
        "model": model,
        "type": "chat",
        "available": False,
        "response_time_ms": 0,
        "error": "All URL paths failed",
    }


async def _test_single_anthropic_model(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    model: str,
    start_time: float,
) -> dict:
    """Test a single model using Anthropic format."""
    url = f"{base_url.rstrip('/')}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "hi"}],
    }

    try:
        async with session.post(
            url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            raw_data = await response.read()
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            try:
                result = json.loads(raw_data)
            except json.JSONDecodeError:
                text = raw_data.decode("utf-8", errors="replace")
                return {
                    "model": model,
                    "type": "chat",
                    "available": False,
                    "response_time_ms": round(elapsed_ms, 0),
                    "error": f"HTTP {response.status}: {text[:100]}",
                }

            # Anthropic响应格式: {"type": "message", "content": [...]}
            if "type" in result and result["type"] == "message":
                if "content" in result and len(result["content"]) > 0:
                    return {
                        "model": model,
                        "type": "chat",
                        "available": True,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": None,
                    }

            if "error" in result:
                return {
                    "model": model,
                    "type": "chat",
                    "available": False,
                    "response_time_ms": round(elapsed_ms, 0),
                    "error": result["error"].get("message", "Unknown error"),
                }

            return {
                "model": model,
                "type": "chat",
                "available": False,
                "response_time_ms": round(elapsed_ms, 0),
                "error": "Unexpected response format",
            }

    except asyncio.TimeoutError:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return {
            "model": model,
            "type": "chat",
            "available": False,
            "response_time_ms": round(elapsed_ms, 0),
            "error": "Timeout (>30s)",
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return {
            "model": model,
            "type": "chat",
            "available": False,
            "response_time_ms": round(elapsed_ms, 0),
            "error": str(e),
        }


async def detect_api_format(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
) -> str:
    """
    探测API格式，返回 "openai" 或 "anthropic"
    """
    # 0. 优先使用平台规则的 URL 模式匹配
    platform = detect_platform(base_url)
    if platform:
        format_from_url = detect_format_from_url(base_url, platform)
        if format_from_url:
            return format_from_url

    # 1. 尝试OpenAI格式
    urls = build_api_urls(base_url, "chat/completions")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "gpt-4o-mini",  # 常见模型名
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
    }

    for url in urls:
        try:
            async with session.post(
                url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    return "openai"
                raw_data = await response.read()
                try:
                    result = json.loads(raw_data)
                    # 返回了JSON（即使是error），说明路径正确
                    if "error" in result or "choices" in result:
                        return "openai"
                except:
                    pass
        except:
            pass

    # 2. 尝试Anthropic格式
    anthropic_url = f"{base_url.rstrip('/')}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    data = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "hi"}],
    }

    try:
        async with session.post(
            anthropic_url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                return "anthropic"
            raw_data = await response.read()
            try:
                result = json.loads(raw_data)
                if "type" in result or "error" in result:
                    return "anthropic"
            except:
                pass
    except:
        pass

    return "openai"  # 默认使用OpenAI格式


async def test_chat_model(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    model: str,
) -> dict:
    """
    Test a chat model with retry logic for model name variants.
    先尝试原始名称，失败则尝试去掉前缀的短名称。
    """
    variants = get_model_name_variants(model)
    last_error = None

    for variant in variants:
        start_time = time.perf_counter()
        result = await _test_single_chat_model(session, base_url, api_key, variant, start_time)
        if result["available"]:
            result["model"] = model  # 保持原始名用于API调用
            result["display_name"] = normalize_model_name(model)  # 显示名无前缀
            result["actual_model"] = variant  # 记录实际成功的名称
            return result
        last_error = result["error"]

    return {
        "model": model,
        "display_name": normalize_model_name(model),
        "type": "chat",
        "available": False,
        "response_time_ms": 0,
        "error": last_error,
    }


async def _test_single_image_model(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    model: str,
    start_time: float,
) -> dict:
    """Test a single image model variant with URL path detection."""
    urls = build_api_urls(base_url, "images/generations")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {"model": model, "prompt": "a cat", "n": 1, "size": "256x256"}

    last_result = None
    for url in urls:
        try:
            async with session.post(
                url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                raw_data = await response.read()
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                try:
                    result = json.loads(raw_data)
                except json.JSONDecodeError:
                    text = raw_data.decode("utf-8", errors="replace")
                    # 参数错误说明连接成功（如 "invalid"、"Bad Request"、"messages" 等参数相关错误）
                    if response.status == 400 and ("invalid" in text.lower() or "Bad Request" in text or "messages" in text):
                        URL_PATH_CACHE[base_url] = url.replace(base_url, "")
                        return {
                            "model": model,
                            "type": "image",
                            "available": True,
                            "response_time_ms": round(elapsed_ms, 0),
                            "error": None,
                        }
                    last_result = {
                        "model": model,
                        "type": "image",
                        "available": False,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": f"HTTP {response.status}: {text[:100]}",
                    }
                    if response.status == 404:
                        continue
                    return last_result

                if "error" in result:
                    error_obj = result["error"]
                    if isinstance(error_obj, dict):
                        error_msg = error_obj.get("message", "Unknown error")
                        error_type = error_obj.get("type", "")
                        # 参数错误（如size不支持）说明连接成功
                        if "invalid" in error_type.lower() or "user_error" in error_type.lower():
                            URL_PATH_CACHE[base_url] = url.replace(base_url, "")
                            return {
                                "model": model,
                                "type": "image",
                                "available": True,
                                "response_time_ms": round(elapsed_ms, 0),
                                "error": None,
                            }
                    else:
                        error_msg = str(error_obj)
                    last_result = {
                        "model": model,
                        "type": "image",
                        "available": False,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": error_msg,
                    }
                    return last_result

                # 某些平台用 {"code": "01", "msg": "..."} 格式
                if "msg" in result and result.get("code"):
                    msg = result["msg"]
                    # 参数错误说明连接成功
                    if "invalid" in msg.lower() or "Bad Request" in msg:
                        URL_PATH_CACHE[base_url] = url.replace(base_url, "")
                        return {
                            "model": model,
                            "type": "image",
                            "available": True,
                            "response_time_ms": round(elapsed_ms, 0),
                            "error": None,
                        }
                    last_result = {
                        "model": model,
                        "type": "image",
                        "available": False,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": msg,
                    }
                    return last_result

                if "data" in result and len(result["data"]) > 0:
                    URL_PATH_CACHE[base_url] = url.replace(base_url, "")
                    return {
                        "model": model,
                        "type": "image",
                        "available": True,
                        "response_time_ms": round(elapsed_ms, 0),
                        "error": None,
                    }

                last_result = {
                    "model": model,
                    "type": "image",
                    "available": False,
                    "response_time_ms": round(elapsed_ms, 0),
                    "error": "No data in response",
                }

        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            last_result = {
                "model": model,
                "type": "image",
                "available": False,
                "response_time_ms": round(elapsed_ms, 0),
                "error": "Timeout (>60s)",
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            last_result = {
                "model": model,
                "type": "image",
                "available": False,
                "response_time_ms": round(elapsed_ms, 0),
                "error": str(e),
            }

    return last_result if last_result else {
        "model": model,
        "type": "image",
        "available": False,
        "response_time_ms": 0,
        "error": "All URL paths failed",
    }


async def test_image_model(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    model: str,
) -> dict:
    """
    Test an image model with retry logic for model name variants.
    先尝试原始名称，失败则尝试去掉前缀的短名称。
    """
    variants = get_model_name_variants(model)
    last_error = None

    for variant in variants:
        start_time = time.perf_counter()
        result = await _test_single_image_model(session, base_url, api_key, variant, start_time)
        if result["available"]:
            result["model"] = model  # 保持原始名用于API调用
            result["display_name"] = normalize_model_name(model)  # 显示名无前缀
            result["actual_model"] = variant  # 记录实际成功的名称
            return result
        last_error = result["error"]

    return {
        "model": model,
        "display_name": normalize_model_name(model),
        "type": "image",
        "available": False,
        "response_time_ms": 0,
        "error": last_error,
    }


def detect_model_type(model_name: str) -> str:
    """根据模型名称判断类型"""
    model_lower = model_name.lower()
    # 仅用 image 端点
    image_only_keywords = ["dall-e", "stable-diffusion", "midjourney"]
    for kw in image_only_keywords:
        if kw in model_lower:
            return "image"
    # 双重测试：先 chat，失败再 image
    image_both_keywords = ["gpt-image", "imagen"]
    for kw in image_both_keywords:
        if kw in model_lower:
            return "both"
    # 检查 -image 后缀（如 gemini-2.5-flash-image）
    if "-image" in model_lower:
        return "both"
    return "chat"


async def test_all_models_stream(
    base_url: str, api_key: str
) -> AsyncGenerator[str, None]:
    """Test all models and yield results as SSE events."""
    semaphore = asyncio.Semaphore(5)
    global CHAT_MODELS, IMAGE_MODELS
    all_models = [(m, detect_model_type(m)) for m in CHAT_MODELS] + [(m, detect_model_type(m)) for m in IMAGE_MODELS]

    async with aiohttp.ClientSession() as session:

        async def test_with_semaphore(model: str, model_type: str) -> dict:
            async with semaphore:
                if model_type == "chat":
                    return await test_chat_model(session, base_url, api_key, model)
                elif model_type == "image":
                    return await test_image_model(session, base_url, api_key, model)
                else:  # both
                    result = await test_chat_model(session, base_url, api_key, model)
                    if result["available"]:
                        return result
                    result = await test_image_model(session, base_url, api_key, model)
                    result["type"] = "image"
                    return result

        yield f"data: {json.dumps({'event': 'start', 'total': len(all_models)})}\n\n"

        tasks = []
        for model, mtype in all_models:
            tasks.append(test_with_semaphore(model, mtype))

        results = await asyncio.gather(*tasks)

        available_results = sorted(
            [r for r in results if r["available"]],
            key=lambda x: x["response_time_ms"]
        )
        unavailable_results = sorted(
            [r for r in results if not r["available"]],
            key=lambda x: x["model"]
        )

        for result in available_results + unavailable_results:
            yield f"data: {json.dumps(result)}\n\n"

        yield f"data: {json.dumps({'event': 'complete', 'available': len(available_results), 'unavailable': len(unavailable_results)})}\n\n"


async def smart_test_stream(
    base_url: str, api_key: str
) -> AsyncGenerator[str, None]:
    """两阶段智能测速：先探测格式，再测平台模型，最后测其他模型"""
    semaphore = asyncio.Semaphore(5)
    global CHAT_MODELS, IMAGE_MODELS

    async with aiohttp.ClientSession() as session:
        # 阶段0：探测API格式
        yield f"data: {json.dumps({'event': 'detect', 'format': 'openai', 'status': 'trying', 'message': '尝试OpenAI格式...'})}\n\n"

        api_format = await detect_api_format(session, base_url, api_key)

        if api_format == "openai":
            yield f"data: {json.dumps({'event': 'format_detected', 'format': 'openai', 'message': '检测到OpenAI格式'})}\n\n"
        else:
            yield f"data: {json.dumps({'event': 'detect', 'format': 'anthropic', 'status': 'trying', 'message': 'OpenAI格式失败，尝试Anthropic格式...'})}\n\n"
            yield f"data: {json.dumps({'event': 'format_detected', 'format': 'anthropic', 'message': '检测到Anthropic格式'})}\n\n"

        # 阶段一：从平台获取模型列表
        yield f"data: {json.dumps({'event': 'phase', 'phase': 1, 'message': '从平台获取模型列表...'})}\n\n"

        platform_models = await fetch_platform_models(base_url, api_key)

        # DEBUG
        if "gpt-image" in str(platform_models):
            yield f"data: {json.dumps({'event': 'debug_platform', 'models': platform_models})}\n\n"

        if platform_models:
            yield f"data: {json.dumps({'event': 'info', 'message': f'平台返回 {len(platform_models)} 个模型'})}\n\n"
        else:
            yield f"data: {json.dumps({'event': 'info', 'message': '无法获取平台模型列表，使用本地列表'})}\n\n"

        # 标准化平台模型名称，用于去重
        platform_normalized = {normalize_model_name(m) for m in platform_models}

        # 阶段一测试：平台模型（智能判断类型）
        phase1_models = []
        for m in platform_models:
            mtype = detect_model_type(m)
            phase1_models.append((m, mtype, "platform"))

        # 阶段二测试：本地列表中，标准化后不在平台列表的模型，且本地内部也要去重
        local_models = set(CHAT_MODELS + IMAGE_MODELS)
        phase2_normalized = set()  # 用于本地内部去重
        phase2_models = []
        for m in local_models:
            normalized = normalize_model_name(m)
            # 排除：1. 平台已有的  2. 本地已添加的（内部去重）
            if normalized not in platform_normalized and normalized not in phase2_normalized:
                phase2_models.append((m, detect_model_type(m), "local"))
                phase2_normalized.add(normalized)

        all_models = phase1_models + phase2_models

        yield f"data: {json.dumps({'event': 'start', 'total': len(all_models), 'phase1': len(phase1_models), 'phase2': len(phase2_models)})}\n\n"

        async def test_with_semaphore(model: str, model_type: str, source: str) -> dict:
            async with semaphore:
                if model_type == "chat":
                    if api_format == "anthropic":
                        # Anthropic格式：尝试不同模型名变体
                        variants = get_model_name_variants(model)
                        last_error = None
                        for variant in variants:
                            start_time = time.perf_counter()
                            result = await _test_single_anthropic_model(session, base_url, api_key, variant, start_time)
                            if result["available"]:
                                result["model"] = model
                                result["display_name"] = normalize_model_name(model)
                                result["actual_model"] = variant
                                result["source"] = source
                                return result
                            last_error = result["error"]
                        return {
                            "model": model,
                            "display_name": normalize_model_name(model),
                            "type": "chat",
                            "available": False,
                            "response_time_ms": 0,
                            "error": last_error,
                            "source": source,
                        }
                    else:
                        result = await test_chat_model(session, base_url, api_key, model)
                        result["source"] = source
                        return result
                elif model_type == "image":
                    result = await test_image_model(session, base_url, api_key, model)
                    result["source"] = source
                    return result
                else:  # both
                    # 先尝试 chat
                    if api_format == "anthropic":
                        variants = get_model_name_variants(model)
                        for variant in variants:
                            result = await _test_single_anthropic_model(session, base_url, api_key, variant, time.perf_counter())
                            if result["available"]:
                                result["model"] = model
                                result["display_name"] = normalize_model_name(model)
                                result["actual_model"] = variant
                                result["type"] = "chat"
                                result["source"] = source
                                return result
                    else:
                        result = await test_chat_model(session, base_url, api_key, model)
                        if result["available"]:
                            result["source"] = source
                            return result
                    # chat 失败，尝试 image
                    result = await test_image_model(session, base_url, api_key, model)
                    result["type"] = "image"
                    result["source"] = source
                    return result

        tasks = []
        for model, mtype, msource in all_models:
            tasks.append(test_with_semaphore(model, mtype, msource))

        results = await asyncio.gather(*tasks)

        # 排序：平台可用 > 本地可用 > 平台不可用 > 本地不可用
        def sort_key(r):
            source_priority = 0 if r.get("source") == "platform" else 1
            available_priority = 0 if r["available"] else 1
            if r["available"]:
                return (source_priority, available_priority, r["response_time_ms"])
            else:
                return (source_priority, available_priority, r["model"])

        sorted_results = sorted(results, key=sort_key)

        for result in sorted_results:
            yield f"data: {json.dumps(result)}\n\n"

        available_count = sum(1 for r in results if r["available"])
        yield f"data: {json.dumps({'event': 'complete', 'available': available_count, 'unavailable': len(results) - available_count})}\n\n"


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main page."""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/test/stream")
async def test_stream(request: Request):
    """Stream test results via SSE."""
    data = await request.json()
    base_url = data.get("base_url", "")
    api_key = data.get("api_key", "")

    if not base_url or not api_key:
        return {"error": "Missing base_url or api_key"}

    return StreamingResponse(
        test_all_models_stream(base_url, api_key),
        media_type="text/event-stream",
    )


@app.post("/api/test/smart")
async def test_smart(request: Request):
    """两阶段智能测速：先测平台模型，再测其他模型"""
    data = await request.json()
    base_url = data.get("base_url", "")
    api_key = data.get("api_key", "")

    if not base_url or not api_key:
        return {"error": "Missing base_url or api_key"}

    return StreamingResponse(
        smart_test_stream(base_url, api_key),
        media_type="text/event-stream",
    )


@app.get("/api/models")
async def get_models():
    """Return the current list of models."""
    global CHAT_MODELS, IMAGE_MODELS
    # Reload from file in case it was updated
    CHAT_MODELS, IMAGE_MODELS = load_models()
    return {
        "chat_models": CHAT_MODELS,
        "image_models": IMAGE_MODELS,
        "total": len(CHAT_MODELS) + len(IMAGE_MODELS),
    }


@app.post("/api/models/sync")
async def sync_models():
    """Sync models from OpenRouter."""
    result = await sync_from_openrouter()
    return JSONResponse(result)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
