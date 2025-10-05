
"""
Advanced Gradio Voice Assistant for Conversational Timesheet Chatbot
Features: Speech-to-text, Text-to-speech, Beautiful UI, API Integration
"""

import gradio as gr
import requests
import json
import time
from datetime import datetime
import speech_recognition as sr
import pyttsx3
import threading
import numpy as np
import io
import wave
import tempfile
import os
from typing import List, Dict, Any, Optional
import base64

# Configuration
TIMESHEET_API_URL = "http://localhost:8000"
DEFAULT_EMAIL = "demo.user@company.com"

class VoiceAssistant:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.tts_engine = pyttsx3.init()
        self.setup_tts()
        self.conversation_history = []

    def setup_tts(self):
        """Configure text-to-speech engine"""
        try:
            voices = self.tts_engine.getProperty('voices')
            if voices:
                # Try to use a female voice if available
                for voice in voices:
                    if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                        self.tts_engine.setProperty('voice', voice.id)
                        break

            self.tts_engine.setProperty('rate', 180)  # Speaking rate
            self.tts_engine.setProperty('volume', 0.8)  # Volume level
        except Exception as e:
            print(f"TTS setup warning: {e}")

    def speech_to_text(self, audio_file) -> str:
        """Convert speech to text using speech_recognition"""
        try:
            if audio_file is None:
                return ""

            # Handle different audio input formats
            if isinstance(audio_file, str):
                # File path
                with sr.AudioFile(audio_file) as source:
                    audio = self.recognizer.record(source)
            else:
                # Numpy array from Gradio
                sample_rate, audio_data = audio_file

                # Convert to mono if stereo
                if len(audio_data.shape) > 1:
                    audio_data = np.mean(audio_data, axis=1)

                # Normalize audio
                audio_data = audio_data.astype(np.float32)
                if np.max(np.abs(audio_data)) > 0:
                    audio_data = audio_data / np.max(np.abs(audio_data))

                # Convert to 16-bit PCM
                audio_data = (audio_data * 32767).astype(np.int16)

                # Create temporary WAV file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                    with wave.open(tmp_file.name, 'wb') as wav_file:
                        wav_file.setnchannels(1)  # Mono
                        wav_file.setsampwidth(2)  # 16-bit
                        wav_file.setframerate(sample_rate)
                        wav_file.writeframes(audio_data.tobytes())

                    with sr.AudioFile(tmp_file.name) as source:
                        audio = self.recognizer.record(source)

                    # Clean up temporary file
                    os.unlink(tmp_file.name)

            # Recognize speech
            text = self.recognizer.recognize_google(audio, language='en-US')
            return text

        except sr.UnknownValueError:
            return "Could not understand audio. Please try speaking more clearly."
        except sr.RequestError as e:
            return f"Speech recognition error: {e}"
        except Exception as e:
            return f"Error processing audio: {e}"

    def text_to_speech_file(self, text: str) -> str:
        """Convert text to speech and return audio file path"""
        try:
            # Create temporary audio file
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_file.close()

            # Generate speech
            self.tts_engine.save_to_file(text, temp_file.name)
            self.tts_engine.runAndWait()

            return temp_file.name

        except Exception as e:
            print(f"TTS error: {e}")
            return None

    def call_timesheet_api(self, email: str, user_prompt: str) -> Dict[str, Any]:
        """Call the FastAPI timesheet chatbot"""
        try:
            response = requests.post(
                f"{TIMESHEET_API_URL}/chat",
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
                    "response": f"API Error: {response.status_code} - {response.text}",
                    "html_content": None,
                    "system_selected": None
                }

        except requests.exceptions.ConnectionError:
            return {
                "response": "❌ Cannot connect to timesheet API. Please ensure the FastAPI server is running at http://localhost:8000",
                "html_content": None,
                "system_selected": None
            }
        except Exception as e:
            return {
                "response": f"Error calling API: {str(e)}",
                "html_content": None,
                "system_selected": None
            }

# Initialize voice assistant
voice_assistant = VoiceAssistant()

