from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA

# Load environment
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Flask setup
app = Flask(__name__)
CORS(app)

# Load PDF content
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

# Load system instructions
def load_system_instruction():
    try:
        with open("instructions.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except:
        return "You are a helpful assistant. Answer based only on the provided context."

# Chunk, embed, and store
def build_vector_store(text):
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text(text)
    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.from_texts(chunks, embedding=embeddings)
    return vectorstore

# Initialization
PDF_PATH = "Manuj Rai.pdf"
SYSTEM_INSTRUCTION = load_system_instruction()
PDF_TEXT = load_pdf_text(PDF_PATH)
VECTOR_STORE = build_vector_store(PDF_TEXT)

# LangChain QA Chain
retriever = VECTOR_STORE.as_retriever(search_type="similarity", k=3)
qa_chain = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(temperature=0, model_name="gpt-3.5-turbo"),
    retriever=retriever,
    chain_type_kwargs={"prompt": None},  # We rely on LangChain's default prompt
    return_source_documents=True
)

# Routes
@app.route("/")
def home():
    return "✅ PDF RAG Q&A API is running"

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.get_json()
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        result = qa_chain(prompt)
        answer = result["result"]
        source_chunks = [doc.page_content[:200] for doc in result["source_documents"]]

        return jsonify({
            "response": answer,
            "sources": source_chunks
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"error": str(e)}), 500

# Start app
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
