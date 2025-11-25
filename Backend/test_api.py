"""
Simple test script to test the Portfolio Q&A API locally.
Run this after starting the Flask server with: python app.py
"""

import requests
import json

BASE_URL = "http://localhost:5000"

def test_home():
    """Test the home endpoint"""
    print("\n" + "="*50)
    print("Testing HOME endpoint...")
    print("="*50)
    response = requests.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

def test_health():
    """Test the health endpoint"""
    print("\n" + "="*50)
    print("Testing HEALTH endpoint...")
    print("="*50)
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response:\n{json.dumps(response.json(), indent=2)}")

def test_ask(question: str):
    """Test the ask endpoint with a question"""
    print("\n" + "="*50)
    print(f"Testing ASK endpoint with: '{question}'")
    print("="*50)
    
    payload = {
        "prompt": question,
        "model": "gpt-3.5-turbo"  # Optional, defaults to gpt-3.5-turbo
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/ask",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nResponse:\n{data['response']}\n")
            print(f"Sources found: {len(data.get('sources', []))}")
        else:
            print(f"Error: {response.text}")
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to the server.")
        print("Make sure the Flask app is running with: python app.py")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🧪 Portfolio Q&A API Test Script")
    print("Make sure the Flask server is running on http://localhost:5000")
    
    # Test home endpoint
    test_home()
    
    # Test health endpoint
    test_health()
    
    # Test ask endpoint with sample questions
    test_questions = [
        "Who is Manuj Rai?",
        "Tell me about Manuj's skills",
        "What projects has Manuj worked on?"
    ]
    
    for question in test_questions:
        test_ask(question)
        print("\n" + "-"*50 + "\n")
    
    print("✅ Testing complete!")
