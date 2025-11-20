from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import traceback
import threading
from dotenv import load_dotenv
from PyPDF2 import PdfReader

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.retrievers import EnsembleRetriever

from web_loader import fetch_clean_text_from_url

# ------------------------------------------------------------------
# Load environment variables
# ------------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PDF_PATH = os.path.join(os.path.dirname(__file__), os.getenv("PDF_PATH", "Manuj Rai.pdf"))
SOURCE_URL = os.getenv("SOURCE_URL")

# ------------------------------------------------------------------
# Flask app setup
# ------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

DEFAULT_MODEL = "gpt-3.5-turbo"
ALLOWED_MODELS = ["gpt-3.5-turbo", "gpt-4", "gpt-4o"]

# ------------------------------------------------------------------
# Global Vectorstores
# ------------------------------------------------------------------
pdf_vectorstore = None
web_vectorstore = None

pdf_loaded = False
web_loaded = False

# ------------------------------------------------------------------
# PDF Loader
# ------------------------------------------------------------------
def load_pdf_text(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text += content + "\n"
        return text.strip()
    except Exception as e:
        print(f"❌ Error loading PDF: {e}")
        return ""

def async_load_pdf():
    global pdf_vectorstore, pdf_loaded
    try:
        print(f"📄 Background: loading PDF {PDF_PATH}")
        text = load_pdf_text(PDF_PATH)
        if text:
            pdf_vectorstore = build_vector_store(text)
            pdf_loaded = True
            print("✅ PDF indexed (background).")
        else:
            print("⚠️ PDF loaded but empty.")
    except Exception as e:
        print(f"❌ PDF load failed: {e}")

# ------------------------------------------------------------------
# Website Loader
# ------------------------------------------------------------------
def async_load_website():
    global web_vectorstore, web_loaded
    try:
        print(f"🌐 Background: fetching {SOURCE_URL}")
        text = fetch_clean_text_from_url(SOURCE_URL)
        if text:
            web_vectorstore = build_vector_store(text)
            web_loaded = True
            print("✅ Website indexed (background).")
        else:
            print("⚠️ No usable website content.")
    except Exception as e:
        print(f"❌ Website load failed: {e}")

# ------------------------------------------------------------------
# Build Vectorstore
# ------------------------------------------------------------------
def build_vector_store(text):
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text(text)
    embeddings = OpenAIEmbeddings()
    return FAISS.from_texts(chunks, embedding=embeddings)

# ------------------------------------------------------------------
# Combined Retrieval
# ------------------------------------------------------------------
def create_fallback_qa_chain(model_name):
    if pdf_vectorstore and web_vectorstore:
        retriever = EnsembleRetriever(
            retrievers=[
                pdf_vectorstore.as_retriever(search_type="similarity", k=3),
                web_vectorstore.as_retriever(search_type="similarity", k=3)
            ], 
            weights=[1.0, 1.0]
        )
    elif pdf_vectorstore:
        retriever = pdf_vectorstore.as_retriever(search_type="similarity", k=3)
    elif web_vectorstore:
        retriever = web_vectorstore.as_retriever(search_type="similarity", k=3)
    else:
        raise RuntimeError("❌ No sources indexed yet.")

    return RetrievalQA.from_chain_type(
        llm=ChatOpenAI(temperature=0, model_name=model_name),
        retriever=retriever,
        return_source_documents=True
    )

# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@app.route("/")
def home():
    return "Server is running live"

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "pdf_loaded": pdf_loaded,
        "website_loaded": web_loaded,
        "source_url": SOURCE_URL
    })

@app.route("/ask", methods=["POST"])
def ask():
    global pdf_loaded, web_loaded

    try:
        data = request.get_json()
        prompt = data.get("prompt", "").strip()
        model = data.get("model", DEFAULT_MODEL)

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        if model not in ALLOWED_MODELS:
            return jsonify({"error": f"Invalid model: {model}"}), 400

        # Lazy loading
        if not pdf_loaded:
            threading.Thread(target=async_load_pdf, daemon=True).start()

        if not web_loaded:
            threading.Thread(target=async_load_website, daemon=True).start()

        if not (pdf_vectorstore or web_vectorstore):
            return jsonify({"message": "Data is still indexing... try again shortly."})

        qa_chain = create_fallback_qa_chain(model)
        result = qa_chain(prompt)

        return jsonify({
            "response": result["result"],
            "sources": [doc.page_content[:200] for doc in result["source_documents"]]
        })

    except Exception as e:
        print("❌ Exception:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------------
# Background loading at startup (non-blocking)
# ------------------------------------------------------------------
threading.Thread(target=async_load_pdf, daemon=True).start()
threading.Thread(target=async_load_website, daemon=True).start()

print("🚀 App started instantly — background indexing running.")
