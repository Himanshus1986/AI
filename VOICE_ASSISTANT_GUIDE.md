
# 🎤 Voice Timesheet Assistant - User Guide

## Overview
The Voice Timesheet Assistant provides a natural speech interface to the conversational timesheet chatbot, allowing you to speak your requests and receive both text and audio responses.

## Features ✨

### 🎙️ Voice Input
- **Speech-to-Text**: Converts your speech to text using Google Speech Recognition
- **Natural Language**: Speak naturally - "Add 8 hours for Oracle project yesterday"
- **Multiple Languages**: Supports various accents and speaking patterns

### 🤖 AI Responses  
- **Text Responses**: Get detailed written responses from the timesheet AI
- **Voice Responses**: Hear responses spoken back using text-to-speech
- **Context Awareness**: Maintains conversation context across interactions

### 📊 Visual Interface
- **Beautiful UI**: Modern, responsive design with animations
- **HTML Tables**: Timesheet data displayed in formatted tables
- **Conversation History**: See your complete conversation flow
- **Real-time Status**: API connection status and system information

### 🔄 Complete Integration
- **FastAPI Backend**: Full integration with the timesheet chatbot API
- **Session Management**: Maintains user context and preferences
- **Error Handling**: Graceful handling of speech recognition and API errors

## Installation & Setup

### Prerequisites
```bash
# Python 3.11+
python --version

# FastAPI timesheet server running
curl http://localhost:8000/health

# System audio dependencies (Linux)
sudo apt-get install portaudio19-dev python3-pyaudio espeak

# System audio dependencies (macOS)  
brew install portaudio espeak
```

### Quick Start
```bash
# Install dependencies
pip install -r voice_assistant_requirements.txt

# Run the voice assistant
python gradio_voice_assistant.py

# Open browser to http://localhost:7860
# Allow microphone access when prompted
```

### Docker Setup
```bash
# Start all services including voice assistant
docker-compose -f docker-compose-voice.yml up -d

# Access voice assistant at http://localhost:7860
# Access API directly at http://localhost:8000
```

## Usage Instructions

### 1. 🎤 Recording Voice Input
1. Click the microphone button in the "Record your voice" section
2. Speak clearly and naturally
3. The system will automatically process your speech when you stop talking
4. Your speech will be converted to text and displayed

### 2. 🗣️ Example Voice Commands

**System Selection:**
- "I want to use Oracle system"
- "Switch to Mars timesheet"
- "Use the Oracle system for my entries"

**Adding Timesheet Entries:**
- "Add 8 hours for ORG-001 yesterday"
- "I worked 6 hours on Mars project MRS-002 last Friday"
- "Fill 8 hours daily for project ORG-003 this week"
- "Add 4 hours for documentation on CMN-001 today"

**Viewing Timesheets:**
- "Show my Oracle timesheet for this week"
- "Display my Mars entries from last week"  
- "What did I work on yesterday?"

**Project Information:**
- "What Oracle project codes are available?"
- "Show me Mars project codes"
- "List all available projects"

**Advanced Operations:**
- "Copy last week's timesheet to this week"
- "Modify my entry for ORG-001 yesterday to 6 hours"
- "Change my Monday entry to use project ORG-002"

### 3. 📊 Understanding Responses

**Text Response:**
- Appears in the "Assistant response" box
- Contains conversational AI response to your request
- Provides feedback on actions taken

**Voice Response:**
- Plays automatically after processing
- Can be replayed by clicking the audio player
- Uses text-to-speech to read the response

**HTML Tables:**
- Timesheet data appears in the "Timesheet Data" section
- Formatted tables with dates, projects, hours, status
- Total hours calculated automatically

**Conversation History:**
- Shows your complete conversation flow
- Timestamped exchanges between you and the assistant
- Scrollable history of recent interactions

## Advanced Features

### 🔧 Configuration Options

