from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
import google.generativeai as genai
import json
from datetime import datetime
import os
import requests
import time
import uuid
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('SECRET_KEY', 'fallback_dev_key_'+str(uuid.uuid4()))

# API Configuration
api_key = os.getenv("GEMINI_API_KEY", "AIzaSyCLnI_Tl1zS3nRcfBWsyBhxiJvu3x9dOLw")
mistral_api_key = os.getenv("MISTRAL_API_KEY", "J2hdJ9IT34rK8P0t6SnJQkLfpCUTA9vy")
genai.configure(api_key=api_key)

# Database Setup
USER_DATA_FILE = "user_data.json"

PROMPT_TEMPLATES = {
    "general_health": (
        "You are a menstrual health assistant. Provide a clear, factual, and educational response to the following question about menstrual health: {user_input}. "
        "Ensure the response is appropriate for all audiences and avoids harmful or sensitive language."
    ),
    "nutrition": (
        "You are a nutritionist specializing in menstrual health. Based on the user's current cycle phase ({cycle_phase}) and cravings ({cravings}), "
        "provide specific dietary recommendations that align with their cravings and cycle phase. For example, if they crave spicy food, suggest spicy and healthy options. "
        "Answer the following question: {user_input}"
    ),
    "child_friendly": (
        "You are a friendly menstrual health assistant, explaining menstrual health topics in a clear, simple, and age-appropriate way. "
        "Answer the question: '{user_input}' directly, without discussing unrelated topics. "
        "Use comforting and inclusive language, keep the response brief and factual, and avoid overwhelming details. "
        "Provide reassurance if the question involves symptoms like cramps, mood swings, or discharge, but do not mention additional symptoms unless asked."
    ),
    "exercise": (
        "You are a fitness coach specializing in menstrual health. Based on the user's cycle phase ({cycle_phase}) and energy levels, "
        "recommend specific exercises suited to that phase. Provide clear workout suggestions with phase-specific titles such as '**Exercises for the {cycle_phase} Phase**' "
        "and include options for different energy levels. Keep the tone encouraging and supportive while focusing on menstrual health benefits. "
        "Answer the following question: '{user_input}'"
    ),
    "cravings_alternatives": (
        "You are a nutritionist focused on menstrual health. Suggest specific, healthy, and satisfying alternatives tailored to the user's cravings ({cravings}) "
        "and current cycle phase ({cycle_phase}). Provide clear options under a phase-specific title like '**Healthy Alternatives for {cravings} Cravings in the {cycle_phase} Phase**' "
        "and offer a variety of sweet, salty, or spicy alternatives as relevant. Keep the tone encouraging and practical. "
        "Answer the following question: '{user_input}'"
    ),
    "meal_planner": (
        "You are a nutritionist specializing in menstrual health. Create a detailed daily meal plan with breakfast, lunch, and dinner, considering the user's cycle phase ({cycle_phase}), "
        "cravings ({cravings}), dietary specifications ({dietary_specs}), preferred cuisine ({cuisine}), and allergies ({allergies}). "
        "Ensure the meals are nutritious, satisfying, and help manage common menstrual symptoms. Provide the plan in the following format:\n"
        "**Breakfast:** [meal]\n**Lunch:** [meal]\n**Dinner:** [meal]"
    ),
    "fertility": (
        "You are a menstrual health assistant specializing in fertility, ovulation, and menstrual cycles. "
        "Answer the question: '{user_input}' directly, without adding unrelated information. "
        "Explain fertility concepts clearly, including ovulation signs, fertility windows, and conception tips if relevant. "
        "Maintain a supportive tone, avoid jargon, and only mention additional symptoms or fertility challenges if specifically asked."
    ),
    "puberty": (
        "You are a menstrual health assistant helping individuals understand puberty, periods, and menstrual health. "
        "Answer the question: '{user_input}' directly, without discussing unrelated topics. "
        "Use clear, factual, and empathetic language, and explain biological processes simply. "
        "If the question involves symptoms like cramps or mood swings, provide practical tips, but do not mention other symptoms unless asked."
    )
}