def process_voice_input(audio_input, email_input):
    """Process voice input and get chatbot response"""
    if audio_input is None:
        return "", "", "", None, ""

    # Convert speech to text
    recognized_text = voice_assistant.speech_to_text(audio_input)

    if not recognized_text or "error" in recognized_text.lower():
        return recognized_text, "", "", None, "❌ Speech recognition failed"

    # Call timesheet API
    api_response = voice_assistant.call_timesheet_api(email_input, recognized_text)

    # Generate audio response
    audio_file = None
    if api_response["response"]:
        audio_file = voice_assistant.text_to_speech_file(api_response["response"])

    # Update conversation history
    timestamp = datetime.now().strftime("%H:%M:%S")
    voice_assistant.conversation_history.append({
        "timestamp": timestamp,
        "user": recognized_text,
        "assistant": api_response["response"],
        "system": api_response.get("system_selected", "Not selected")
    })

    # Format conversation for display
    conversation_html = format_conversation_history()

    return (
        recognized_text,  # Recognized text
        api_response["response"],  # Bot response
        api_response.get("html_content", ""),  # HTML table
        audio_file,  # Audio response
        conversation_html  # Conversation history
    )

def format_conversation_history() -> str:
    """Format conversation history as HTML"""
    if not voice_assistant.conversation_history:
        return "<div class='no-conversation'>No conversation yet. Start by saying something!</div>"

    html = "<div class='conversation-history'>"

    for entry in voice_assistant.conversation_history[-10:]:  # Show last 10 exchanges
        html += f"""
        <div class='conversation-entry'>
            <div class='timestamp'>{entry['timestamp']}</div>
            <div class='user-message'>
                <div class='message-label'>🎤 You said:</div>
                <div class='message-content'>{entry['user']}</div>
            </div>
            <div class='assistant-message'>
                <div class='message-label'>🤖 Assistant:</div>
                <div class='message-content'>{entry['assistant']}</div>
            </div>
            <div class='system-info'>System: {entry['system']}</div>
        </div>
        """

    html += "</div>"
    return html

def clear_conversation():
    """Clear conversation history"""
    voice_assistant.conversation_history = []
    return "", "", "", None, "<div class='no-conversation'>Conversation cleared!</div>"

