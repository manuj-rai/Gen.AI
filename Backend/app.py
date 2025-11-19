from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import traceback
from dotenv import load_dotenv
from PyPDF2 import PdfReader

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.retrievers import EnsembleRetriever
from langchain.prompts import PromptTemplate

from web_loader import fetch_clean_text_from_url

# ------------------------------------------------------------------
# Load environment variables from .env
# ------------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PDF_PATH = os.path.join(os.path.dirname(__file__), os.getenv("PDF_PATH", "Manuj Rai.pdf"))
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

# ------------------------------------------------------------------
# Global vectorstores for each content source and system instructions
# ------------------------------------------------------------------
pdf_vectorstore = None
web_vectorstore = None
system_instructions = ""

# ------------------------------------------------------------------
# Load system instructions for HR Policy Assistant
# ------------------------------------------------------------------
def load_system_instructions():
    global system_instructions
    try:
        with open(INSTRUCTIONS_PATH, 'r', encoding='utf-8') as f:
            system_instructions = f.read()
        print("✅ System instructions loaded successfully.")
    except FileNotFoundError:
        print(f"⚠️ Instructions file not found at {INSTRUCTIONS_PATH}. Using default behavior.")
        system_instructions = "You are a helpful HR Policy Assistant. Provide clear, accurate, and friendly answers about company policies and procedures."
    except Exception as e:
        print(f"⚠️ Error loading instructions: {e}")
        system_instructions = "You are a helpful HR Policy Assistant. Provide clear, accurate, and friendly answers about company policies and procedures."

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
# Build a RetrievalQA chain using one or both sources with custom prompt
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

    # Create custom prompt template with HR instructions
    prompt_template = f"""{system_instructions}

---

## Context Information:
{{context}}

---

## Employee Question:
{{question}}

## Your Response:
Remember to be warm, supportive, and human-like in your answer. Use the context above to provide accurate information while following the conversation style guidelines."""

    PROMPT = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )

    # Build the QA chain with the chosen retriever and custom prompt
    return RetrievalQA.from_chain_type(
        llm=ChatOpenAI(temperature=0.3, model_name=model_name),  # Slightly higher temperature for more natural responses
        retriever=retriever,
        chain_type_kwargs={"prompt": PROMPT},
        return_source_documents=True
    )


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.route("/")
def home():
    return jsonify({
        "message": "HR Policy Assistant API is running",
        "version": "2.0",
        "description": "AI-powered HR assistant for company policies and employee support",
        "endpoints": {
            "/health": "Check system status",
            "/ask": "POST - Ask HR policy questions"
        }
    })

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "HR Policy Assistant",
        "version": "2.0",
        "pdf_loaded": pdf_vectorstore is not None,
        "website_loaded": web_vectorstore is not None,
        "instructions_loaded": len(system_instructions) > 0,
        "source_url": SOURCE_URL,
        "ready": pdf_vectorstore is not None or web_vectorstore is not None
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
print("🚀 HR Policy Assistant is starting... loading sources.")

# Load system instructions first
load_system_instructions()

try:
    preload_pdf_data()
    print("✅ Finished loading PDF.")
except Exception as e:
    print(f"⚠️ PDF load failed: {e}")

try:
    preload_website_data()
    print("✅ Finished loading website.")
except Exception as e:
    print(f"⚠️ Website load failed: {e}")

print("✅ HR Policy Assistant is ready to help employees!")    

# # ------------------------------------------------------------------
# # Start the app and preload sources
# # ------------------------------------------------------------------
# if __name__ == "__main__":
#     print("🚀 App is starting... loading sources.")
#     try:
#         preload_pdf_data()
#         print("✅ Finished loading PDF.")
#     except Exception as e:
#         print(f"⚠️ PDF load failed: {e}")

#     try:
#         preload_website_data()
#         print("✅ Finished loading website.")
#     except Exception as e:
#         print(f"⚠️ Website load failed: {e}")

#     app.run(debug=True, host="0.0.0.0", port=5000)
