from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

ADVISOR_SYSTEM_PROMPT = """你现在是用户的专属战略顾问，不是被动回答问题的工具。

你的行为准则：
1. 主动提问：每次回复都要包含1-3个针对性的追问，帮助用户深入思考
2. 理清线索：把用户零散的想法整理成结构化的要点
3. 识别盲点：指出用户没考虑到的问题和风险
4. 推进落地：当信息足够时，主动提出行动方案

开场白（仅第一次）：
"老大好！我是你的战略顾问。别把我当工具人，咱俩是搭档。
你现在脑子里有什么想法、项目、或者乱七八糟的线索？都说出来，越详细越好，我来帮你理得明明白白。"

后续对话中：
- 用"老大"称呼对方
- 语言干脆利索，少废话多干货
- 每次回复都要推动对话向前走（要么深挖、要么给方案）
- 当觉得信息足够清晰时，主动说"脉络基本清晰了，我来给你出一份详细行动计划"，然后生成计划
"""

class AskRequest(BaseModel):
    question: str
    context: str = ""
    history: List[Dict] = []
    mode: str = "qa"  # "qa" or "advisor"

app = FastAPI(title="QA Project")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/ask")
async def ask(req: AskRequest):
    messages = []

    # 顾问模式：注入战略顾问 system prompt
    if req.mode == "advisor":
        messages.append({"role": "system", "content": ADVISOR_SYSTEM_PROMPT})
    elif req.context:
        messages.append({"role": "system", "content": req.context})

    # 加入历史对话（跳过第一条系统消息）
    for h in req.history:
        role = h.get("role", "user")
        content = h.get("content", "")
        if content and role in ("user", "assistant"):
            messages.append({"role": role, "content": content})

    # 添加当前用户消息
    messages.append({"role": "user", "content": req.question})

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{os.getenv('AI_API_BASE')}/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('AI_API_KEY')}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.getenv("AI_MODEL", "auto"),
                "messages": messages,
                "temperature": 0.8 if req.mode == "advisor" else 0.7,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    answer = data["choices"][0]["message"]["content"]
    return {
        "question": req.question,
        "answer": answer,
        "mode": req.mode,
    }
