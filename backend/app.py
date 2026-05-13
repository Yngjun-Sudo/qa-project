from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import traceback
import httpx
import json
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEFAULT_AI_API_BASE = "https://api.deepseek.com/anthropic"
DEFAULT_AI_MODEL = "deepseek-v4-flash"
STALE_API_HOSTS = ("52mx.net",)
INVALID_MODELS = ("gpt-5.5", "codex")

MEMORY_DIR = Path.home() / "WorkBuddy" / "Claw" / ".workbuddy" / "memory"
MEMORY_MD = MEMORY_DIR / "MEMORY.md"
GROWTH_BOX = Path.home() / ".workbuddy" / "growth_box.json"

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

class MemoryEntry(BaseModel):
    content: str
    category: str = "general"  # general, success, failure, discovery, constraint

class GrowthBoxError(BaseModel):
    error_id: str
    title: str
    description: str
    severity: str = "medium"  # low, medium, high
    category: str = "general"

app = FastAPI(title="Strategic Advisor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== AI Config ==========

def get_ai_config():
    api_base = os.getenv("AI_API_BASE", DEFAULT_AI_API_BASE).strip().rstrip("/")
    if not api_base or any(host in api_base for host in STALE_API_HOSTS):
        api_base = DEFAULT_AI_API_BASE

    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL
    if model.lower() == "auto" or any(invalid in model.lower() for invalid in INVALID_MODELS):
        model = DEFAULT_AI_MODEL
    return api_base, api_key, model


def is_anthropic_api(api_base: str) -> bool:
    return "/anthropic" in api_base.rstrip("/").lower()


def build_anthropic_messages(messages: List[Dict]):
    system_parts = []
    user_messages = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role in ("user", "assistant") and content:
            user_messages.append({"role": role, "content": content})
    return "\n\n".join(system_parts), user_messages


def extract_anthropic_answer(data: Dict) -> str:
    content = data.get("content", [])
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return "".join(text_parts).strip()
    if isinstance(content, str):
        return content
    return ""


# ========== Health & System Status ==========

@app.get("/health")
def health():
    api_base, api_key, model = get_ai_config()
    return {
        "status": "healthy",
        "ai_base": api_base,
        "ai_model": model,
        "ai_key_configured": bool(api_key),
    }


@app.get("/api/system/status")
def system_status():
    """系统总览：各模块状态"""
    today = date.today().isoformat()
    daily_path = MEMORY_DIR / f"{today}.md"

    # AI config
    api_base, api_key, model = get_ai_config()

    # Memory stats
    daily_files = sorted(MEMORY_DIR.glob("202*.md")) if MEMORY_DIR.exists() else []
    recent_7 = [f for f in daily_files if f.stem >= (date.today() - __import__("datetime").timedelta(days=7)).isoformat()]
    memory_md_exists = MEMORY_MD.exists() if MEMORY_DIR.exists() else False
    memory_md_lines = len(MEMORY_MD.read_text(encoding="utf-8").splitlines()) if memory_md_exists else 0

    # Growth box stats
    gb_total = 0
    gb_promoted = 0
    gb_high_severity = 0
    if GROWTH_BOX.exists():
        try:
            gb_data = json.loads(GROWTH_BOX.read_text(encoding="utf-8"))
            gb_total = len(gb_data.get("errors", []))
            gb_promoted = sum(1 for e in gb_data.get("errors", []) if e.get("promoted"))
            gb_high_severity = sum(1 for e in gb_data.get("errors", []) if e.get("severity") == "high")
        except Exception:
            pass

    # Today's record exists?
    today_has_record = daily_path.exists() and daily_path.stat().st_size > 50

    return {
        "ai": {
            "model": model,
            "api_base": api_base,
            "key_configured": bool(api_key),
        },
        "memory": {
            "total_daily_files": len(daily_files),
            "recent_7_days": len(recent_7),
            "longterm_exists": memory_md_exists,
            "longterm_lines": memory_md_lines,
            "today_recorded": today_has_record,
        },
        "growth_box": {
            "total_errors": gb_total,
            "promoted_to_rules": gb_promoted,
            "high_severity": gb_high_severity,
        },
        "today": today,
        "today_has_record": today_has_record,
    }


# ========== Memory API ==========

@app.get("/api/memory/daily")
def get_daily_memory(target_date: Optional[str] = None):
    """获取指定日期的工作日志"""
    if not target_date:
        target_date = date.today().isoformat()
    daily_path = MEMORY_DIR / f"{target_date}.md"
    if not daily_path.exists():
        return {"date": target_date, "content": "", "exists": False}
    content = daily_path.read_text(encoding="utf-8")
    return {"date": target_date, "content": content, "exists": True}


@app.get("/api/memory/daily/list")
def list_daily_memory(days: int = 7):
    """列出最近 N 天的日志"""
    result = []
    if not MEMORY_DIR.exists():
        return result
    cutoff = (date.today() - __import__("datetime").timedelta(days=days)).isoformat()
    for f in sorted(MEMORY_DIR.glob("202*.md"), reverse=True):
        if f.stem < cutoff:
            continue
        content = f.read_text(encoding="utf-8")
        preview = content.split("\n")[-1][:80].strip() if content else ""
        result.append({
            "date": f.stem,
            "size": len(content),
            "preview": preview,
        })
    return result


@app.get("/api/memory/longterm")
def get_longterm_memory():
    """获取长期记忆 MEMORY.md"""
    if not MEMORY_MD.exists():
        return {"content": "", "exists": False}
    content = MEMORY_MD.read_text(encoding="utf-8")
    return {"content": content, "exists": True}


@app.post("/api/memory/daily")
def append_daily_memory(entry: MemoryEntry):
    """追加一条到今日日志"""
    if not MEMORY_DIR.exists():
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    daily_path = MEMORY_DIR / f"{today}.md"

    if not daily_path.exists():
        header = f"# {today} 工作日志\n\n## 工作记录\n\n"
        daily_path.write_text(header, encoding="utf-8")

    now = datetime.now().strftime("%H:%M")
    category_tag = {"success": "成功", "failure": "失败", "discovery": "发现", "constraint": "约束", "general": "记录"}.get(entry.category, "记录")
    line = f"- [{category_tag}] {entry.content}\n"

    existing = daily_path.read_text(encoding="utf-8")
    daily_path.write_text(existing + line, encoding="utf-8")

    return {"status": "ok", "date": today, "line": line.strip()}


@app.post("/api/memory/search")
def search_memory(query: str):
    """在所有记忆文件中搜索关键词"""
    results = []
    if not MEMORY_DIR.exists():
        return {"query": query, "results": results}

    q = query.lower()
    for f in sorted(MEMORY_DIR.glob("202*.md"), reverse=True):
        try:
            content = f.read_text(encoding="utf-8")
            matches = []
            for i, line in enumerate(content.splitlines(), 1):
                if q in line.lower():
                    matches.append({"line": i, "text": line.strip()[:120]})
            if matches:
                results.append({"file": f.stem, "matches": matches[:5]})
        except Exception:
            pass

    if MEMORY_MD.exists():
        try:
            content = MEMORY_MD.read_text(encoding="utf-8")
            matches = []
            for i, line in enumerate(content.splitlines(), 1):
                if q in line.lower():
                    matches.append({"line": i, "text": line.strip()[:120]})
            if matches:
                results.insert(0, {"file": "MEMORY.md", "matches": matches[:5]})
        except Exception:
            pass

    return {"query": query, "total_files": len(results), "results": results[:10]}


# ========== Growth Box API ==========

def _load_growth_box():
    if not GROWTH_BOX.exists():
        GROWTH_BOX.parent.mkdir(parents=True, exist_ok=True)
        GROWTH_BOX.write_text(json.dumps({"errors": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"errors": []}
    try:
        return json.loads(GROWTH_BOX.read_text(encoding="utf-8"))
    except Exception:
        return {"errors": []}


def _save_growth_box(data):
    GROWTH_BOX.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/api/growthbox/errors")
def get_growth_box_errors():
    """获取成长箱所有错误"""
    data = _load_growth_box()
    errors = data.get("errors", [])
    # 统计
    summary = {}
    for e in errors:
        title = e.get("title", "unknown")
        summary[title] = summary.get(title, 0) + 1
    return {
        "errors": errors,
        "total": len(errors),
        "summary": summary,
        "eligible_for_promotion": [e for e in errors if e.get("count", 1) >= 3 and not e.get("promoted")],
    }


@app.post("/api/growthbox/errors")
def add_growth_box_error(error: GrowthBoxError):
    """添加一条错误到成长箱"""
    data = _load_growth_box()
    errors = data.get("errors", [])

    # 检查是否已有同 title 的错误
    existing = next((e for e in errors if e.get("title") == error.title), None)
    if existing:
        existing["count"] = existing.get("count", 1) + 1
        existing["last_seen"] = datetime.now().isoformat()
        existing_id = existing.get("id")
        action = "count_increased"
    else:
        new_error = {
            "id": error.error_id,
            "title": error.title,
            "description": error.description,
            "severity": error.severity,
            "category": error.category,
            "count": 1,
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "promoted": False,
        }
        errors.append(new_error)
        existing_id = error.error_id
        action = "created"

    data["errors"] = errors
    _save_growth_box(data)

    can_promote = any(e.get("count", 1) >= 3 and not e.get("promoted") for e in errors)
    return {"status": "ok", "action": action, "id": existing_id, "can_promote": can_promote}


@app.post("/api/growthbox/promote")
def promote_error(error_id: str):
    """将错误晋升为约束规则"""
    data = _load_growth_box()
    errors = data.get("errors", [])
    target = next((e for e in errors if e.get("id") == error_id), None)
    if not target:
        return {"status": "error", "message": f"Error {error_id} not found"}

    target["promoted"] = True
    target["promoted_at"] = datetime.now().isoformat()
    _save_growth_box(data)

    # 写入 MEMORY.md
    if not MEMORY_DIR.exists():
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    rule_text = f"\n### [{target['title']}]（已验证{target.get('count', 1)}次）\n- {target['description']}\n- 来源：growth_box {error_id}\n"

    if MEMORY_MD.exists():
        existing = MEMORY_MD.read_text(encoding="utf-8")
        if "### 约束（成长箱晋升规则" in existing:
            # 插入到约束部分之后
            parts = existing.split("## 约束（成长箱晋升规则，已验证）\n")
            if len(parts) == 2:
                new_content = parts[0] + "## 约束（成长箱晋升规则，已验证）\n" + rule_text + parts[1]
                MEMORY_MD.write_text(new_content, encoding="utf-8")
            else:
                MEMORY_MD.write_text(existing + rule_text, encoding="utf-8")
        else:
            MEMORY_MD.write_text(existing + rule_text, encoding="utf-8")
    else:
        MEMORY_MD.write_text(f"# 长期记忆\n\n## 约束（成长箱晋升规则，已验证）\n{rule_text}\n", encoding="utf-8")

    return {"status": "ok", "promoted": target["title"], "rule": rule_text.strip()}


# ========== Chat (original) ==========

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
            if is_anthropic_api(api_base):
                system_prompt, anthropic_messages = build_anthropic_messages(messages)
                resp = await client.post(
                    f"{api_base}/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": model,
                        "max_tokens": 1000,
                        "system": system_prompt,
                        "messages": anthropic_messages,
                        "temperature": 0.8,
                    },
                )
            else:
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
            if is_anthropic_api(api_base):
                answer = extract_anthropic_answer(data)
            else:
                answer = data["choices"][0]["message"]["content"]
            return {"answer": answer or "Error: Empty AI response"}
        except httpx.TimeoutException:
            return {
                "answer": f"Error: AI API request timed out. Current api_base={api_base}, model={model}. Please check whether the upstream API key/model is valid."
            }
        except Exception as e:
            error_detail = traceback.format_exc()
            print(f"Error in /chat: {error_detail}")
            return {"answer": f"Error: {str(e)}"}
