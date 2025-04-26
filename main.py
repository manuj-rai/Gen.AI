import os
import openai
import tiktoken
from dotenv import load_dotenv, find_dotenv
 
_ = load_dotenv(find_dotenv())  
 
# Load environment variables
_ = load_dotenv(find_dotenv())
openai.api_key = os.getenv('OPENAI_API_KEY')
 
def get_completion(prompt, model="gpt-4o"):
    with open("instructions.txt", "r") as f:
        system_instruction = f.read().strip()
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": prompt}
    ]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=1.0,      # More creativity
        max_tokens=50,        # Limit length
        top_p=1.0             # Use nucleus sampling
    )
    return response.choices[0].message.content  # ← Correct

while True:
    user_prompt = input("\nEnter your question (or type 'exit' to quit): ")
    if user_prompt.lower() == "exit":
        break
    response = get_completion(user_prompt)
    print("AI Response:", response)