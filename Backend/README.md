# Manuj Portfolio Assistant Backend

This backend powers an AI assistant for Manuj Rai's portfolio site. It uses Retrieval-Augmented Generation (RAG) to answer questions from verified portfolio data instead of hallucinating or pretending to be Manuj.

The original version behaved like "Manuj himself" and returned one full response at the end. This upgraded version behaves like **Manuj's assistant**, supports **streaming responses**, keeps **source metadata**, accepts **chat history**, and is structured more safely for **production use on Render**.

## What This Backend Does

When a visitor asks a question:

1. The backend receives the prompt and optional conversation history.
2. It retrieves relevant context from:
   - `portfolio_data.xml`
   - the portfolio website pages from `SOURCE_URL`
3. It builds a grounded prompt using only that verified context.
4. It sends the request to the OpenAI Responses API.
5. It returns either:
   - a normal JSON response from `POST /ask`
   - a streaming SSE response from `POST /ask/stream`

The assistant answers as a helpful portfolio assistant, not as Manuj directly.

## Why This Version Is Better

- It no longer impersonates you. That is safer and more professional for recruiters and clients.
- It uses retrieved context first, then generation. That makes answers more accurate.
- It supports streaming, so the frontend can render the answer live.
- It supports multi-turn chat with `messages`.
- It returns richer source info for debugging and trust.
- It exposes `health` and `ready` endpoints for deployment monitoring.
- It uses a Gunicorn threaded worker setup that is more suitable for streaming than a single sync worker.

## Tech Stack

- Flask
- Gunicorn
- OpenAI Responses API
- LangChain text splitting + retrievers
- FAISS vector store
- OpenAI embeddings
- BeautifulSoup / requests crawler
- Optional Playwright fallback for JS-heavy sites

## Architecture

### 1. Data Sources

- `portfolio_data.xml`
  - Structured, high-trust personal/professional data.
- `SOURCE_URL`
  - Crawled website pages for extra live portfolio content.

### 2. Indexing

- XML sections are converted into documents.
- Website pages are crawled and stored with page URL/title metadata.
- Documents are split into chunks.
- Chunks are embedded with OpenAI embeddings.
- Vectors are stored in FAISS.

### 3. Retrieval

- On each question, the app pulls the most relevant chunks.
- If both XML and website indexes exist, it uses both.
- Retrieved chunks are combined into grounded context.

### 4. Generation

- The backend sends:
  - assistant instructions
  - recent chat history
  - retrieved context
  - the latest user question
- OpenAI generates the final answer.

### 5. Delivery

- `POST /ask` returns a full JSON response.
- `POST /ask/stream` returns server-sent events for live rendering.

## API Endpoints

### `GET /`

Basic API info.

### `GET /health`

Returns service status, source loading status, configured model info, and whether the API is ready.

### `GET /ready`

Returns `200` only when:

- `OPENAI_API_KEY` is configured
- at least one knowledge source is loaded

Otherwise it returns `503`.

### `POST /ask`

Synchronous response.

Request body:

```json
{
  "prompt": "What kind of work does Manuj do?",
  "model": "gpt-4o",
  "messages": [
    { "role": "user", "content": "Tell me about Manuj." },
    { "role": "assistant", "content": "Manuj is a full-stack developer..." }
  ],
  "session_id": "portfolio-web-1"
}
```

Response:

```json
{
  "id": "request_id",
  "model": "gpt-4o",
  "response": "Manuj is a full-stack developer focused on React, .NET, Python, and SQL Server...",
  "tokens": 321,
  "usage": {
    "input_tokens": 250,
    "output_tokens": 71,
    "total_tokens": 321
  },
  "source_count": 4,
  "sources": [
    {
      "index": 1,
      "title": "Portfolio XML - Experience",
      "source_type": "portfolio_xml",
      "url": null,
      "source_id": "portfolio:experience",
      "preview": "experience: ..."
    }
  ]
}
```

### `POST /ask/stream`

Streaming response using `text/event-stream`.

The stream emits:

- `meta`
- `delta`
- `done`
- `error`

This is meant for `fetch()` + `ReadableStream` on the frontend.

Example JavaScript client:

```js
const response = await fetch("https://your-render-url.onrender.com/ask/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    prompt: "Summarize Manuj's projects",
    model: "gpt-4o"
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { value, done } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const events = buffer.split("\n\n");
  buffer = events.pop() || "";

  for (const rawEvent of events) {
    const lines = rawEvent.split("\n");
    const event = lines.find((line) => line.startsWith("event:"))?.replace("event:", "").trim();
    const dataLine = lines.find((line) => line.startsWith("data:"))?.replace("data:", "").trim();
    if (!event || !dataLine) continue;

    const data = JSON.parse(dataLine);

    if (event === "delta") {
      console.log("chunk:", data.text);
    }

    if (event === "done") {
      console.log("final:", data.response);
      console.log("sources:", data.sources);
    }
  }
}
```

## Local Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Optional for JS-rendered sites:

```bash
playwright install chromium
```

### 2. Create `.env`

```env
OPENAI_API_KEY=your_openai_api_key
SOURCE_URL=https://manuj-rai.vercel.app/
PORTFOLIO_PATH=portfolio_data.xml
OPENAI_MODEL=gpt-4o
ALLOWED_MODELS=gpt-4o,gpt-4o-mini
CORS_ORIGINS=https://your-portfolio-domain.com

ENABLE_PORTFOLIO_PRELOAD=true
ENABLE_WEBSITE_PRELOAD=true
WEBSITE_PRELOAD_MODE=background
USE_PLAYWRIGHT=false
MAX_WEB_PAGES=15

CHUNK_SIZE=900
CHUNK_OVERLAP=120
RETRIEVER_K=4
MAX_HISTORY_MESSAGES=6
MAX_CONTEXT_CHARS=12000
MAX_OUTPUT_TOKENS=450
OPENAI_TEMPERATURE=0.2
REQUEST_TIMEOUT_SECONDS=60
OPENAI_TRUNCATION=auto
```

