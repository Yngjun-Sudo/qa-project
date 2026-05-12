# QA Project 部署指南

## 公网部署（永久运行）

### 方案一：Render（后端）+ Vercal（前端）【推荐】

#### 1. 后端部署到 Render

1. 访问 https://render.com 注册（免费）
2. 点 "New +" → "Web Service"
3. 连接 GitHub 仓库（先把代码推到 GitHub）
4. 配置：
   - **Name**: `qa-project-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `cd backend && python -m uvicorn app:app --host 0.0.0.0 --port $PORT`
5. 添加环境变量（Environment Variables）：
   - `AI_API_KEY`: `sk-itNzYFFpSTJq0bc2vNM2YL2AONwq3EKy21CjU16vPkyrcUDt`
   - `AI_API_BASE`: `https://api.iamhc.cn/v1`
   - `AI_MODEL`: `step-3.5-flash`
6. 点 "Create Web Service"
7. 等待部署完成，记下后端地址（如 `https://qa-project-backend.onrender.com`）

#### 2. 前端部署到 Vercel

1. 访问 https://vercel.com 注册（免费）
2. 点 "New Project" → 导入 GitHub 仓库
3. 配置：
   - **Framework Preset**: `Other`
   - **Root Directory**: `frontend`
4. 点 "Deploy"
5. 部署完成后，记下前端地址（如 `https://qa-project.vercel.app`）

#### 3. 修改前端 API 地址

1. 打开 `frontend/index.html`
2. 把 `http://192.168.1.6:8001/ask` 改成你的 Render 后端地址：
   ```javascript
   const response = await fetch('https://qa-project-backend.onrender.com/ask', {
   ```
3. 提交代码，Vercel 自动重新部署

---

### 方案二：Cloudflare Tunnel（临时测试用）

1. 下载 `cloudflared`：https://github.com/cloudflare/cloudflared/releases
2. 运行：
   ```bash
   cloudflared tunnel --url http://localhost:8000  # 前端
   cloudflared tunnel --url http://localhost:8001  # 后端
   ```
3. 得到两个 `https://*.trycloudflare.com` 地址
4. 把前端里的后端地址改成 Cloudflare 给的地址

---

## 注意事项

1. **Render 免费版会休眠**：15 分钟无访问后休眠，下次访问需要等 30 秒唤醒
2. **API Key 安全**：不要提交 `.env` 文件到 GitHub！用 Render 的环境变量功能
3. **CORS 配置**：如果前端地址固定，可以修改后端 CORS 配置，只允许你的前端域名访问

---

## 快速测试（本地）

```bash
# 启动后端
cd backend
python -m uvicorn app:app --host 0.0.0.0 --port 8001

# 启动前端（新终端）
cd frontend
python -m http.server 8000
```

访问：`http://localhost:8000/`
