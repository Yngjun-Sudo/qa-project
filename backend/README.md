# QA Project 环境配置

## 安装依赖

1. 创建虚拟环境：
   python -m venv venv

2. 激活虚拟环境：
   # Windows:
   venv\Scripts\activate
   # Mac/Linux:
   source venv/bin/activate

3. 安装依赖：
   pip install -r requirements.txt

## 启动后端

   uvicorn main:app --reload --port 8000

然后浏览器打开：http://localhost:8000/docs
