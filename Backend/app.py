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

from web_loader import fetch_clean_text_from_url

# ------------------------------------------------------------------
# Load environment variables (especially OPENAI_API_KEY)
# ------------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SOURCE_URL = os.getenv("SOURCE_URL")

# ------------------------------------------------------------------
# Flask setup
# ------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
PDF_PATH = "Manuj Rai.pdf"                 # Static PDF file
INSTRUCTION_PATH = "instructions.txt"      # System instruction file
DEFAULT_MODEL = "gpt-3.5-turbo"             # Default model to use
ALLOWED_MODELS = ["gpt-3.5-turbo", "gpt-4", "gpt-4o"] # Valid models

# ------------------------------------------------------------------
# Global variables
# ------------------------------------------------------------------
vectorstore = None
system_instruction = ""

# ------------------------------------------------------------------
# Helper: Load PDF and extract text
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
# Helper: Load system instruction from file
# ------------------------------------------------------------------
def load_system_instruction():
    try:
        with open(INSTRUCTION_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"⚠️ Could not load instructions.txt: {e}")
        return "You are a helpful assistant. Answer based only on the provided context."

# ------------------------------------------------------------------
# Helper: Build FAISS vector store from text
# ------------------------------------------------------------------
def build_vector_store(text):
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text(text)
    embeddings = OpenAIEmbeddings()
    return FAISS.from_texts(chunks, embedding=embeddings)

# ------------------------------------------------------------------
# Helper: Create LangChain QA chain
# ------------------------------------------------------------------
def create_qa_chain(vectorstore, model_name):
    retriever = vectorstore.as_retriever(search_type="similarity", k=3)
    return RetrievalQA.from_chain_type(
        llm=ChatOpenAI(temperature=0, model_name=model_name),
        retriever=retriever,
        chain_type_kwargs={"prompt": None},  # Uses LangChain's default prompt
        return_source_documents=True
    )

# ------------------------------------------------------------------
# Load everything once at app start
# ------------------------------------------------------------------
def preload_data():
    global vectorstore, system_instruction
    system_instruction = load_system_instruction()
    text = load_pdf_text(PDF_PATH)
    vectorstore = build_vector_store(text)
    print("✅ PDF and system instruction loaded.")


def preload_website_data():
    global vectorstore
    print(f"🌐 Loading content from: {SOURCE_URL}")
    text = fetch_clean_text_from_url(SOURCE_URL)
    if not text:
        raise RuntimeError("❌ Failed to load content from URL")
    vectorstore = build_vector_store(text)
    print("✅ Content loaded and indexed.")    


# ------------------------------------------------------------------
# API: Homepage
# ------------------------------------------------------------------
@app.route("/")
def home():
    return "✅ PDF RAG Q&A API is running."


# ------------------------------------------------------------------
# API: Health check
# ------------------------------------------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "1.0"})


# ------------------------------------------------------------------
# API: Ask a question
# ------------------------------------------------------------------
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

        qa_chain = create_qa_chain(vectorstore, model_name=model)
        result = qa_chain(prompt)

        answer = result["result"]
        source_chunks = [
            doc.page_content[:200] for doc in result["source_documents"]
        ]

        return jsonify({
            "response": answer,
            "sources": source_chunks
        })

    except Exception as e:
        print("❌ Exception:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------------
# App entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    preload_data()
    app.run(debug=True, host="0.0.0.0", port=5000)
