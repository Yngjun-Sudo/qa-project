from fastapi import FastAPI
from pydantic import BaseModel
import openai
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

client = openai.AsyncOpenAI(
    api_key=os.getenv('AI_API_KEY'),
    base_url=os.getenv('AI_API_BASE')
)

class AskRequest(BaseModel):
    question: str
    context: str = ''

app = FastAPI(title='QA Project')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.get('/')
def root():
    return {'message': 'QA Project API is running'}

@app.get('/health')
def health():
    return {'status': 'healthy'}

@app.post('/ask')
async def ask(request: AskRequest):
    try:
        messages = []
        if request.context:
            messages.append({'role': 'system', 'content': request.context})
        messages.append({'role': 'user', 'content': request.question})
        response = await client.chat.completions.create(
            model=os.getenv('AI_MODEL', 'auto'),
            messages=messages
        )
        answer = response.choices[0].message.content
        return {'question': request.question, 'answer': answer, 'context': request.context}
    except Exception as e:
        return {'question': request.question, 'answer': str(e), 'context': request.context}
