import os
import openai
import tiktoken
from dotenv import load_dotenv, find_dotenv
from colorama import Fore, Style, init
import sys
import PyPDF2

# Initialize colorama for colored terminal output
init(autoreset=True)

# Load environment variables
_ = load_dotenv(find_dotenv())
openai.api_key = os.getenv('OPENAI_API_KEY')

# Choose model from command line or fallback
model = sys.argv[1] if len(sys.argv) > 1 else "gpt-4o"

# Load system instructions
def load_system_instruction():
    try:
        with open("instructions.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are a helpful assistant."

system_instruction = load_system_instruction()

# Load PDF content
def load_pdf_text(pdf_path="Manuj Rai.pdf"):
    try:
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
            return text.strip()
    except Exception as e:
        return f"❌ Failed to load PDF: {str(e)}"

pdf_context = load_pdf_text()

# Function to get AI response
def get_completion(prompt, model="gpt-4o"):
    try:
        context = pdf_context
        messages = [
            {"role": "system", "content": system_instruction},
            # {"role": "user", "content": prompt}
            {"role": "user", "content": f"Based on the following document:\n\n{context}\n\nAnswer this: {prompt}"}

        ]
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=1.0,
            max_tokens=150,
            top_p=1.0
        )
        content = response['choices'][0]['message']['content']
        tokens_used = response['usage']['total_tokens']
        return content.strip(), tokens_used
    except Exception as e:
        return f"❌ Error: {str(e)}", 0

# Logging function
def log_session(prompt, response, tokens_used):
    with open("session_log.txt", "a", encoding="utf-8") as log:
        log.write(f"User: {prompt}\nAI: {response}\nTokens Used: {tokens_used}\n{'='*50}\n")

# Interactive loop
print(Fore.YELLOW + f"Model: {model} | Type 'exit' to quit | Type 'reload system' to reload instructions\n")

while True:
    user_prompt = input(Fore.CYAN + "\nYour Question: " + Style.RESET_ALL).strip()

    if user_prompt.lower() == "exit":
        print(Fore.YELLOW + "Session Ended.")
        break
    elif user_prompt.lower() == "reload system":
        system_instruction = load_system_instruction()
        print(Fore.GREEN + "System prompt reloaded.")
        continue

    response, tokens_used = get_completion(user_prompt, model)
    print(Fore.GREEN + "\nAI Response:\n" + Style.RESET_ALL + response)
    print(Fore.MAGENTA + f"\n[Tokens Used: {tokens_used}]")

    log_session(user_prompt, response, tokens_used)
