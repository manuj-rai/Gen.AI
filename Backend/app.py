from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import threading
import traceback
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.retrievers import EnsembleRetriever
from langchain.prompts import PromptTemplate

from web_loader import get_all_pages_from_website

# ------------------------------------------------------------------
# Load environment variables from .env
# ------------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORTFOLIO_PATH = os.path.join(
    os.path.dirname(__file__),
    os.getenv("PORTFOLIO_PATH")
    or os.getenv("PDF_PATH", "portfolio_data.xml")
)
SOURCE_URL = os.getenv("SOURCE_URL")
INSTRUCTIONS_PATH = os.path.join(os.path.dirname(__file__), "instructions.txt")

# ------------------------------------------------------------------
# Flask app setup
# ------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# ------------------------------------------------------------------
# Configuration constants
# ------------------------------------------------------------------
DEFAULT_MODEL = "gpt-3.5-turbo"                        # Default OpenAI model
ALLOWED_MODELS = ["gpt-3.5-turbo", "gpt-4", "gpt-4o"]  # Supported model list


def _env_flag(name: str, default: str = "false") -> bool:
    """Return True if the env var represents an affirmative value."""
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """Parse an int env var safely."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        print(f"⚠️ Invalid integer for {name}={raw_value!r}. Falling back to {default}.")
        return default


# Allow legacy ENABLE_PDF_PRELOAD to keep working as the default signal.
_default_portfolio_preload = os.getenv("ENABLE_PDF_PRELOAD", "true")
ENABLE_PORTFOLIO_PRELOAD = _env_flag("ENABLE_PORTFOLIO_PRELOAD", _default_portfolio_preload)
ENABLE_WEBSITE_PRELOAD = _env_flag("ENABLE_WEBSITE_PRELOAD", "true")
WEBSITE_PRELOAD_MODE = os.getenv("WEBSITE_PRELOAD_MODE", "background").lower()
USE_PLAYWRIGHT = _env_flag("USE_PLAYWRIGHT", "false")
MAX_WEB_PAGES = _env_int("MAX_WEB_PAGES", 15)

if WEBSITE_PRELOAD_MODE not in {"background", "sync"}:
    print(f"⚠️ Unknown WEBSITE_PRELOAD_MODE={WEBSITE_PRELOAD_MODE!r}. Falling back to 'background'.")
    WEBSITE_PRELOAD_MODE = "background"

# ------------------------------------------------------------------
# Global vectorstores for each content source
# ------------------------------------------------------------------
portfolio_vectorstore = None
web_vectorstore = None
system_instructions = None

# ------------------------------------------------------------------
# Load and extract text from the structured XML data file
# ------------------------------------------------------------------
def load_portfolio_text(xml_path):
    try:
        if not os.path.exists(xml_path):
            raise FileNotFoundError(f"{xml_path} does not exist.")

        tree = ET.parse(xml_path)
        root = tree.getroot()
        lines = []

        def walk(node, depth=0):
            label = node.tag.replace("_", " ").strip()
            content = (node.text or "").strip()
            indent = "  " * depth

            if content:
                lines.append(f"{indent}{label}: {content}")
            elif node:
                lines.append(f"{indent}{label}:")

            for child in node:
                walk(child, depth + 1)

        walk(root)
        return "\n".join(line for line in lines if line).strip()
    except FileNotFoundError as e:
        print(f"❌ Portfolio file not found: {e}")
        return ""
    except Exception as e:
        print(f"❌ Error parsing portfolio XML: {e}")
        return ""

# ------------------------------------------------------------------
# Load system instructions from instructions.txt
# ------------------------------------------------------------------
def load_system_instructions():
    global system_instructions
    try:
        if os.path.exists(INSTRUCTIONS_PATH):
            with open(INSTRUCTIONS_PATH, "r", encoding="utf-8") as f:
                system_instructions = f.read().strip()
            print("✅ System instructions loaded.")
        else:
            print("⚠️ Instructions file not found. Using default behavior.")
            system_instructions = "You are a helpful assistant that answers questions based on the provided context."
    except Exception as e:
        print(f"⚠️ Error loading instructions: {e}")
        system_instructions = "You are a helpful assistant that answers questions based on the provided context."

# ------------------------------------------------------------------
# Build a vectorstore from raw text using LangChain + FAISS
# ------------------------------------------------------------------
def build_vector_store(text):
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text(text)
    embeddings = OpenAIEmbeddings()
    return FAISS.from_texts(chunks, embedding=embeddings)

# ------------------------------------------------------------------
# Load portfolio XML and build vectorstore (if successful)
# ------------------------------------------------------------------
def preload_portfolio_data():
    global portfolio_vectorstore
    print(f"📄 Attempting to load portfolio data at: {PORTFOLIO_PATH}")

    try:
        text = load_portfolio_text(PORTFOLIO_PATH)
        if text:
            portfolio_vectorstore = build_vector_store(text)
            print("✅ Portfolio data indexed.")
        else:
            print("⚠️ Portfolio file loaded but produced no usable text.")
    except FileNotFoundError:
        print(f"❌ Portfolio file not found: {PORTFOLIO_PATH}")
    except Exception as e:
        print(f"❌ Error reading portfolio file: {e}")

# ------------------------------------------------------------------
# Load website content and build vectorstore (if successful)
# Scrapes all pages from the website domain
# ------------------------------------------------------------------
def preload_website_data():
    global web_vectorstore
    if not SOURCE_URL:
        print("⚠️ SOURCE_URL not configured. Skipping website scraping.")
        return
    
    print(f"🌐 Starting to crawl website: {SOURCE_URL} (max_pages={MAX_WEB_PAGES})")
    text = get_all_pages_from_website(
        SOURCE_URL,
        max_pages=MAX_WEB_PAGES
    )
    if text:
        web_vectorstore = build_vector_store(text)
        print("✅ Website indexed (all pages).")
    else:
        print("⚠️ Website returned no usable content.")

# ------------------------------------------------------------------
# Build a RetrievalQA chain using one or both sources
# ------------------------------------------------------------------
def create_fallback_qa_chain(model_name):
    # Prefer both sources if available
    if portfolio_vectorstore and web_vectorstore:
        print("✅ Using both portfolio XML and website sources.")
        retriever = EnsembleRetriever(
            retrievers=[
                portfolio_vectorstore.as_retriever(search_type="similarity", k=3),
                web_vectorstore.as_retriever(search_type="similarity", k=3)
            ],
            weights=[1.0, 1.0]
        )

    # Use only portfolio XML if website failed
    elif portfolio_vectorstore:
        print("⚠️ Website unavailable. Using portfolio data only.")
        retriever = portfolio_vectorstore.as_retriever(search_type="similarity", k=3)

    # Use only Website if portfolio failed
    elif web_vectorstore:
        print("⚠️ Portfolio data unavailable. Using website only.")
        retriever = web_vectorstore.as_retriever(search_type="similarity", k=3)

    # Fail if both are unavailable
    else:
        raise RuntimeError("❌ No sources available for answering.")

    # Create custom prompt with system instructions
    prompt_template = f"""{system_instructions or "You are a helpful assistant."}

