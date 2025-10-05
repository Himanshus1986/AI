
"""
Simple Gradio Interface for Conversational Timesheet Chatbot API
Text-based input interface to consume the FastAPI backend
"""

import gradio as gr
import requests
import json
from datetime import datetime
from typing import Dict, Any, Optional

# API Configuration
TIMESHEET_API_URL = "http://localhost:8000"
DEFAULT_EMAIL = "demo.user@company.com"

class TimesheetChatAPI:
    """Simple API client for the timesheet chatbot"""

    def __init__(self, base_url: str = TIMESHEET_API_URL):
        self.base_url = base_url

    def chat(self, email: str, user_prompt: str) -> Dict[str, Any]:
        """Call the main chat endpoint"""
        try:
            response = requests.post(
                f"{self.base_url}/chat",
                json={
                    "email": email,
                    "user_prompt": user_prompt
                },
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "response": f"❌ API Error: {response.status_code}\n{response.text}",
                    "html_content": None,
                    "system_selected": None,
                    "session_id": None
                }

        except requests.exceptions.ConnectionError:
            return {
                "response": "❌ Cannot connect to the timesheet API.\n\nPlease ensure the FastAPI server is running at http://localhost:8000\n\nTo start the server, run: python main.py",
                "html_content": None,
                "system_selected": None,
                "session_id": None
            }
        except requests.exceptions.Timeout:
            return {
                "response": "⏱️ Request timed out. The server might be busy. Please try again.",
                "html_content": None,
                "system_selected": None,
                "session_id": None
            }
        except Exception as e:
            return {
                "response": f"❌ Error calling chat API: {str(e)}",
                "html_content": None,
                "system_selected": None,
                "session_id": None
            }

    def get_health(self) -> str:
        """Check API health status"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            if response.status_code == 200:
                health = response.json()
                status = health.get("status", "unknown")
                db_status = health.get("database", "unknown")
                ollama_status = health.get("ollama", "unknown")

                if status == "healthy":
                    return f"✅ API is healthy\n📊 Database: {db_status}\n🧠 Ollama: {ollama_status}"
                else:
                    return f"⚠️ API Status: {status}\n📊 Database: {db_status}\n🧠 Ollama: {ollama_status}"
            else:
                return f"❌ API Health Check Failed\nHTTP {response.status_code}: {response.text}"
        except Exception as e:
            return f"❌ Cannot reach API server\nError: {str(e)}\n\nMake sure the FastAPI server is running at {self.base_url}"

# Initialize API client
api_client = TimesheetChatAPI()

# Global conversation history
conversation_history = []

def process_chat_message(email: str, message: str, history):
    """Process chat message and return updated conversation"""

    # Validate inputs
    if not email or not email.strip():
        error_msg = "Please enter your email address"
        history.append([message, error_msg])
        return history, "", f"Current system: Not selected | Session: None"

    if not message or not message.strip():
        return history, "", f"Current system: Not selected | Session: None"

    # Call the API
    result = api_client.chat(email.strip(), message.strip())

    # Extract response
    bot_response = result.get("response", "No response received")
    html_content = result.get("html_content", "")
    system_selected = result.get("system_selected", "Not selected")
    session_id = result.get("session_id", "None")

    # Add HTML content to response if available
    if html_content:
        bot_response += f"\n\n{html_content}"

    # Update conversation history
    history.append([message, bot_response])

    # Create status message
    status = f"Current system: {system_selected} | Session: {session_id}"

    return history, "", status

def clear_conversation():
    """Clear the conversation history"""
    return [], "", "Current system: Not selected | Session: None"

def check_api_status():
    """Check if the API is running"""
    return api_client.get_health()

def load_example_prompts():
    """Return example prompts for users to try"""
    examples = [
        "I want to use Oracle system",
        "Add 8 hours for ORG-001 yesterday",
        "Show my timesheet for this week", 
        "What Oracle project codes are available?",
        "Fill 8 hours daily for project ORG-002 this week",
        "I worked 6 hours on Mars project MRS-001 last Friday",
        "Copy last week's timesheet to this week",
        "Switch to Mars system",
        "View my Mars entries from last week"
    ]
    return examples

# Create the Gradio interface
def create_chat_interface():

    # Custom CSS for better styling
    custom_css = """
    .gradio-container {
        max-width: 1200px !important;
        margin: 0 auto !important;
    }

    .main-header {
        text-align: center;
        padding: 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 20px;
    }

    .main-header h1 {
        margin: 0;
        font-size: 2.2em;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }

    .main-header p {
        margin: 10px 0 0 0;
        font-size: 1.1em;
        opacity: 0.9;
    }

    .status-box {
        background: #f0f8ff;
        border: 1px solid #b3d9ff;
        border-radius: 8px;
        padding: 12px;
        margin: 10px 0;
        font-family: monospace;
        font-size: 0.9em;
    }

    .examples-box {
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
    }

    .examples-box h4 {
        margin-top: 0;
        color: #495057;
    }

    .examples-box ul {
        margin: 10px 0;
        padding-left: 20px;
    }

    .examples-box li {
        margin: 5px 0;
        color: #6c757d;
        cursor: pointer;
    }

    .examples-box li:hover {
        color: #007bff;
        font-weight: bold;
    }

    .chatbot {
        height: 500px !important;
    }

    .api-status {
        font-family: monospace;
        white-space: pre-line;
        background: #f8f9fa;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #dee2e6;
    }
    """

    with gr.Blocks(
        css=custom_css,
        title="🎤 Timesheet Chatbot",
        theme=gr.themes.Soft()
    ) as demo:

        # Header
        gr.HTML("""
        <div class='main-header'>
            <h1>🎤 Conversational Timesheet Assistant</h1>
            <p>Chat naturally to manage your Oracle and Mars timesheets with AI</p>
        </div>
        """)

        # Main chat interface
        with gr.Row():
            with gr.Column(scale=3):
                # Chat interface
                chatbot = gr.Chatbot(
                    label="💬 Conversation",
                    height=500,
                    placeholder="Your conversation will appear here..."
                )

                with gr.Row():
                    message_input = gr.Textbox(
                        label="💭 Your Message",
                        placeholder="Type your timesheet request here... (e.g., 'Add 8 hours for ORG-001 yesterday')",
                        lines=2,
                        scale=4
                    )

                with gr.Row():
                    send_btn = gr.Button("📤 Send Message", variant="primary", scale=1)
                    clear_btn = gr.Button("🗑️ Clear Chat", variant="secondary", scale=1)

            with gr.Column(scale=1):
                # Email input
                email_input = gr.Textbox(
                    label="📧 Your Email",
                    value=DEFAULT_EMAIL,
                    placeholder="Enter your email address",
                    lines=1
                )

                # Status display
                status_display = gr.Textbox(
                    label="📊 Session Status", 
                    value="Current system: Not selected | Session: None",
                    interactive=False,
                    lines=2
                )

                # API health check
                api_status = gr.Textbox(
                    label="🔧 API Status",
                    value="Click 'Check API' to test connection",
                    interactive=False,
                    lines=4,
                    elem_classes=["api-status"]
                )

                check_api_btn = gr.Button("🔍 Check API", variant="secondary")

        # Examples section
        gr.HTML("""
        <div class='examples-box'>
            <h4>🗣️ Example Commands:</h4>
            <ul>
                <li><strong>System Selection:</strong> "I want to use Oracle system"</li>
                <li><strong>Add Entry:</strong> "Add 8 hours for ORG-001 yesterday"</li>
                <li><strong>View Data:</strong> "Show my timesheet for this week"</li>
                <li><strong>Project Info:</strong> "What Oracle project codes are available?"</li>
                <li><strong>Multi-day:</strong> "Fill 8 hours daily for ORG-002 this week"</li>
                <li><strong>Copy Week:</strong> "Copy last week's timesheet to this week"</li>
                <li><strong>Switch System:</strong> "Switch to Mars system"</li>
                <li><strong>Complex:</strong> "I worked 6 hours on MRS-001 Monday and 4 hours on CMN-002 Tuesday"</li>
            </ul>
        </div>
        """)

        # Instructions
        gr.HTML("""
        <div class='examples-box'>
            <h4>📚 How to Use:</h4>
            <ol>
                <li><strong>Set Email:</strong> Enter your email address (used for session management)</li>
                <li><strong>Check API:</strong> Click "Check API" to ensure the server is running</li>
                <li><strong>Start Chatting:</strong> Type natural language timesheet requests</li>
                <li><strong>View Responses:</strong> See AI responses with formatted timesheet tables</li>
                <li><strong>Continue Conversation:</strong> Context is maintained across messages</li>
            </ol>

            <h4>🔧 Setup:</h4>
            <p>Make sure your FastAPI server is running:</p>
            <code>python main.py</code>
            <p>Then access this interface at: <strong>http://localhost:7860</strong></p>
        </div>
        """)

        # Event handlers
        def handle_message_submit(email, message, history):
            """Handle message submission"""
            return process_chat_message(email, message, history)

        # Send button click
        send_btn.click(
            fn=handle_message_submit,
            inputs=[email_input, message_input, chatbot],
            outputs=[chatbot, message_input, status_display]
        )

        # Enter key press in message input
        message_input.submit(
            fn=handle_message_submit,
            inputs=[email_input, message_input, chatbot],
            outputs=[chatbot, message_input, status_display]
        )

        # Clear button
        clear_btn.click(
            fn=clear_conversation,
            outputs=[chatbot, message_input, status_display]
        )

        # API health check
        check_api_btn.click(
            fn=check_api_status,
            outputs=[api_status]
        )

        # Auto-check API status on load
        demo.load(
            fn=check_api_status,
            outputs=[api_status]
        )

    return demo

if __name__ == "__main__":
    print("🚀 Starting Simple Timesheet Chat Interface...")
    print(f"🌐 API URL: {TIMESHEET_API_URL}")
    print("📧 Default Email:", DEFAULT_EMAIL)
    print("💡 Make sure your FastAPI server is running: python main.py")
    print("🔗 Interface will be available at: http://localhost:7860")

    demo = create_chat_interface()
    demo.launch(
        share=False,
        server_name="0.0.0.0", 
        server_port=7860,
        debug=True,
        show_error=True
    )
