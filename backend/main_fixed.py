from fastapi import FastAPI
from pydantic import BaseModel
import openai
import os
from dotenv import load_dotenv

load_dotenv()
client = openai.AsyncOpenAI(
    api_key=os.getenv("AI_API_KEY"),
    base_url=os.getenv("AI_API_BASE")
)

class AskRequest(BaseModel):
    question: str
    context: str = ""

app = FastAPI(title="QA Project")

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/ask")
async def ask(req: AskRequest):
    messages = []
    if req.context:
        messages.append({"role": "system", "content": req.context})
    messages.append({"role": "user", "content": req.question})
    resp = await client.chat.completions.create(
        model=os.getenv("AI_MODEL", "auto"),
        messages=messages
    )
    answer = resp.choices[0].message.content
    return {"question": req.question, "answer": answer, "context": req.context}
