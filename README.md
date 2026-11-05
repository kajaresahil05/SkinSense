# SkinSense — Intelligent Dermatological Assessment System

**SkinSense** is a full-stack, AI-powered dermatological assessment web application that combines computer vision for skin disease classification, a fuzzy logic inference engine for symptom severity triaging, a dynamic conversational assistant, and persistent assessment logging and analytics.

---

## 🌟 Key Features

1. **Dataset2 Keras Skin Disease Classifier (`MobileNetV2`)**
   - Uses the bundled nine-class Dataset2 checkpoint with 224 x 224 RGB inputs.
   - Image quality validation and Gemini suitability screening before disease classification. Image screening requires upload consent and an available Gemini quota.
   - Reports the model scores and flags low-confidence predictions.

2. **Fuzzy Logic Symptom Severity Engine**
   - Multivariable fuzzy inference mapping 6 symptom vectors (Itching, Pain, Redness, Duration, Fever, Burning) to a continuous 0–100 severity scale.
   - Increasing a symptom cannot lower the score. High severity triggers a priority review.
   - Severity categories (*Mild*, *Moderate*, *High / Severe*) with detailed rule activation breakdown.

3. **Clinical Decision Chain Visualization**
   - **Step 1**: Keras Image Classification & Quality Validation.
   - **Step 2**: Patient Symptom Vector Extraction.
   - **Step 3**: Fuzzy Logic Severity Calculation.
   - **Step 4**: Clinical Summary Synthesis & Top 3 Condition Probabilities.

4. **Dialogflow / AI Conversational Assistant**
   - Natural language skin health assistant.
   - Retrieves and explains saved assessments via Assessment ID (`#ASS-XXXXXX`).
   - Direct image attachment analysis support within the chat.

5. **History Log & Model Analytics Dashboard**
   - Persistent SQLite assessment records with search and class filtering.
   - Live prediction statistics and Dataset2 validation metrics from the supplied 181-sample report.

---

## 🛠️ Technology Stack

- **Frontend**: HTML5, Vanilla CSS3 (Dark Navy Glassmorphism Theme), JavaScript (ES6+), Bootstrap 5, Chart.js.
- **Backend**: Python 3.12+, Flask 3.0, Flask-CORS, REST API.
- **Machine Learning**: TensorFlow, Keras, MobileNetV2.
- **Fuzzy Logic**: Python fuzzy membership and rule evaluation.
- **Database**: SQLite 3.
- **Conversational AI**: Google Gemini API (`google-genai`) / Domain NLP fallback engine.

---

## 🚀 Execution Instructions

### Prerequisites
- Python 3.12 or higher installed.

### 1. Setup Virtual Environment (Windows PowerShell)

```powershell
# Navigate to project root
cd "d:\Downloads\SkinSense — Intelligent Dermatological Assessment System"

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1
```

*(Linux/macOS equivalent)*
```bash
python3 -m venv venv
source venv/bin/activate
```

---

### 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

---

### 3. Verify Model Files

The app loads `Dataset2/skinsense_dataset2_mobilenetv2.keras` and `Dataset2/skinsense_dataset2_class_names.json` at startup.

---

### 4. Run Automated Test Suite

```powershell
python run_tests.py
```

---

### 5. Start the Flask Backend Server

```powershell
python app.py
```

Access the application in your browser at:
`http://127.0.0.1:5000`

---

## 📡 REST API Endpoints

- `GET /api/health` — Returns system health status and active CNN & Fuzzy engine availability.
- `POST /api/predict` — Accepts image file, symptom inputs, and `image_screening_consent=true`. Returns an assessment after screening. Unsuitable images return 422 and unavailable screening returns 503.
- `POST /api/assess-symptoms` — Evaluates standalone symptom vector using Fuzzy Severity Engine.
- `POST /api/chat` — Processes user prompt or attached image; returns dynamic conversational response.
- `GET /api/history` — Retrieves saved assessments with search and class filtering.
- `GET /api/history/<assessment_id>` — Retrieves single assessment record.
- `DELETE /api/history/<assessment_id>` — Deletes an assessment record.
- `GET /api/analytics` — Returns model benchmark metrics and live prediction stats.

---

## ⚠️ Medical Safety Disclaimer

SkinSense is an educational prototype and decision-support demonstration system. AI predictions and fuzzy severity scores are preliminary statistical estimates and **do not constitute a confirmed clinical diagnosis or medical prescription**. Always consult a certified dermatologist or healthcare professional for clinical evaluation.