### 3. Run locally

```bash
python app.py
```

Or production-like:

```bash
gunicorn app:app --worker-class gthread --workers 1 --threads 8 --timeout 300 --bind 0.0.0.0:5000
```

## Render Notes

This repo includes a `Procfile`:

```txt
web: gunicorn app:app --worker-class gthread --workers 1 --threads 8 --timeout 300 --bind 0.0.0.0:$PORT
```

Why `gthread`?

- Streaming keeps requests open longer.
- A single sync worker can become a bottleneck.
- Threads give a safer baseline for concurrent streaming + health checks on a small Render deployment.

## Environment Variables Explained

### Required

- `OPENAI_API_KEY`
  - Needed for embeddings and generation.
- `SOURCE_URL`
  - Website to crawl for portfolio content.

### Core

- `PORTFOLIO_PATH`
  - Path to the structured XML file.
- `OPENAI_MODEL`
  - Default generation model.
- `ALLOWED_MODELS`
  - Models the API will accept from callers.
- `CORS_ORIGINS`
  - Comma-separated allowed frontend origins.

### Preload / Crawling

- `ENABLE_PORTFOLIO_PRELOAD`
  - Load XML into the vector index on startup.
- `ENABLE_WEBSITE_PRELOAD`
  - Crawl and index website data on startup.
- `WEBSITE_PRELOAD_MODE`
  - `background` or `sync`.
- `USE_PLAYWRIGHT`
  - Enables a browser-based crawl path if requests-only scraping is not enough.
- `MAX_WEB_PAGES`
  - Crawl limit.

### Retrieval / Prompting

- `CHUNK_SIZE`
  - Chunk size for vector indexing.
- `CHUNK_OVERLAP`
  - Overlap between chunks.
- `RETRIEVER_K`
  - How many chunks to retrieve.
- `MAX_HISTORY_MESSAGES`
  - Recent messages included in each request.
- `MAX_CONTEXT_CHARS`
  - Cap on retrieved context size sent to the model.

### Model Controls

- `MAX_OUTPUT_TOKENS`
  - Output budget.
- `OPENAI_TEMPERATURE`
  - Lower values are more stable and factual.
- `REQUEST_TIMEOUT_SECONDS`
  - API timeout.
- `OPENAI_TRUNCATION`
  - `auto` is safer for production.

## How To Explain This In An Interview

### Short version

"I built a portfolio assistant backend using Flask, FAISS, LangChain, and OpenAI. It uses RAG, which means I first retrieve relevant context from my structured portfolio XML and website content, then send only that grounded context to the model. I also upgraded it to support streaming responses, health checks, source metadata, and a more production-safe assistant persona instead of direct impersonation."

### Slightly deeper version

"The backend has two ingestion paths: a structured XML source for high-confidence personal and professional data, and a web crawler for portfolio pages. Both are chunked, embedded, and indexed into FAISS. At runtime, I retrieve the most relevant chunks, combine them into context, and use the OpenAI Responses API to generate an answer. I added a synchronous endpoint and a streaming endpoint, plus deployment-friendly health/readiness checks and threaded Gunicorn config for Render."

### Why these choices make sense

- **Flask**
  - Lightweight and easy to deploy on Render.
- **XML + website hybrid**
  - XML gives trusted data, website pages add breadth.
- **FAISS**
  - Fast local vector retrieval without needing a managed vector DB.
- **RAG**
  - Better grounding and less hallucination.
- **Responses API**
  - Better fit for modern OpenAI integrations and streaming.
- **SSE streaming**
  - Improves chat UX because the UI can render the answer as it is generated.
- **Assistant persona**
  - Better trust boundary than pretending to be the real person.

## What Changed From The Old Version

- Replaced the old RetrievalQA chain with explicit retrieval + Responses API generation.
- Changed the persona from "I am Manuj" to "I am Manuj's assistant".
- Added `POST /ask/stream`.
- Added chat history support through `messages`.
- Added richer sources with metadata instead of plain text snippets only.
- Added `GET /ready`.
- Added better startup status tracking.
- Updated the Gunicorn process model for streaming.

## Production Gaps You Can Add Later

If you want to take it even further later, these are the next strong upgrades:

- Rate limiting
- Request authentication for private/admin endpoints
- Structured logging and tracing
- Automated evaluation prompts / regression tests
- Persistent vector index caching
- Source refresh jobs
- Redis for caching or chat session state

## Quick Test Commands

### Health

```bash
curl http://localhost:5000/health
```

### Ready

```bash
curl http://localhost:5000/ready
```

### Ask

```bash
curl -X POST http://localhost:5000/ask \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": \"What kind of projects has Manuj built?\", \"model\": \"gpt-4o\"}"
```

### Stream

```bash
curl -N -X POST http://localhost:5000/ask/stream \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": \"Summarize Manuj's experience\", \"model\": \"gpt-4o\"}"
```

## Final Summary

This backend is now a stronger portfolio assistant service, not just a demo chatbot. It is grounded, stream-capable, safer in how it represents you, and much easier to explain as a real engineering project.
