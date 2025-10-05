
"""
Test script for Conversational Timesheet Chatbot API
Run this script to test the API functionality
"""
import requests
import json
import time
from datetime import datetime

# API Configuration
API_BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test.user@company.com"

def test_api_endpoint(endpoint, method="GET", data=None):
    """Test an API endpoint"""
    url = f"{API_BASE_URL}{endpoint}"

    try:
        if method == "POST":
            response = requests.post(url, json=data, headers={"Content-Type": "application/json"})
        else:
            response = requests.get(url)

        print(f"\n{method} {endpoint}")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            return result
        else:
            print(f"Error: {response.text}")
            return None

    except Exception as e:
        print(f"Request failed: {e}")
        return None

def test_chat_conversation():
    """Test a complete conversation flow"""
    print("\n" + "="*50)
    print("TESTING CONVERSATIONAL TIMESHEET CHATBOT")
    print("="*50)

    # Test health check
    print("\n1. Testing Health Check...")
    health = test_api_endpoint("/health")

    if not health or health.get("status") != "healthy":
        print("❌ API is not healthy. Please check the setup.")
        return

    print("✅ API is healthy!")

    # Test conversation flow
    conversation_tests = [
        {
            "step": "2. System Selection",
            "prompt": "I want to use Oracle system for my timesheet"
        },
        {
            "step": "3. Get Project Codes", 
            "prompt": "What Oracle projects are available?"
        },
        {
            "step": "4. Fill Single Entry",
            "prompt": "Add 8 hours for ORG-001 yesterday with description work on database maintenance"
        },
        {
            "step": "5. Fill Multiple Days",
            "prompt": "Fill 8 hours daily for ORG-002 from Monday to Wednesday this week"
        },
        {
            "step": "6. View Timesheet",
            "prompt": "Show me my Oracle timesheet entries for this week"
        },
        {
            "step": "7. Complex Request",
            "prompt": "I worked 6 hours on ORG-003 last Friday and 4 hours on CMN-001 documentation"
        },
        {
            "step": "8. Switch System",
            "prompt": "Switch to Mars system"
        },
        {
            "step": "9. Mars Project Codes",
            "prompt": "Show available Mars project codes"
        },
        {
            "step": "10. Mars Timesheet Entry",
            "prompt": "Add 7 hours for MRS-001 tomorrow"
        }
    ]

    for test in conversation_tests:
        print(f"\n{test['step']}...")
        print(f"User: {test['prompt']}")

        chat_data = {
            "email": TEST_EMAIL,
            "user_prompt": test['prompt']
        }

        result = test_api_endpoint("/chat", method="POST", data=chat_data)

        if result:
            print(f"Bot: {result.get('response', 'No response')}")
            if result.get('html_content'):
                print("📊 HTML table generated (content truncated)")
            print(f"System: {result.get('system_selected', 'Not selected')}")

        time.sleep(1)  # Brief pause between requests

    # Test direct API endpoints
    print("\n" + "="*30)
    print("TESTING DIRECT API ENDPOINTS")
    print("="*30)

    print("\n11. Testing Project Codes Endpoint...")
    test_api_endpoint("/projects/Oracle")

    print("\n12. Testing Timesheet Endpoint...")
    test_api_endpoint(f"/timesheet/{TEST_EMAIL}/Oracle")

    print("\n" + "="*30)
    print("TESTING COMPLETED!")
    print("="*30)
    print("\n✅ If all tests passed, your API is working correctly!")
    print("🔗 Visit http://localhost:8000/docs for interactive API documentation")

if __name__ == "__main__":
    print("Conversational Timesheet Chatbot API Test Suite")
    print(f"Testing API at: {API_BASE_URL}")
    print(f"Test User: {TEST_EMAIL}")

    # Wait a moment for user to confirm
    input("\nPress Enter to start testing (make sure the API is running)...")

    test_chat_conversation()
