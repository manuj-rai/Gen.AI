from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import traceback
from dotenv import load_dotenv
from PyPDF2 import PdfReader

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.retrievers import EnsembleRetriever

from web_loader import fetch_clean_text_from_url

# ------------------------------------------------------------------
# Load environment variables from .env
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

# ------------------------------------------------------------------
# Configuration constants
# ------------------------------------------------------------------
DEFAULT_MODEL = "gpt-3.5-turbo"                        # Default OpenAI model
ALLOWED_MODELS = ["gpt-3.5-turbo", "gpt-4", "gpt-4o"]  # Supported model list

# ------------------------------------------------------------------
# Global vectorstores for each content source
# ------------------------------------------------------------------
pdf_vectorstore = None
web_vectorstore = None

# ------------------------------------------------------------------
# Load and extract text from a PDF file
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

# ------------------------------------------------------------------
# Build a vectorstore from raw text using LangChain + FAISS
# ------------------------------------------------------------------
def build_vector_store(text):
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text(text)
    embeddings = OpenAIEmbeddings()
    return FAISS.from_texts(chunks, embedding=embeddings)

# ------------------------------------------------------------------
# Load PDF and build vectorstore (if successful)
# ------------------------------------------------------------------
def preload_pdf_data():
    global pdf_vectorstore
    print(f"📄 Attempting to load PDF at: {PDF_PATH}")

    try:
        text = load_pdf_text(PDF_PATH)
        if text:
            pdf_vectorstore = build_vector_store(text)
            print("✅ PDF indexed.")
        else:
            print("⚠️ PDF loaded but has no extractable text.")
    except FileNotFoundError:
        print(f"❌ PDF file not found: {PDF_PATH}")
    except Exception as e:
        print(f"❌ Error reading PDF: {e}")

# ------------------------------------------------------------------
# Load website content and build vectorstore (if successful)
# ------------------------------------------------------------------
def preload_website_data():
    global web_vectorstore
    print(f"🌐 Fetching from: {SOURCE_URL}")
    text = fetch_clean_text_from_url(SOURCE_URL)
    if text:
        web_vectorstore = build_vector_store(text)
        print("✅ Website indexed.")
    else:
        print("⚠️ Website returned no usable content.")

# ------------------------------------------------------------------
# Build a RetrievalQA chain using one or both sources
# ------------------------------------------------------------------
def create_fallback_qa_chain(model_name):
    # Prefer both sources if available
    if pdf_vectorstore and web_vectorstore:
        print("✅ Using both PDF and Website sources.")
        retriever = EnsembleRetriever(
            retrievers=[
                pdf_vectorstore.as_retriever(search_type="similarity", k=3),
                web_vectorstore.as_retriever(search_type="similarity", k=3)
            ],
            weights=[1.0, 1.0]
        )

    # Use only PDF if website failed
    elif pdf_vectorstore:
        print("⚠️ Website unavailable. Using PDF only.")
        retriever = pdf_vectorstore.as_retriever(search_type="similarity", k=3)

    # Use only Website if PDF failed
    elif web_vectorstore:
        print("⚠️ PDF unavailable. Using Website only.")
        retriever = web_vectorstore.as_retriever(search_type="similarity", k=3)

    # Fail if both are unavailable
    else:
        raise RuntimeError("❌ No sources available for answering.")

    # Build the QA chain with the chosen retriever
    return RetrievalQA.from_chain_type(
        llm=ChatOpenAI(temperature=0, model_name=model_name),
        retriever=retriever,
        chain_type_kwargs={"prompt": None},
        return_source_documents=True
    )


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.route("/")
def home():
    return "✅ PDF + Website Q&A API is running"

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "1.1",
        "pdf_loaded": pdf_vectorstore is not None,
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
# Start the app and preload sources
# ------------------------------------------------------------------
if __name__ == "__main__":
    try:
        preload_pdf_data()
    except Exception as e:
        print(f"⚠️ PDF load failed: {e}")

    try:
        preload_website_data()
    except Exception as e:
        print(f"⚠️ Website load failed: {e}")

    app.run(debug=True, host="0.0.0.0", port=5000)
