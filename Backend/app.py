from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import openai
import PyPDF2
from dotenv import load_dotenv, find_dotenv

# Load environment variables
_ = load_dotenv(find_dotenv())
openai.api_key = os.getenv('OPENAI_API_KEY')

app = Flask(__name__)
CORS(app)

# Load PDF content
def load_pdf_text(pdf_path="Manuj Rai.pdf"):
    try:
        full_path = os.path.abspath(pdf_path)
        print(f"📄 Loading PDF from: {full_path}")
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
        if not text.strip():
            print("⚠️ PDF loaded but no extractable text found.")
        return text.strip()
    except Exception as e:
        print(f"❌ Failed to load PDF: {e}")
        return ""

pdf_context = load_pdf_text()

# Load system instruction
def load_system_instruction():
    try:
        with open("instructions.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except:
        return "You are a helpful assistant."

system_instruction = load_system_instruction()

@app.route('/ask', methods=['POST'])
def ask():
    data = request.get_json()
    prompt = data.get("prompt", "")
    model = data.get("model", "gpt-4o")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": f"Based on the following document:\n{pdf_context}\n\nAnswer this: {prompt}"}
    ]

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=1.0,
            max_tokens=150
        )
        content = response['choices'][0]['message']['content']
        tokens_used = response['usage']['total_tokens']
        return jsonify({"response": content.strip(), "tokens": tokens_used})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
