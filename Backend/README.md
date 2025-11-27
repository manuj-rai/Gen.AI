# Portfolio Q&A Backend API

A Flask-based backend API that provides Q&A capabilities about your portfolio using AI. It scrapes your portfolio website and ingests the structured `portfolio_data.xml` file to answer questions about you.

## 🚀 Local Setup & Running

### Prerequisites
- Python 3.8 or higher
- OpenAI API Key

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

**Important:** If you want to scrape JavaScript-rendered websites (like React/Next.js SPAs), you also need to install Playwright browsers:

```bash
playwright install chromium
```

This is optional but recommended for modern portfolio websites that use JavaScript frameworks.

### Step 2: Create `.env` File

Create a `.env` file in the root directory with the following variables:

```env
OPENAI_API_KEY=your_openai_api_key_here
SOURCE_URL=https://manuj-rai.vercel.app/
PORTFOLIO_PATH=portfolio_data.xml
# Optional tuning knobs (defaults shown)
ENABLE_PORTFOLIO_PRELOAD=true
ENABLE_WEBSITE_PRELOAD=true
WEBSITE_PRELOAD_MODE=background   # set to sync to block startup
MAX_WEB_PAGES=15
USE_PLAYWRIGHT=false              # enable only if Playwright browsers installed
```

**Note:** The `.env` file is already in `.gitignore`, so it won't be committed to git.

### Step 3: Run the Application

#### Option 1: Run with Python directly (Recommended for local testing)

```bash
python app.py
```

**Note:** If the app doesn't start, you may need to uncomment the bottom section of `app.py`. Let me know and I can help with that.

#### Option 2: Run with Flask CLI

```bash
flask run --host=0.0.0.0 --port=5000
```

Or set the environment variables and run:

```bash
set FLASK_APP=app.py
flask run
```

#### Option 3: Run with Gunicorn (Production-like)

```bash
gunicorn app:app --bind 0.0.0.0:5000 --timeout 300
```

### Step 4: Verify It's Running

1. **Check the home route:**
   ```bash
   curl http://localhost:5000/
   ```
   Or open in browser: http://localhost:5000/

2. **Check health endpoint:**
   ```bash
   curl http://localhost:5000/health
   ```
   Or open in browser: http://localhost:5000/health

   This will show:
   - Status of portfolio XML loading
   - Status of website scraping
   - Source URL configuration

### Step 5: Test the API

#### Using curl:
```bash
curl -X POST http://localhost:5000/ask \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": \"Who is Manuj Rai?\"}"
```

#### Using PowerShell (Windows):
```powershell
Invoke-RestMethod -Uri "http://localhost:5000/ask" -Method POST -ContentType "application/json" -Body '{"prompt": "Who is Manuj Rai?"}'
```

#### Using Python:
```python
import requests

response = requests.post(
    "http://localhost:5000/ask",
    json={"prompt": "Who is Manuj Rai?"}
)
print(response.json())
```

#### Using Postman/Thunder Client:
- Method: POST
- URL: `http://localhost:5000/ask`
- Headers: `Content-Type: application/json`
- Body (JSON):
```json
{
  "prompt": "Who is Manuj Rai?",
  "model": "gpt-3.5-turbo"
}
```

## 📝 API Endpoints

### 1. `GET /`
- **Description:** Home endpoint
- **Response:** "Portfolio Q&A API is running live"

### 2. `GET /health`
- **Description:** Health check endpoint
- **Response:** 
```json
{
  "status": "ok",
  "version": "1.1",
  "portfolio_loaded": true,
  "website_loaded": true,
  "source_url": "https://manuj-rai.vercel.app/"
}
```

### 3. `POST /ask`
- **Description:** Ask a question about the portfolio
- **Request Body:**
```json
{
  "prompt": "Who is Manuj Rai?",
  "model": "gpt-3.5-turbo"  // Optional: defaults to gpt-3.5-turbo
}
```
- **Response:**
```json
{
  "response": "I'm Manuj Rai, a web developer...",
  "sources": ["snippet 1", "snippet 2"]
}
```

## 🔧 Troubleshooting

### Issue: Portfolio XML not loading
- **Solution:** Make sure `portfolio_data.xml` exists in the backend directory
- Check the `PORTFOLIO_PATH` in `.env` matches the actual filename

### Issue: Website not scraping
- **Solution:** 
  - Verify `SOURCE_URL` in `.env` is correct
  - Check internet connection
  - The scraper will try to crawl all pages from the domain

### Issue: OpenAI API errors
- **Solution:** 
  - Verify `OPENAI_API_KEY` in `.env` is correct
  - Check your OpenAI account has credits
  - Ensure the API key has proper permissions

### Issue: Port already in use
- **Solution:** Change the port in the run command:
  ```bash
  flask run --port=5001
  ```

### Issue: Module not found errors
- **Solution:** Make sure all dependencies are installed:
  ```bash
  pip install -r requirements.txt
  ```

## 📋 What Happens on Startup

When you start the application, it will:

1. ✅ Load system instructions from `instructions.txt`
2. ✅ Load and index your structured portfolio data (`portfolio_data.xml`)
3. ✅ Scrape and index all pages from your portfolio website
4. ✅ Build vector stores for semantic search
5. ✅ Be ready to answer questions!

## 🎯 Example Questions to Test

- "Who is Manuj Rai?"
- "Tell me about Manuj's skills"
- "What projects has Manuj worked on?"
- "Explain Manuj's experience in simple words"
- "What services does Manuj provide?"
- "Where is Manuj located?"
- "What technologies does Manuj know?"

## 🌐 CORS

CORS is enabled, so your frontend can make requests from any origin. If you need to restrict this, modify the CORS configuration in `app.py`.

---

**Happy Testing! 🚀**
