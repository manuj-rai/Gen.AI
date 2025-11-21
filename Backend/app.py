import os
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from PyPDF2 import PdfReader

# LangChain modules
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import EnsembleRetriever
from langchain.chains import RetrievalQA
from langchain.prompts.chat import ChatPromptTemplate

# ✅ OpenAI components from separate module (not from langchain_community)
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# Local module
from web_loader import fetch_clean_text_from_url

# =========================================================
# ENV & CONFIG
# =========================================================
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PDF_PATH = os.getenv("PDF_PATH", "Manuj Rai.pdf")
SOURCE_URL = os.getenv("SOURCE_URL", "https://manuj-rai.vercel.app/")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3
DEFAULT_MODEL = "gpt-3.5-turbo"
ALLOWED_MODELS = {"gpt-3.5-turbo", "gpt-4", "gpt-4o"}

ROOT_DIR = Path(os.path.dirname(__file__))
VECTOR_DIR = ROOT_DIR / "vectorstores"
INSTRUCTION_PATH = ROOT_DIR / "instructions.txt"
VECTOR_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# FLASK APP
# =========================================================
app = Flask(__name__)
CORS(app)

# =========================================================
# GLOBAL STATE
# =========================================================
pdf_vectorstore = None
web_vectorstore = None
pdf_loaded = False
web_loaded = False

pdf_lock = threading.RLock()
web_lock = threading.RLock()
executor = ThreadPoolExecutor(max_workers=2)

def load_system_prompt():
    try:
        return (INSTRUCTION_PATH.read_text(encoding="utf-8")).strip()
    except Exception as e:
        app.logger.warning(f"⚠️ Could not load system prompt: {e}")
        return "You are a helpful assistant that only answers from the resume and website."

system_prompt = load_system_prompt()

# =========================================================
# HELPERS
# =========================================================
def load_pdf_text(path):
    try:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            c = page.extract_text()
            if c:
                text += c + "\n"
        return text.strip()
    except Exception as e:
        app.logger.error(f"PDF read error: {e}")
        return ""

def build_vectorstore(text, source_tag):
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_text(text)
    metadata = [{"source": source_tag, "chunk": i} for i in range(len(chunks))]
    embeddings = OpenAIEmbeddings()
    return FAISS.from_texts(chunks, embedding=embeddings, metadatas=metadata)

def save_vectorstore(vs, name):
    try:
        path = VECTOR_DIR / name
        path.mkdir(parents=True, exist_ok=True)
        vs.save_local(str(path))
        app.logger.info(f"Saved vectorstore: {name}")
    except Exception as e:
        app.logger.warning(f"Could not save vectorstore '{name}': {e}")

def load_vectorstore(name):
    try:
        path = VECTOR_DIR / name
        if path.exists():
            return FAISS.load_local(str(path), OpenAIEmbeddings())
        return None
    except Exception as e:
        app.logger.warning(f"Failed to load vectorstore '{name}': {e}")
        return None

# =========================================================
# INDEXING HANDLERS
# =========================================================
def index_pdf(force=False):
    global pdf_vectorstore, pdf_loaded
    with pdf_lock:
        if pdf_loaded and not force:
            app.logger.debug("PDF already loaded, skipping index_pdf.")
            return
        app.logger.info("Indexing PDF...")
        text = load_pdf_text(str(ROOT_DIR / PDF_PATH))
        if not text:
            app.logger.warning("PDF empty or unreadable")
            return
        try:
            pdf_vectorstore = build_vectorstore(text, "resume")
            pdf_loaded = True
            save_vectorstore(pdf_vectorstore, "pdf")
            app.logger.info("PDF indexing complete.")
        except Exception as e:
            app.logger.error(f"Error building PDF vectorstore: {e}")
            pdf_loaded = False

