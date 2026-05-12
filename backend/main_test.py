from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

ai_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ai_client
    logger.info("🚀 Lifespan started...")
    api_key = os.getenv("AI_API_KEY")
    api_base = os.getenv("AI_API_BASE")
    if api_key and api_base:
        try:
            import openai
            ai_client = openai.AsyncOpenAI(api_key=api_key, base_url=api_base)
            logger.info(f"✅ AI client initialized: {api_base}")
        except Exception as e:
            logger.error(f"❌ AI client failed: {e}")
    yield
    logger.info("🛑 Lifespan shutting down...")
    ai_client = None

app = FastAPI(title="QA Project - TEST", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str
    context: str = ""

@app.get("/")
def root():
    return {"message": "TEST API running"}

@app.get("/health")
def health():
    return {"status": "healthy", "ai": ai_client is not None}

@app.post("/ask")
async def ask(request: AskRequest):
    return {"question": "这是一个测试问题？"}