def load_user_data():
    try:
        with open(USER_DATA_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_data(data):
    with open(USER_DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)

def ask_mistral(prompt):
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {mistral_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mistral-large-latest",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response_data = response.json()
        return response_data.get("choices", [{}])[0].get("message", {}).get("content", "Error: Unable to fetch response from Mistral.").strip()
    except Exception as e:
        return f"Error: {str(e)}"

def ask_gpt(prompt):
    try:
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        
        if response.candidates and response.candidates[0].finish_reason == 3:
            return "FALLBACK_TO_MISTRAL"
        
        if response.text:
            return response.text.strip()
        else:
            return "FALLBACK_TO_MISTRAL"
    except Exception as e:
        return "FALLBACK_TO_MISTRAL"
    finally:
        time.sleep(1)

def determine_intent(user_input, age, cravings):
    user_input = user_input.lower()
    if age < 18:
        return "child_friendly"
    elif "alternative" in user_input and cravings:
        return "cravings_alternatives"
    elif any(word in user_input for word in ["nutrition", "diet", "food", "eat"]):
        return "nutrition"
    elif any(word in user_input for word in ["exercise", "workout", "fitness"]):
        return "exercise"
    elif any(word in user_input for word in ["pregnant", "fertility", "ovulation", "get pregnant"]):
        return "fertility"
    elif any(word in user_input for word in ["puberty", "11 years old", "teen", "young"]):
        return "puberty"
    else:
        return "general_health"

def handle_question(user_input, user_data, user_id):
    age = user_data[user_id]["age"]
    cravings = user_data[user_id]["cravings"]
    cycle_phase = user_data[user_id]["cycle_phase"]
    intent = determine_intent(user_input, age, cravings)

    if intent == "nutrition":
        prompt = PROMPT_TEMPLATES["nutrition"].format(cycle_phase=cycle_phase, cravings=cravings, user_input=user_input)
    elif intent == "child_friendly":
        prompt = PROMPT_TEMPLATES["child_friendly"].format(user_input=user_input)
    elif intent == "exercise":
        prompt = PROMPT_TEMPLATES["exercise"].format(cycle_phase=cycle_phase, user_input=user_input)
    elif intent == "cravings_alternatives":
        prompt = PROMPT_TEMPLATES["cravings_alternatives"].format(cravings=cravings, cycle_phase=cycle_phase, user_input=user_input)
    elif intent == "fertility":
        prompt = PROMPT_TEMPLATES["fertility"].format(user_input=user_input)
    elif intent == "puberty":
        prompt = PROMPT_TEMPLATES["puberty"].format(user_input=user_input)
    else:
        prompt = PROMPT_TEMPLATES["general_health"].format(user_input=user_input)

    response = ask_gpt(prompt)
    return response if response != "FALLBACK_TO_MISTRAL" else ask_mistral(prompt)

@app.route("/", methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        session['user_id'] = str(uuid.uuid4())
        session.modified = True
        return redirect(url_for('onboarding'))
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Health Chatbot</title>
            <style>
                :root {
                    --primary: #ab0aab;
                    --secondary: #DB5968;
                    --light: #FCEAD9;
                    --accent1: #ed495d;
                    --accent2: #f96e83;
                    --dark: #2d645f;
                    --transparent: rgba(245, 53, 92, 0.723);
                }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: var(--light);
                    color: var(--dark);
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }
                h1 {
                    color: var(--primary);
                    text-align: center;
                    margin-bottom: 30px;
                }
                .welcome-box {
                    background: linear-gradient(135deg, var(--primary), var(--accent2));
                    color: white;
                    padding: 20px;
                    border-radius: 15px;
                    text-align: center;
                    margin-bottom: 30px;
                }
                .btn-start {
                    background-color: white;
                    color: var(--primary);
                    font-weight: bold;
                    padding: 12px 30px;
                    margin-top: 15px;
                    border: none;
                    border-radius: 25px;
                    cursor: pointer;
                    transition: all 0.3s;
                }
                .btn-start:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                }
            </style>
        </head>
        <body>
            <div class="welcome-box">
                <h1>Welcome to Health Assistant</h1>
                <p>Your personalized menstrual health companion</p>
                <form method="POST" action="/">
                    <button type="submit" class="btn-start">Get Started</button>
                </form>
            </div>
        </body>
        </html>
    ''')

@app.route("/onboarding", methods=['GET', 'POST'])
def onboarding():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        user_data = load_user_data()
        user_id = session['user_id']
        
        user_data[user_id] = {
            "name": request.form.get('name'),
            "age": int(request.form.get('age')),
            "cycle_phase": request.form.get('cycle_phase'),
            "cravings": request.form.get('cravings'),
            "dietary_specs": None,
            "cuisine": None,
            "allergies": None,
            "last_interaction": datetime.now().isoformat()
        }
        save_user_data(user_data)
        return redirect(url_for('chat_interface'))
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Personalization</title>
            <style>
                :root {
                    --primary: #ab0aab;
                    --secondary: #DB5968;
                    --light: #FCEAD9;
                    --accent1: #ed495d;
                    --accent2: #f96e83;
                    --dark: #2d645f;
                    --transparent: rgba(245, 53, 92, 0.723);
                }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: var(--light);
                    color: var(--dark);
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }
                h1 {
                    color: var(--primary);
                    text-align: center;
                }
                .form-container {
                    background-color: white;
                    padding: 30px;
                    border-radius: 15px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                }
                .form-group {
                    margin-bottom: 20px;
                }
                label {
                    display: block;
                    margin-bottom: 8px;
                    font-weight: 600;
                    color: var(--dark);
                }
                input, select {
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #ddd;
                    border-radius: 8px;
                    font-size: 16px;
                    transition: border 0.3s;
                }
                input:focus, select:focus {
                    border-color: var(--primary);
                    outline: none;
                }
                button {
                    background-color: var(--primary);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 14px;
                    width: 100%;
                    font-size: 16px;
                    font-weight: bold;
                    cursor: pointer;
                    transition: all 0.3s;
                }
                button:hover {
                    background-color: var(--accent1);
                }
            </style>
        </head>
        <body>
            <h1>Let's Personalize Your Experience</h1>
            <div class="form-container">
                <form method="POST" action="/onboarding">
                    <div class="form-group">
                        <label for="name">Your Name</label>
                        <input type="text" id="name" name="name" required>
                    </div>
                    <div class="form-group">
                        <label for="age">Your Age</label>
                        <input type="number" id="age" name="age" min="10" max="100" required>
                    </div>
                    <div class="form-group">
                        <label for="cycle_phase">Current Cycle Phase</label>
                        <select id="cycle_phase" name="cycle_phase" required>
                            <option value="">Select phase</option>
                            <option value="menstrual">Menstrual</option>
                            <option value="follicular">Follicular</option>
                            <option value="ovulatory">Ovulatory</option>
                            <option value="luteal">Luteal</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="cravings">Current Cravings (if any)</label>
                        <input type="text" id="cravings" name="cravings" placeholder="e.g., chocolate, salty, spicy">
                    </div>
                    <button type="submit">Continue to Chat</button>
                </form>
            </div>
        </body>
        </html>
    ''')