def test_api_connection():
    """Test API connection"""
    try:
        response = requests.get(f"{TIMESHEET_API_URL}/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            return f"✅ API Connected - Status: {health_data.get('status', 'unknown')}"
        else:
            return f"⚠️ API Response Error: {response.status_code}"
    except Exception as e:
        return f"❌ API Connection Failed: {str(e)}"

# Custom CSS for beautiful styling
custom_css = """
/* Main container styling */
.gradio-container {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

/* Header styling */
.main-header {
    text-align: center;
    color: white;
    padding: 20px;
    margin-bottom: 20px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 15px;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
}

.main-header h1 {
    font-size: 2.5em;
    margin-bottom: 10px;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
}

.main-header p {
    font-size: 1.2em;
    opacity: 0.9;
}

/* Component containers */
.component-container {
    background: rgba(255, 255, 255, 0.95);
    border-radius: 15px;
    padding: 20px;
    margin: 10px 0;
    box-shadow: 0 8px 32px rgba(0,0,0,0.1);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
}

/* Voice input section */
.voice-section {
    text-align: center;
    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
    color: white;
    border-radius: 20px;
    padding: 30px;
    margin: 20px 0;
}

/* Text displays */
.recognized-text {
    background: #e8f5e9;
    border: 2px solid #4caf50;
    border-radius: 10px;
    padding: 15px;
    font-size: 1.1em;
    margin: 10px 0;
}

.bot-response {
    background: #e3f2fd;
    border: 2px solid #2196f3;
    border-radius: 10px;
    padding: 15px;
    font-size: 1.1em;
    margin: 10px 0;
}

/* Conversation history */
.conversation-history {
    max-height: 400px;
    overflow-y: auto;
    padding: 15px;
    background: #f8f9fa;
    border-radius: 10px;
    border: 1px solid #dee2e6;
}

.conversation-entry {
    margin-bottom: 20px;
    padding: 15px;
    background: white;
    border-radius: 10px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.timestamp {
    font-size: 0.8em;
    color: #666;
    text-align: right;
    margin-bottom: 5px;
}

.user-message, .assistant-message {
    margin: 10px 0;
}

.message-label {
    font-weight: bold;
    font-size: 0.9em;
    margin-bottom: 5px;
}

.user-message .message-label {
    color: #4caf50;
}

.assistant-message .message-label {
    color: #2196f3;
}

.message-content {
    background: #f8f9fa;
    padding: 10px;
    border-radius: 8px;
    border-left: 4px solid #ddd;
}

.user-message .message-content {
    border-left-color: #4caf50;
}

.assistant-message .message-content {
    border-left-color: #2196f3;
}

.system-info {
    font-size: 0.8em;
    color: #666;
    text-align: right;
    font-style: italic;
}

.no-conversation {
    text-align: center;
    color: #666;
    font-style: italic;
    padding: 30px;
}

/* Status indicators */
.status-indicator {
    padding: 10px;
    border-radius: 8px;
    margin: 10px 0;
    font-weight: bold;
}

.status-success {
    background: #d4edda;
    color: #155724;
    border: 1px solid #c3e6cb;
}

.status-error {
    background: #f8d7da;
    color: #721c24;
    border: 1px solid #f5c6cb;
}

/* Button styling */
.action-button {
    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
    border: none;
    color: white;
    padding: 12px 30px;
    border-radius: 25px;
    font-size: 1.1em;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}

.action-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.3);
}

/* Timesheet table styling */
.timesheet-container {
    background: white;
    border-radius: 15px;
    padding: 20px;
    margin: 15px 0;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
}

.timesheet-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 10px;
}

.timesheet-table th {
    background: linear-gradient(45deg, #667eea, #764ba2);
    color: white;
    padding: 12px;
    font-weight: bold;
    text-align: left;
    border: none;
}

.timesheet-table td {
    padding: 10px 12px;
    border-bottom: 1px solid #eee;
}

.timesheet-table tr:hover {
    background-color: #f8f9fa;
}

/* Audio controls */
audio {
    width: 100%;
    margin: 10px 0;
}

/* Animations */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}

.component-container {
    animation: fadeIn 0.6s ease-out;
}

/* Responsive design */
@media (max-width: 768px) {
    .main-header h1 {
        font-size: 2em;
    }

    .main-header p {
        font-size: 1em;
    }

    .component-container {
        padding: 15px;
        margin: 5px 0;
    }
}
"""

# JavaScript for enhanced functionality
custom_js = """
function initializeVoiceAssistant() {
    console.log('Voice Assistant initialized');

    // Add visual feedback for voice recording
    const audioInputs = document.querySelectorAll('audio');
    audioInputs.forEach(audio => {
        audio.addEventListener('play', function() {
            this.style.border = '3px solid #4ECDC4';
            this.style.boxShadow = '0 0 20px rgba(78, 205, 196, 0.5)';
        });

        audio.addEventListener('pause', function() {
            this.style.border = '1px solid #ddd';
            this.style.boxShadow = 'none';
        });
    });

    // Auto-scroll conversation history
    const conversationHistory = document.querySelector('.conversation-history');
    if (conversationHistory) {
        conversationHistory.scrollTop = conversationHistory.scrollHeight;
    }

    return 'Voice Assistant Ready!';
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeVoiceAssistant);
"""

# Create the main Gradio interface
def create_voice_assistant_interface():
    with gr.Blocks(
        css=custom_css,
        js=custom_js,
        theme=gr.themes.Soft(),
        title="🎤 Voice Timesheet Assistant"
    ) as demo:

        # Header
        gr.HTML("""
        <div class='main-header'>
            <h1>🎤 Voice Timesheet Assistant</h1>
            <p>Speak naturally to manage your Oracle and Mars timesheets with AI-powered conversation</p>
        </div>
        """)

        # Main layout
        with gr.Row():
            # Left column - Voice input and controls
            with gr.Column(scale=1):
                gr.HTML("<div class='component-container'>")
                gr.Markdown("### 🎙️ Voice Input")

                email_input = gr.Textbox(
                    label="📧 Your Email",
                    value=DEFAULT_EMAIL,
                    placeholder="Enter your email address"
                )

                audio_input = gr.Audio(
                    label="🎤 Record your voice",
                    sources=["microphone"],
                    type="numpy",
                    format="wav"
                )

                with gr.Row():
                    clear_btn = gr.Button("🗑️ Clear History", variant="secondary")
                    test_btn = gr.Button("🔌 Test API", variant="secondary")

                api_status = gr.Textbox(
                    label="📡 API Status",
                    interactive=False,
                    value="Click 'Test API' to check connection"
                )
                gr.HTML("</div>")

            # Right column - Responses and conversation
            with gr.Column(scale=2):
                gr.HTML("<div class='component-container'>")
                gr.Markdown("### 💬 Conversation & Responses")

                recognized_text = gr.Textbox(
                    label="🎯 What you said",
                    interactive=False,
                    lines=2
                )

                bot_response = gr.Textbox(
                    label="🤖 Assistant response",
                    interactive=False,
                    lines=3
                )

                audio_output = gr.Audio(
                    label="🔊 Listen to response",
                    interactive=False
                )

                gr.HTML("</div>")

        # Full width sections
        with gr.Row():
            with gr.Column():
                gr.HTML("<div class='component-container'>")
                gr.Markdown("### 📊 Timesheet Data")
                html_output = gr.HTML(
                    label="Timesheet tables and data will appear here"
                )
                gr.HTML("</div>")

        with gr.Row():
            with gr.Column():
                gr.HTML("<div class='component-container'>")
                gr.Markdown("### 🗣️ Conversation History")
                conversation_history = gr.HTML(
                    value="<div class='no-conversation'>No conversation yet. Start by recording your voice!</div>"
                )
                gr.HTML("</div>")

        # Instructions
        gr.HTML("""
        <div class='component-container'>
            <h3>📝 How to Use</h3>
            <ol>
                <li><strong>🎤 Record:</strong> Click the microphone and speak your timesheet request</li>
                <li><strong>🤖 Listen:</strong> The AI will process your speech and respond with both text and voice</li>
                <li><strong>📊 View:</strong> See timesheet tables and data in the response area</li>
                <li><strong>💬 Continue:</strong> Have natural conversations about your timesheet</li>
            </ol>

            <h4>🗣️ Example Voice Commands:</h4>
            <ul>
                <li>"I want to use Oracle system"</li>
                <li>"Add 8 hours for ORG-001 yesterday"</li>
                <li>"Show my timesheet for this week"</li>
                <li>"What project codes are available?"</li>
                <li>"Fill 8 hours daily for Mars project MRS-001 this week"</li>
                <li>"Copy last week's timesheet to this week"</li>
            </ul>
        </div>
        """)

        # Event handlers
        audio_input.change(
            fn=process_voice_input,
            inputs=[audio_input, email_input],
            outputs=[recognized_text, bot_response, html_output, audio_output, conversation_history]
        )

        clear_btn.click(
            fn=clear_conversation,
            outputs=[recognized_text, bot_response, html_output, audio_output, conversation_history]
        )

        test_btn.click(
            fn=test_api_connection,
            outputs=api_status
        )

    return demo

if __name__ == "__main__":
    # Check if required packages are installed
    required_packages = {
        'speech_recognition': 'SpeechRecognition',
        'pyttsx3': 'pyttsx3',
        'requests': 'requests',
        'numpy': 'numpy'
    }

    missing_packages = []
    for package, install_name in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(install_name)

    if missing_packages:
        print("❌ Missing required packages. Please install:")
        print(f"pip install {' '.join(missing_packages)}")
        exit(1)

    # Launch the interface
    print("🚀 Starting Voice Timesheet Assistant...")
    print("🔊 Make sure your microphone is working")
    print("🎯 Ensure the FastAPI server is running at http://localhost:8000")

    demo = create_voice_assistant_interface()
    demo.launch(
        share=False,
        server_name="0.0.0.0",
        server_port=7860,
        debug=True,
        show_error=True
    )
