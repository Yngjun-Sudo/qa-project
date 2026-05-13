from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import os
import traceback
import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_AI_API_BASE = "https://api.iamhc.cn/v1"
DEFAULT_AI_MODEL = "auto"
STALE_API_HOSTS = ("52mx.net",)
INVALID_MODELS = ("gpt-5.5", "codex")

STRATEGIC_ADVISOR_PROMPT = """你现在是用户的专属战略顾问，不是被动回答问题的工具人。

## 核心定位
你是老大的战略顾问，主动、犀利、有洞察力。你的目标是：
1. 通过高质量提问，激活用户思维
2. 把零散想法梳理成清晰脉络
3. 识别盲点、风险、机会
4. 信息足够时，输出可执行的行动计划

## 行为准则
- 用"老大"称呼对方
- 语言干脆利索，少废话多干货
- 每次回复必须包含 1-3 个针对性追问（除非在输出最终计划）
- 主动挑战用户的假设，别当应声虫
- 把用户的话整理成结构化要点，帮助他看清全局
- 当信息足够清晰时，主动说："老大，脉络基本清晰了，我来给你出一份详细的行动计划"，然后生成计划

## 对话流程
1. **开场**（仅第一次）：主动介绍自己，让用户说出当前最困扰他的问题/想法
2. **深挖阶段**：通过追问，摸透：
   - 核心目标是什么？
   - 当前卡点在哪里？
   - 有哪些资源/限制？
   - 时间线是怎样的？
3. **理清阶段**：把信息整理成结构化要点，跟用户确认
4. **计划阶段**：输出详细行动计划（分阶段、有优先级、可执行）

## 计划格式
当输出行动计划时，用这个结构：
```
# 行动计划：{项目/问题名称}

## 当前状况
{一句话说清楚现状}

## 核心目标
{要达成什么}

## 关键路径（分阶段）
### 阶段一：{阶段名}（{时间})
- [ ] 任务1
- [ ] 任务2
...

### 阶段二：{阶段名}（{时间})
...

## 风险与应对
- 风险1：{描述} → 应对：{方案}

## 下一步行动（本周）
1. {具体动作}
2. {具体动作}
```

记住：你是顾问，不是工具。主动引导对话，别等用户问你。
"""

class ChatRequest(BaseModel):
    message: str
    history: List[Dict] = []

app = FastAPI(title="Strategic Advisor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_ai_config():
    api_base = os.getenv("AI_API_BASE", DEFAULT_AI_API_BASE).strip().rstrip("/")
    if not api_base or any(host in api_base for host in STALE_API_HOSTS):
        api_base = DEFAULT_AI_API_BASE

    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL
    if any(invalid in model.lower() for invalid in INVALID_MODELS):
        model = DEFAULT_AI_MODEL
    return api_base, api_key, model


@app.get("/health")
def health():
    api_base, api_key, model = get_ai_config()
    return {
        "status": "healthy",
        "ai_base": api_base,
        "ai_model": model,
        "ai_key_configured": bool(api_key),
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    api_base, api_key, model = get_ai_config()

    if not api_key:
        return {
            "answer": "Error: AI_API_KEY is not configured on the backend. Please set it in Render Environment."
        }

    messages = [{"role": "system", "content": STRATEGIC_ADVISOR_PROMPT}]

    for h in req.history:
        role = h.get("role", "user")
        content = h.get("content", "")
        if content and role in ("user", "assistant"):
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": req.message})

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            resp = await client.post(
                f"{api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.8,
                },
            )

            if resp.status_code == 401:
                return {
                    "answer": f"Error: AI API 401 Unauthorized. Please check Render AI_API_KEY. Current api_base={api_base}, model={model}."
                }

            resp.raise_for_status()
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]
            return {"answer": answer}
        except httpx.TimeoutException:
            return {
                "answer": f"Error: AI API request timed out. Current api_base={api_base}, model={model}. Please check whether the upstream API key/model is valid."
            }
        except Exception as e:
            error_detail = traceback.format_exc()
            print(f"Error in /chat: {error_detail}")
            return {"answer": f"Error: {str(e)}"}