Use the following pieces of context to answer the question. If you don't know the answer based on the context, just say that you don't have that information, don't try to make up an answer.

Context: {{context}}

Question: {{question}}

Answer:"""

    PROMPT = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )

    # Build the QA chain with the chosen retriever and custom prompt
    return RetrievalQA.from_chain_type(
        llm=ChatOpenAI(temperature=0.7, model_name=model_name),
        retriever=retriever,
        chain_type="stuff",
        chain_type_kwargs={"prompt": PROMPT},
        return_source_documents=True
    )


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.route("/")
def home():
    return "Portfolio Q&A API is running live"

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "1.1",
        "portfolio_loaded": portfolio_vectorstore is not None,
        "website_loaded": web_vectorstore is not None,
        "source_url": SOURCE_URL
    })

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.get_json()
        prompt = data.get("prompt", "").strip()
        model = data.get("model", DEFAULT_MODEL)

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        if model not in ALLOWED_MODELS:
            return jsonify({"error": f"Invalid model: {model}"}), 400

        # Create QA chain based on available sources
        qa_chain = create_fallback_qa_chain(model)
        result = qa_chain(prompt)

        # Prepare response with answer and snippet sources
        return jsonify({
            "response": result["result"],
            "sources": [doc.page_content[:200] for doc in result["source_documents"]]
        })

    except Exception as e:
        print("❌ Exception:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    
# ------------------------------------------------------------------
# Run preload logic immediately on import (for Gunicorn compatibility)
# ------------------------------------------------------------------
print("🚀 App is starting... loading sources.")

# Load system instructions first
load_system_instructions()

if ENABLE_PORTFOLIO_PRELOAD:
    try:
        preload_portfolio_data()
        print("✅ Finished loading portfolio data.")
    except Exception as e:
        print(f"⚠️ Portfolio load failed: {e}")
else:
    print("ℹ️ Portfolio preload disabled via ENABLE_PORTFOLIO_PRELOAD.")

def _load_website_sources():
    try:
        preload_website_data()
        print("✅ Finished loading website.")
    except Exception as e:
        print(f"⚠️ Website load failed: {e}")

if ENABLE_WEBSITE_PRELOAD:
    if WEBSITE_PRELOAD_MODE == "background":
        print("⏳ Website preload running in a background thread.")
        threading.Thread(target=_load_website_sources, name="website-preload", daemon=True).start()
    else:
        _load_website_sources()
else:
    print("ℹ️ Website preload disabled via ENABLE_WEBSITE_PRELOAD.")

# ------------------------------------------------------------------
# Start the app locally (for development/testing)
# Note: Preloading happens at import time above for Gunicorn compatibility
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Sources are already loaded at import time, so we just start the server
    print("🚀 Starting Flask development server...")
    app.run(debug=True, host="0.0.0.0", port=5000)
