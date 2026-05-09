#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Model Tester - Test which models are supported by OpenAI-compatible APIs
"""

import argparse
import sys
import requests


def list_models(base_url: str, api_key: str) -> None:
    """List all models supported by the API"""
    url = f"{base_url.rstrip('/')}/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    print(f"\n[LIST] Fetching model list...")
    print(f"   API: {base_url}")

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            models = data.get("data", [])
            if models:
                print(f"\n[OK] Found {len(models)} models:\n")
                for i, model in enumerate(models, 1):
                    model_id = model.get("id", "unknown")
                    print(f"   {i:2}. {model_id}")
            else:
                print("[WARN] Model list is empty")
        else:
            print(f"[FAIL] HTTP {response.status_code}")
            print(f"   {response.text}")
    except Exception as e:
        print(f"[ERROR] {e}")


def test_chat_model(base_url: str, api_key: str, model: str, prompt: str = "hi") -> bool:
    """Test if a chat model is available"""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 10
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        result = response.json()

        if "error" in result:
            return False
        if "choices" in result:
            return True
        return False
    except Exception:
        return False


def test_image_model(base_url: str, api_key: str, model: str, prompt: str = "a cat") -> bool:
    """Test if an image generation model is available"""
    url = f"{base_url.rstrip('/')}/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "256x256"
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        result = response.json()

        if "error" in result:
            return False
        if "data" in result:
            return True
        return False
    except Exception:
        return False


def test_models(base_url: str, api_key: str, models: list, model_type: str = "chat") -> None:
    """Batch test models"""
    print(f"\n[TEST] Testing {model_type} models...")
    print(f"   API: {base_url}\n")

    available = []
    unavailable = []

    test_func = test_chat_model if model_type == "chat" else test_image_model

    for model in models:
        print(f"   Testing {model}...", end=" ", flush=True)
        if test_func(base_url, api_key, model):
            print("[OK] Available")
            available.append(model)
        else:
            print("[FAIL] Not available")
            unavailable.append(model)

    print(f"\n[RESULT]")
    print(f"   Available: {len(available)}")
    for m in available:
        print(f"      + {m}")
    print(f"   Not available: {len(unavailable)}")
    for m in unavailable:
        print(f"      - {m}")


def test_common_models(base_url: str, api_key: str) -> None:
    """Test common models"""
    # Common chat models
    chat_models = [
        # OpenAI GPT series
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        # OpenAI O series
        "o1",
        "o1-mini",
        "o1-preview",
        "o3-mini",
        # Anthropic Claude series
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
        # Google Gemini series
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-image",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3-pro-image-preview",
        "gemini-3.1-pro-preview",
        "gemini-3.1-flash-image-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        # Others
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "mistral-large-latest",
        "deepseek-chat",
        "deepseek-reasoner",
    ]

    # Common image models
    image_models = [
        "dall-e-3",
        "dall-e-2",
        "gpt-image-1",
        "gpt-image-2",
        "gpt-image",
        "stable-diffusion-xl-1024-v1-0",
    ]

    test_models(base_url, api_key, chat_models, "chat")
    test_models(base_url, api_key, image_models, "image")


def main():
    parser = argparse.ArgumentParser(
        description="API Model Tester - Test which models are supported by OpenAI-compatible APIs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list --api-key sk-xxx
  %(prog)s --test-common --api-key sk-xxx
  %(prog)s --test gpt-4o,gpt-3.5-turbo --api-key sk-xxx
  %(prog)s --test-image dall-e-3 --api-key sk-xxx
        """
    )

    parser.add_argument("--api-url", default="https://api.openai.com",
                       help="API base URL (default: OpenAI official)")
    parser.add_argument("--api-key", required=True,
                       help="API Key")
    parser.add_argument("--list", action="store_true",
                       help="List all available models")
    parser.add_argument("--test-common", action="store_true",
                       help="Test common models")
    parser.add_argument("--test",
                       help="Test specified chat models, comma-separated")
    parser.add_argument("--test-image",
                       help="Test specified image models, comma-separated")

    args = parser.parse_args()

    if args.list:
        list_models(args.api_url, args.api_key)
    elif args.test_common:
        test_common_models(args.api_url, args.api_key)
    elif args.test:
        models = [m.strip() for m in args.test.split(",")]
        test_models(args.api_url, args.api_key, models, "chat")
    elif args.test_image:
        models = [m.strip() for m in args.test_image.split(",")]
        test_models(args.api_url, args.api_key, models, "image")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()