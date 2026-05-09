# API Model Tester

一个用于测试API模型可用性和响应速度的Web工具。

## 功能特点

- **智能测速**：自动检测API格式（OpenAI/Anthropic），获取平台模型列表
- **多平台支持**：支持OpenAI、Anthropic、腾讯codingplan、OpenRouter等聚合平台
- **实时结果**：通过SSE流式返回测速结果，实时显示进度
- **模型列表同步**：从OpenRouter同步最新模型列表
- **响应时间排序**：按响应速度排序显示可用模型

## 支持的平台

| 平台 | URL格式 | 模型列表API |
|-----|---------|------------|
| OpenAI | `/v1/chat/completions` | `/v1/models` |
| Anthropic | `/v1/messages` | 硬编码列表 |
| 腾讯codingplan | `/coding/v3` 或 `/coding/anthropic` | `/v3/models` |
| OpenRouter | `/api/v1/chat/completions` | `/api/v1/models` |
| DeepSeek | `/v1/chat/completions` | `/v1/models` |
| Groq | `/openai/v1/chat/completions` | `/openai/v1/models` |

## 安装

```bash
# 克隆仓库
git clone https://github.com/Aestion/APIsearch.git
cd APIsearch

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

```bash
# 启动Web服务
python web_app.py
```

然后访问 http://localhost:8000

### 测试步骤

1. 输入API Base URL（如 `https://api.openai.com`）
2. 输入API Key
3. 点击 **Smart Test** 开始智能测速

### 按钮说明

| 按钮 | 功能 |
|-----|------|
| **Smart Test (平台+本地)** | 先获取平台模型列表测试，再测试本地其他模型 |
| **Test Models** | 使用本地模型列表测试 |
| **Sync from OpenRouter** | 从OpenRouter同步最新模型列表 |

## 技术栈

- **后端**：FastAPI + aiohttp（异步HTTP请求）
- **前端**：原生JavaScript + SSE（Server-Sent Events）
- **API格式**：自动检测OpenAI和Anthropic格式

## 项目结构

```
APIsearch/
├── web_app.py        # FastAPI后端服务
├── api_tester.py     # 命令行版本
├── models.json       # 模型列表配置
├── requirements.txt  # Python依赖
└── static/
    ├── index.html    # 前端页面
    ├── app.js        # 前端逻辑
    └── style.css     # 样式文件
```

## License

MIT
