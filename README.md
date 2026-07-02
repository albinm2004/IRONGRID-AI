# IRONGRID AI — RAG Gym Front Desk Assistant

IRONGRID AI is a production-ready **Retrieval-Augmented Generation (RAG)** conversational virtual receptionist designed to automate repetitive customer service inquiries for premium fitness clubs. 

Built using a modern technical stack—**Flask, ChromaDB, SentenceTransformers (`all-MiniLM-L6-v2`), and Google Gemini 2.0 Flash API**—the system answers complex visitor queries regarding membership tiers, timings, equipment, training costs, and safety rules while completely preventing hallucinations.

---

## 🚀 Key Features

* **Grounded RAG Architecture**: Restricts LLM response synthesis strictly to retrieved context, preventing guess-work, hallucinations, or out-of-scope advice (e.g. customized diet/workout plans).
* **225 Fact Chunks**: A robust structured knowledge base containing 225 gym facts categorized across 11 areas: memberships, timings, trainers, facilities, rules, and FAQs.
* **Persistent Vector Storage**: Leverages a local, persistent ChromaDB database configured with HNSW cosine similarity search.
* **Local Semantic Encoding**: Translates natural language inquiries into dense 384-dimensional arrays using the optimized local `all-MiniLM-L6-v2` transformer model.
* **Top-5 Document Retrieval**: Dynamically extracts the top 5 most relevant database knowledge chunks to ground the LLM context frame.
* **Sliding Session History**: Retains chat dialogue history across a sliding window of 10 conversation turns for fluid, contextual exchanges.
* **Confidence Auto-Scoring**: Classifies query matches into human-readable similarity ratings: **High** ($\ge$ 0.55), **Medium** ($\ge$ 0.35), or **Low** ($<$ 0.35) badges based on similarity scores.
* **Source & Attribution Audit**: Displays retrieved database category and subcategory tags next to answers to guarantee verification transparency.
* **Follow-up Suggestion Chips**: Auto-generates 3 relevant follow-up inquiry suggestions based on the category of retrieved data.
* **Robust Error Handling**: If API connections or rate limits fail, the system automatically redirects the query to serve direct database template text matches.
* **Premium Slate-Theme UI**: Light slate-blue responsive interface featuring live operating-hour status clocks and typing animation indicators.

---

## 🛠️ Technology Stack

* **Backend Logic**: Python 3.13 + Flask
* **Frontend Interface**: HTML5 + CSS3 (Vanilla) + JavaScript (Vanilla)
* **Vector Vector DB**: ChromaDB 1.5.9
* **Dense Embeddings**: SentenceTransformers (`all-MiniLM-L6-v2`)
* **Generative Language Model**: Google Gemini 2.0 Flash API (via `google-genai`)
* **Database Source**: Structured JSON Knowledge Store

---

## 📁 Folder Structure

```
IRONGRID-AI/
├── app.py                      # Flask backend API endpoint & RAG pipeline controller
├── embed_knowledge.py          # Vector database ingestion script (run once)
├── knowledge_base.json         # Structured corpus of 225 verified gym facts
├── requirements.txt            # Python software package dependency list
├── .gitignore                  # Git repository exclusion parameters
├── .env.example                # Environment variables template file
├── README.md                   # Repository guide and execution manual
│
├── static/                     # Serves frontend client assets
│   ├── index.html              # HTML5 chatbot interface markup structure
│   ├── style.css               # Design system token styling and animation styles
│   └── script.js               # Async fetch API controller and state manager
│
├── chroma_db/                  # Persistent HNSW vector database index (local directory)
│
└── assets/                     # Graphic resources and document attachments
    ├── logo/                   # Project brand and icon logo assets
    ├── screenshots/            # UI demonstration captures
    └── presentation/           # Presentation materials
        ├── irongrid_presentation_redesigned.pptx  # Premium redesigned slide deck
        ├── generate_pptx_redesigned.py            # Custom slide deck python compiler
        └── slides_preview.html                    # Redesigned slide preview page
```