@app.route("/chat")
def chat_interface():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    user_id = session['user_id']
    user_data = load_user_data()
    
    if user_id not in user_data:
        return redirect(url_for('onboarding'))
    
    return render_template_string(r'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Chat with Health Assistant</title>
            <style>
                :root {
                    --primary: #ab0aab;
                    --secondary: #DB5968;
                    --light: #FCEAD9;
                    --accent1: #ed495d;
                    --accent2: #f96e83;
                    --dark: #2d645f;
                    --transparent: rgba(245, 53, 92, 0.723);
                }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: var(--light);
                    color: var(--dark);
                    margin: 0;
                    padding: 0;
                    height: 100vh;
                    display: flex;
                    flex-direction: column;
                }
                header {
                    background-color: var(--primary);
                    color: white;
                    padding: 15px 20px;
                    text-align: center;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }
                .chat-container {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    max-width: 800px;
                    width: 100%;
                    margin: 0 auto;
                    padding: 20px;
                    box-sizing: border-box;
                }
                #chatbox {
                    flex: 1;
                    overflow-y: auto;
                    padding: 15px;
                    margin-bottom: 15px;
                    background-color: white;
                    border-radius: 15px;
                    box-shadow: inset 0 0 5px rgba(0,0,0,0.1);
                }
                .message {
                    margin-bottom: 15px;
                    max-width: 80%;
                    padding: 12px 18px;
                    border-radius: 20px;
                    line-height: 1.4;
                    position: relative;
                    animation: fadeIn 0.3s ease-out;
                }
                .user-message {
                    background-color: var(--transparent);
                    color: white;
                    margin-left: auto;
                    border-bottom-right-radius: 5px;
                }
                .bot-message {
                    background-color: var(--secondary);
                    color: white;
                    margin-right: auto;
                    border-bottom-left-radius: 5px;
                }
                .formatted-response {
                    background-color: white;
                    border-radius: 10px;
                    padding: 15px;
                    margin: 10px 0;
                    color: var(--dark);
                    border-left: 4px solid var(--primary);
                }
                .input-area {
                    display: flex;
                    gap: 10px;
                    padding: 10px;
                    background-color: white;
                    border-radius: 30px;
                    box-shadow: 0 -2px 5px rgba(0,0,0,0.05);
                }
                #userInput {
                    flex: 1;
                    padding: 12px 20px;
                    border: 2px solid var(--primary);
                    border-radius: 30px;
                    font-size: 16px;
                    outline: none;
                }
                #sendButton {
                    background-color: var(--primary);
                    color: white;
                    border: none;
                    border-radius: 50%;
                    width: 50px;
                    height: 50px;
                    cursor: pointer;
                    transition: all 0.3s;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                #sendButton:hover {
                    background-color: var(--accent1);
                    transform: scale(1.05);
                }
                .typing-indicator {
                    display: inline-block;
                    padding: 10px 15px;
                    background-color: #eee;
                    border-radius: 20px;
                    color: #666;
                    font-style: italic;
                }
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .meal-planner-input {
                    display: flex;
                    gap: 10px;
                    width: 100%;
                }
                #mealPlannerInput {
                    flex: 1;
                    padding: 12px;
                    border: 2px solid var(--primary);
                    border-radius: 8px;
                }
                #submitMealPlannerAnswer {
                    background-color: var(--primary);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 0 20px;
                    cursor: pointer;
                }
            </style>
        </head>
        <body>
            <header>
                <h1>Health Assistant</h1>
            </header>
            <div class="chat-container">
                <div id="chatbox">
                    <div class="bot-message">
                        Hello! I'm your health assistant. How can I help you today?
                        <div class="formatted-response">
                            You can ask me about:<br>
                            • Nutrition advice<br>
                            • Exercise recommendations<br>
                            • Cycle tracking<br>
                            • General health questions<br><br>
                            Type "meal planner" to get personalized meal plans!
                        </div>
                    </div>
                </div>
                <div class="input-area">
                    <input type="text" id="userInput" placeholder="Type your message here..." autocomplete="off">
                    <button id="sendButton">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="22" y1="2" x2="11" y2="13"></line>
                            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                        </svg>
                    </button>
                </div>
            </div>

            <script>
                let mealPlannerState = null;
                const chatbox = document.getElementById('chatbox');
                const userInput = document.getElementById('userInput');
                const sendButton = document.getElementById('sendButton');
                
                function formatResponse(text) {
                    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                    text = text.replace(/\n/g, '<br>');
                    text = text.replace(/- (.*?)(<br>|$)/g, '• $1<br>');
                    return text;
                }
                
                function addMessage(sender, message, isFormatted = false) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `${sender}-message message`;
                    
                    if (isFormatted) {
                        const formattedDiv = document.createElement('div');
                        formattedDiv.className = 'formatted-response';
                        formattedDiv.innerHTML = formatResponse(message);
                        messageDiv.appendChild(formattedDiv);
                    } else {
                        messageDiv.textContent = message;
                    }
                    
                    chatbox.appendChild(messageDiv);
                    chatbox.scrollTop = chatbox.scrollHeight;
                }
                
                                function handleSpecialCommands(message) {
                    if (message.toLowerCase() === 'meal planner') {
                        startMealPlanner();
                        return true;
                    }
                    return false;
                }
                
                function startMealPlanner() {
                    fetch('/api/start_meal_planner', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: '{{ session["user_id"] }}' })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.error) {
                            addMessage('bot', "Error: " + data.error);
                            return;
                        }
                        
                        mealPlannerState = {
                            questions: data.questions,
                            currentQuestion: 0,
                            answers: {}
                        };
                        
                        askNextMealPlannerQuestion();
                    })
                    .catch(error => {
                        addMessage('bot', "Sorry, I couldn't start the meal planner. Please try again.");
                    });
                }
                
                function askNextMealPlannerQuestion() {
                    if (mealPlannerState.currentQuestion >= mealPlannerState.questions.length) {
                        submitMealPlanner();
                        return;
                    }
                    
                    const question = mealPlannerState.questions[mealPlannerState.currentQuestion];
                    addMessage('bot', question.text);
                    
                    const inputArea = document.querySelector('.input-area');
                    inputArea.innerHTML = `
                        <input type="text" id="mealPlannerInput" placeholder="Your answer...">
                        <button id="submitMealPlannerAnswer">Submit</button>
                    `;
                    
                    document.getElementById('submitMealPlannerAnswer').addEventListener('click', submitMealPlannerAnswer);
                    document.getElementById('mealPlannerInput').addEventListener('keypress', function(e) {
                        if (e.key === 'Enter') submitMealPlannerAnswer();
                    });
                    document.getElementById('mealPlannerInput').focus();
                }
                
                function submitMealPlannerAnswer() {
                    const answer = document.getElementById('mealPlannerInput').value.trim();
                    if (!answer) return;
                    
                    const currentQuestion = mealPlannerState.questions[mealPlannerState.currentQuestion];
                    mealPlannerState.answers[currentQuestion.id] = answer;
                    
                    addMessage('user', answer);
                    mealPlannerState.currentQuestion++;
                    
                    const inputArea = document.querySelector('.input-area');
                    inputArea.innerHTML = `
                        <input type="text" id="userInput" placeholder="Type your message here..." autocomplete="off">
                        <button id="sendButton">
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <line x1="22" y1="2" x2="11" y2="13"></line>
                                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                            </svg>
                        </button>
                    `;
                    
                    document.getElementById('sendButton').addEventListener('click', sendMessage);
                    document.getElementById('userInput').addEventListener('keypress', function(e) {
                        if (e.key === 'Enter') sendMessage();
                    });
                    
                    if (mealPlannerState.currentQuestion < mealPlannerState.questions.length) {
                        setTimeout(askNextMealPlannerQuestion, 500);
                    } else {
                        submitMealPlanner();
                    }
                }
                
                function submitMealPlanner() {
                    addMessage('bot', "Generating your personalized meal plan...");
                    
                    fetch('/api/submit_meal_planner', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            user_id: '{{ session["user_id"] }}',
                            ...mealPlannerState.answers
                        })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.error) {
                            addMessage('bot', "Error: " + data.error);
                        } else {
                            addMessage('bot', data.meal_plan, true);
                        }
                        mealPlannerState = null;
                    })
                    .catch(error => {
                        addMessage('bot', "Sorry, I couldn't generate your meal plan. Please try again.");
                        mealPlannerState = null;
                    });
                }
                
                function sendMessage() {
                    const message = userInput.value.trim();
                    if (!message) return;
                    
                    if (handleSpecialCommands(message)) {
                        userInput.value = '';
                        return;
                    }
                    
                    addMessage('user', message);
                    userInput.value = '';
                    
                    const typingIndicator = document.createElement('div');
                    typingIndicator.className = 'bot-message message typing-indicator';
                    typingIndicator.textContent = 'Assistant is typing...';
                    chatbox.appendChild(typingIndicator);
                    chatbox.scrollTop = chatbox.scrollHeight;
                    
                    fetch('/api/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            user_id: '{{ session["user_id"] }}',
                            message: message
                        })
                    })
                    .then(response => response.json())
                    .then(data => {
                        chatbox.removeChild(typingIndicator);
                        if (data.error) {
                            addMessage('bot', "Error: " + data.error);
                        } else {
                            addMessage('bot', data.response, true);
                        }
                    })
                    .catch(error => {
                        chatbox.removeChild(typingIndicator);
                        addMessage('bot', "Sorry, I encountered an error. Please try again.");
                    });
                }
                
                // Initialize event listeners
                sendButton.addEventListener('click', sendMessage);
                userInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') sendMessage();
                });
                
                // Focus input field on page load
                userInput.focus();
            </script>
        </body>
        </html>
    ''', user_id=user_id)

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_id = data.get('user_id')
    message = data.get('message')
    
    if not user_id or not message:
        return jsonify({'error': 'User ID and message are required'}), 400
    
    user_data = load_user_data()
    
    if user_id not in user_data:
        return jsonify({'error': 'User not registered'}), 404
    
    try:
        response = handle_question(message, user_data, user_id)
        return jsonify({
            'response': response,
            'user_id': user_id,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/start_meal_planner', methods=['POST'])
def start_meal_planner():
    user_id = request.json.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    
    return jsonify({
        'questions': [
            {
                'id': 'dietary_specs',
                'text': 'Do you have any dietary specifications? (e.g., vegetarian, vegan, gluten-free)',
                'type': 'text'
            },
            {
                'id': 'cuisine',
                'text': 'What type of cuisine do you prefer? (e.g., Italian, Indian, Mediterranean)',
                'type': 'text'
            },
            {
                'id': 'allergies',
                'text': 'Do you have any food allergies we should know about?',
                'type': 'text'
            }
        ]
    })

@app.route('/api/submit_meal_planner', methods=['POST'])
def submit_meal_planner():
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    
    user_data = load_user_data()
    if user_id not in user_data:
        return jsonify({'error': 'User not found'}), 404
    
    # Update user data with meal planner preferences
    user_data[user_id].update({
        "dietary_specs": data.get('dietary_specs', 'none'),
        "cuisine": data.get('cuisine', 'no preference'),
        "allergies": data.get('allergies', 'none')
    })
    save_user_data(user_data)
    
    # Generate meal plan
    prompt = PROMPT_TEMPLATES["meal_planner"].format(
        cycle_phase=user_data[user_id]["cycle_phase"],
        cravings=user_data[user_id]["cravings"],
        dietary_specs=user_data[user_id]["dietary_specs"],
        cuisine=user_data[user_id]["cuisine"],
        allergies=user_data[user_id]["allergies"]
    )
    
    meal_plan = ask_gpt(prompt)
    return jsonify({'meal_plan': meal_plan})

@app.route('/api/quiz', methods=['GET'])
def quiz():
    return jsonify({
        "questions": [
            {
                "question": "How long is an average menstrual cycle?",
                "options": ["21 days", "28 days", "35 days"],
                "answer": 1
            },
            {
                "question": "Which phase comes after ovulation?",
                "options": ["Follicular", "Luteal", "Menstrual"],
                "answer": 1
            }
        ]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)