**Email Address:**
- Set your email in the input field
- Used for session management and timesheet ownership
- Defaults to demo.user@company.com

**API Connection:**
- Click "Test API" to verify connection to FastAPI server
- Status indicator shows connection health
- Automatically handles connection errors

**Clear History:**
- "Clear History" button resets conversation
- Useful for starting fresh conversations
- Doesn't affect saved timesheet data

### 🎯 Speech Recognition Tips

**For Best Results:**
- Speak clearly and at normal pace
- Minimize background noise
- Use specific project codes (ORG-001, MRS-002, etc.)
- Include specific dates ("yesterday", "Monday", "this week")

**If Recognition Fails:**
- Try speaking more slowly
- Check microphone permissions in browser
- Ensure microphone is not muted
- Try refreshing the page

### 🔊 Audio System Setup

**Browser Requirements:**
- Modern browser (Chrome, Firefox, Safari, Edge)
- HTTPS required for microphone access (or localhost)
- Microphone permissions granted

**System Audio:**
- Working microphone for input
- Speakers or headphones for TTS output
- Proper audio drivers installed

## Troubleshooting

### Common Issues

**🎤 Microphone Not Working:**
```
Issue: Browser doesn't detect microphone
Solution: 
1. Check browser permissions (click lock icon in address bar)
2. Ensure microphone isn't used by other applications
3. Try different browser
4. For production: use HTTPS (required for microphone access)
```

**🔊 No Audio Output:**
```  
Issue: Text-to-speech not working
Solution:
1. Check system volume
2. Verify speakers/headphones connected
3. Try: pip install gtts pygame (alternative TTS)
4. Check browser audio permissions
```

**🌐 API Connection Failed:**
```
Issue: Cannot connect to timesheet API
Solution:
1. Ensure FastAPI server running: python main.py
2. Check API URL: http://localhost:8000
3. Verify firewall settings
4. Test API health: curl http://localhost:8000/health
```

**🗣️ Speech Recognition Errors:**
```
Issue: "Could not understand audio"
Solution:
1. Speak more clearly and slowly
2. Reduce background noise
3. Check microphone quality
4. Try shorter phrases
5. Alternative: pip install openai-whisper (better accuracy)
```

### Performance Optimization

**For Better Accuracy:**
```bash
# Install Whisper for improved speech recognition
pip install openai-whisper torch

# Install Google TTS for better voice output  
pip install gtts pygame
```

**For Production Deployment:**
```bash
# Use HTTPS for microphone access
# Configure proper SSL certificates
# Use production-grade TTS services
# Implement rate limiting and authentication
```

## Development & Customization

### Extending Functionality

**Adding New Voice Commands:**
1. Modify the `process_voice_input` function
2. Add intent recognition patterns
3. Implement corresponding API calls
4. Update conversation history formatting

**Custom TTS Voices:**
1. Replace pyttsx3 with advanced TTS services
2. Configure voice parameters (speed, pitch, accent)
3. Add emotion and personality to responses

**UI Customization:**
1. Modify the `custom_css` variable
2. Add new themes and color schemes
3. Implement responsive design improvements
4. Add animations and visual effects

### Integration Options

**With External Services:**
- Google Cloud Speech-to-Text API
- Azure Cognitive Services
- AWS Transcribe and Polly
- OpenAI Whisper API

**Mobile App Integration:**
- React Native wrapper
- Flutter implementation  
- Progressive Web App (PWA)
- Native mobile SDK

## Security Considerations

### Privacy Protection
- Audio processing happens locally by default
- No audio data sent to external services (unless configured)
- Session data encrypted in transit
- User consent required for microphone access

### Production Security
- Implement HTTPS/TLS encryption
- Add user authentication and authorization
- Rate limiting for API calls
- Input validation and sanitization
- Regular security audits and updates

---

**🎉 Enjoy using your Voice Timesheet Assistant!**

For support and updates, check the project repository or contact the development team.