def index_website(force=False):
    global web_vectorstore, web_loaded
    with web_lock:
        if web_loaded and not force:
            app.logger.debug("Website already loaded, skipping index_website.")
            return
        app.logger.info(f"Fetching website: {SOURCE_URL}")
        try:
            text = fetch_clean_text_from_url(SOURCE_URL)
        except Exception as e:
            app.logger.error(f"Error fetching website: {e}")
            text = ""
        if not text:
            app.logger.warning("Website content empty")
            return
        try:
            web_vectorstore = build_vectorstore(text, SOURCE_URL)
            web_loaded = True
            save_vectorstore(web_vectorstore, "website")
            app.logger.info("Website indexing complete.")
        except Exception as e:
            app.logger.error(f"Error building website vectorstore: {e}")
            web_loaded = False

def create_retriever(model_name):
    if pdf_vectorstore and web_vectorstore:
        return EnsembleRetriever(
            retrievers=[
                pdf_vectorstore.as_retriever(search_type="similarity", k=TOP_K),
                web_vectorstore.as_retriever(search_type="similarity", k=TOP_K)
            ],
            weights=[1.0, 1.0]
        )
    elif pdf_vectorstore:
        return pdf_vectorstore.as_retriever(search_type="similarity", k=TOP_K)
    elif web_vectorstore:
        return web_vectorstore.as_retriever(search_type="similarity", k=TOP_K)
    else:
        raise RuntimeError("No sources indexed")

# =========================================================
# STARTUP LOAD (Persistent)
# =========================================================
loaded_pdf = load_vectorstore("pdf")
if loaded_pdf:
    pdf_vectorstore = loaded_pdf
    pdf_loaded = True
    app.logger.info("Loaded PDF vectorstore from disk.")

loaded_web = load_vectorstore("website")
if loaded_web:
    web_vectorstore = loaded_web
    web_loaded = True
    app.logger.info("Loaded website vectorstore from disk.")

try:
    if not pdf_loaded:
        app.logger.info("No saved PDF vectorstore found — indexing PDF synchronously at startup.")
        index_pdf(force=False)
    if not web_loaded:
        app.logger.info("No saved website vectorstore found — indexing website synchronously at startup.")
        index_website(force=False)
except Exception as e:
    app.logger.error(f"Startup indexing failed: {e}\n{traceback.format_exc()}")

# =========================================================
# ROUTES
# =========================================================
@app.route("/")
def home():
    return "AI Backend Running"

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "pdf_loaded": pdf_loaded,
        "website_loaded": web_loaded,
        "source_url": SOURCE_URL
    })

@app.route("/reindex", methods=["POST"])
def reindex():
    body = request.get_json() or {}
    target = body.get("target", "both")

    if target in ("pdf", "both"):
        executor.submit(index_pdf, True)
    if target in ("website", "both"):
        executor.submit(index_website, True)

    return jsonify({"message": "Reindex started", "target": target})

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.get_json() or {}
        prompt = (data.get("prompt") or "").strip()
        model = data.get("model", DEFAULT_MODEL)

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400
        if model not in ALLOWED_MODELS:
            return jsonify({"error": f"invalid model {model}"}), 400
        if not (pdf_loaded or web_loaded):
            return jsonify({"message": "Indexing... try again soon"}), 202

        retriever = create_retriever(model)
        qa_chain = RetrievalQA.from_chain_type(
            llm=ChatOpenAI(model_name=model, temperature=0),
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs={
                "prompt": ChatPromptTemplate.from_messages([
                    ("system", system_prompt),
                    ("human", "{question}")
                ])
            }
        )

        result = qa_chain(prompt)
        answer = result["result"]
        sources = [{"snippet": doc.page_content[:400], "metadata": doc.metadata} for doc in result["source_documents"]]

        return jsonify({"response": answer, "sources": sources})

    except Exception as e:
        app.logger.error(traceback.format_exc())
        return jsonify({
            "error": "internal_server_error",
            "detail": str(e)
        }), 500

# =========================================================
# MAIN (local debug)
# =========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