---

## 💻 Installation & Setup

### Prerequisites
* **Python 3.10+** (Python 3.13 recommended)
* **Google Gemini API Key** (Obtain a free key at [Google AI Studio](https://aistudio.google.com/apikey))

### 1. Clone & Navigate
Clone this repository to your local system and navigate to the project directory:
```bash
git clone https://github.com/your-username/IRONGRID-AI.git
cd IRONGRID-AI
```

### 2. Configure Virtual Environment
Set up a clean virtual environment to isolate the project packages:
```bash
# Create the virtual environment folder
python -m venv venv

# Activate on Windows (PowerShell/CMD)
venv\Scripts\activate

# Activate on macOS/Linux
source venv/bin/activate
```

### 3. Install Package Dependencies
Install the required packages using pip:
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Secrets
Create a local `.env` configuration file from the provided example template:
```bash
# Windows command line
copy .env.example .env

# macOS/Linux/Git Bash command line
cp .env.example .env
```
Open `.env` in a text editor and replace the placeholder with your actual Google Gemini API key:
```env
GEMINI_API_KEY=AIzaSy...your_gemini_api_key
```

### 5. Generate Vector Embeddings (Ingestion)
Run the embedding pipeline to read `knowledge_base.json`, encode the chunks, and ingest them into your local persistent database directory:
```bash
python embed_knowledge.py
```
*Note: During the first run, SentenceTransformers will automatically download the ~80MB embedding model files. Please wait for this to complete. The script will output database ingestion statistics and execute a sample validation search to confirm database functionality.*

---

## 🏃 Running the Application

Start the Flask development server:
```bash
python app.py
```
Open your browser and navigate to:
```
http://localhost:5000
```
You can now interact with the virtual receptionist in real-time. The server console will log details for each user inquiry, RAG match count, confidence score levels, and API call events.

---

## ⚙️ RAG Data Processing Flow

```
User Query Input (Web UI)
        │
        ▼ (POST to /api/chat)
Flask API Controller (app.py)
        │
        ▼ (SentenceTransformers)
Query Text Vectorized (384-dimensional embedding)
        │
        ▼ (ChromaDB query match)
Search chroma_db/ HNSW Index (Cosine similarity space)
        │
        ▼
Extract Top-5 Matching Fact Chunks
        │
        ▼
Construct Prompt (System prompt rules + Context chunks + 10-turn history)
        │
        ▼
Call Google Gemini 2.0 API
        │
        ├──▶ [API Success]: Synthesize conversational grounded answer
        │
        └──▶ [API Error (429/connection)]: Shift to robust local fallback
                                           (serves raw text directly from the top DB match)
        │
        ▼
Send JSON response payload to client UI containing:
{
  "answer": "Grounded answer text...",
  "confidence": average cosine similarity score,
  "confidence_level": "high" | "medium" | "low",
  "sources": list of category/subcategory metadata matching source tags,
  "follow_ups": 3 dynamically generated next-question options
}
```

---

## 📋 API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| **GET** | `/` | Serves the main landing page and frontend static assets. |
| **POST** | `/api/chat` | Main conversational pipeline endpoint. Accepts query payloads and generates RAG responses. |
| **GET** | `/api/health` | Diagnostic endpoint checking vectors loaded in ChromaDB and Gemini configuration. |
| **GET** | `/api/greeting` | Serves greeting greetings based on active operating times. |

---

## 🔮 Future Roadmap

* **🎙️ Voice Recognition**: Integration of Speech-to-Text and Text-to-Speech layers for hands-free queries.
* **🖥️ Administrator Dashboard**: Portal enabling gym staff to view, delete, or upload knowledge chunks dynamically.
* **💬 Messaging Channels**: Connect the RAG backend directly to WhatsApp, Telegram, or Facebook Messenger.
* **💳 Direct Booking Integration**: Process membership class signups and payment gateway transactions inside chat panels.
* **🌐 Multilingual Support**: Add translation models to capture queries in local regional dialects.

---

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
