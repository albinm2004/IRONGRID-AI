"""
IRONGRID AI — Flask Backend with RAG Pipeline
Serves the chatbot frontend and handles RAG-powered responses
using ChromaDB + SentenceTransformers + Google Gemini API.

Run: python app.py
"""

import logging
import os
import uuid
from datetime import datetime

import chromadb
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from sentence_transformers import SentenceTransformer
from google import genai

# ── Load environment variables ──────────────────────────────────
load_dotenv()

# ── Configuration ───────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "irongrid_knowledge"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K = 5                       # Number of chunks to retrieve (ChromaDB Top-5)
MAX_HISTORY_TURNS = 10          # Conversation memory depth
MAX_RETRIES = 3                 # LLM API retry count
PORT = 5000

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("irongrid")

# ── Flask App ───────────────────────────────────────────────────
# We use standard Flask rendering directories for index.html
app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

# ── In-memory session store ────────────────────────────────────
sessions: dict[str, list[dict]] = {}

# ── System Prompt ───────────────────────────────────────────────
SYSTEM_PROMPT = """You are IRONGRID's front-desk assistant. Be warm, concise, professional. Answer ONLY from the context below. If info is missing, say "Please contact our front desk." Never hallucinate. Use bullet points for lists. Keep answers under 100 words. Use Rs for prices. Never say "As an AI".

CONTEXT:
{context}
"""


# ── Load Models & ChromaDB (once at startup) ────────────────────
def load_embedding_model():
    """Load the SentenceTransformer model."""
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    logger.info("Embedding model loaded.")
    return model


def load_chroma_collection():
    """Load the persistent ChromaDB collection."""
    logger.info(f"Connecting to persistent ChromaDB at: {DB_DIR}")
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    logger.info(f"Connected to ChromaDB collection: '{COLLECTION_NAME}' (contains {collection.count()} vectors)")
    return collection


def load_gemini_client():
    """Initialize the Gemini API client."""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set! LLM responses will fail.")
        return None
    client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info(f"Gemini client initialized (model: {GEMINI_MODEL})")
    return client


# Initialize globals
embedder = load_embedding_model()
chroma_collection = load_chroma_collection()
gemini_client = load_gemini_client()


# ── RAG Pipeline ────────────────────────────────────────────────
def retrieve_context(query: str, top_k: int = TOP_K) -> tuple[str, list[dict], float]:
    """
    Embed the query and retrieve top-k relevant chunks from ChromaDB.
    Returns: (formatted_context, sources, avg_confidence)
    """
    query_embedding = embedder.encode([query]).tolist()

    results = chroma_collection.query(
        query_embeddings=query_embedding,
        n_results=top_k
    )

    documents = results["documents"][0] if results["documents"] else []
    metadatas = results["metadatas"][0] if results["metadatas"] else []
    distances = results["distances"][0] if results["distances"] else []

    if not documents:
        return "", [], 0.0

    # Build formatted context and sources mapping
    context_parts = []
    sources = []
    similarities = []

    for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
        # Cosine distance = 1 - Cosine similarity.
        # Cosine similarity = 1 - Cosine distance.
        sim = max(0.0, min(1.0, 1.0 - dist))
        similarities.append(sim)

        context_parts.append(f"[Source {i+1}: {meta['title']}]\n{doc}")
        sources.append({
            "category": meta["category"],
            "subcategory": meta["subcategory"],
            "title": meta["title"],
            "source": meta["source"],
            "chunk_id": meta["chunk_id"],
            "raw_answer": meta["raw_answer"],
            "relevance": round(sim, 3),
        })

    context = "\n\n".join(context_parts)
    avg_confidence = sum(similarities) / len(similarities) if similarities else 0.0

    return context, sources, round(avg_confidence, 3)


def classify_confidence(score: float) -> str:
    """Classify confidence score into human-readable level."""
    if score >= 0.55:
        return "high"
    elif score >= 0.35:
        return "medium"
    else:
        return "low"


def build_messages(system_prompt: str, history: list[dict], user_message: str) -> list[dict]:
    """Build the message list for Gemini, including conversation history."""
    messages = []

    # Add conversation history (last N turns)
    recent_history = history[-(MAX_HISTORY_TURNS * 2):]
    for msg in recent_history:
        messages.append(msg)

    # Add current user message
    messages.append({"role": "user", "parts": [{"text": user_message}]})

    return messages


def call_gemini(system_prompt: str, messages: list[dict]) -> str:
    """Call Gemini API with retry logic and fast-fail on quota limits."""
    if not gemini_client:
        return "I'm having trouble connecting to my knowledge system right now. Please try again in a moment, or contact the front desk directly."

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=messages,
                config={
                    "system_instruction": system_prompt,
                    "temperature": 0.3,
                    "max_output_tokens": 256,
                    "top_p": 0.8,
                },
            )

            if response and response.text:
                return response.text.strip()
            else:
                logger.warning(f"Empty response from Gemini (attempt {attempt})")

        except Exception as e:
            last_error = e
            error_msg = str(e).lower()
            logger.error(f"Gemini API error (attempt {attempt}/{MAX_RETRIES}): {e}")
            
            # Fast fail for quota/rate limit/model errors to eliminate latency
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg or "404" in error_msg:
                logger.warning("Quota exceeded or model not found. Fast failing to fallback.")
                break
                
            if attempt < MAX_RETRIES:
                wait_time = 2 * attempt  # 2s, 4s delay is enough for transient network issues
                logger.info(f"API issue. Waiting {wait_time}s before retry...")
                import time
                time.sleep(wait_time)

    logger.error(f"All {MAX_RETRIES} Gemini attempts failed. Last error: {last_error}")
    return "I'm having trouble processing your request right now. Please try again in a moment, or reach out to the front desk directly."


def generate_follow_ups(query: str, answer: str, sources: list[dict]) -> list[str]:
    """Generate suggested follow-up questions based on the retrieved sources."""
    categories = list(set(s["category"] for s in sources))

    follow_up_map = {
        "Membership": [
            "What payment methods do you accept?",
            "Can I freeze my membership?",
            "Do you offer student discounts?",
        ],
        "Equipment": [
            "Do you have personal trainers?",
            "What are the gym timings?",
            "Is there a functional training zone?",
        ],
        "Trainers": [
            "How much does personal training cost?",
            "Do you have female trainers?",
            "What group classes do you offer?",
        ],
        "Group Classes": [
            "What is the class schedule?",
            "How do I book a class?",
            "Do you have yoga classes?",
        ],
        "Facilities": [
            "Do you have a steam room?",
            "Is parking free?",
            "Do you have a protein café?",
        ],
        "Safety": [
            "Do you have first aid facilities?",
            "Are there security cameras?",
            "How often is equipment maintained?",
        ],
        "Nutrition": [
            "Do you offer meal plans?",
            "Do you sell protein supplements?",
            "Can vegetarians get enough protein?",
        ],
        "Rules": [
            "What is the dress code?",
            "Can I bring my own trainer?",
            "What are the guest rules?",
        ],
        "Timings": [
            "Can I access the gym 24/7?",
            "What are the peak hours?",
            "Is the gym open on holidays?",
        ],
        "FAQ": [
            "What membership plans do you offer?",
            "Can beginners join?",
            "Do you have a free trial?",
        ],
        "About the Gym": [
            "What makes IRONGRID different?",
            "What are the membership plans?",
            "Can I visit before joining?",
        ],
    }

    suggestions = []
    for cat in categories:
        if cat in follow_up_map:
            for q in follow_up_map[cat]:
                if q.lower() not in query.lower() and q not in suggestions:
                    suggestions.append(q)
                    if len(suggestions) >= 3:
                        return suggestions

    # Fallback suggestions
    fallback = [
        "What membership plans do you offer?",
        "What are the gym timings?",
        "Do you have a free trial?",
    ]
    while len(suggestions) < 2:
        for q in fallback:
            if q not in suggestions:
                suggestions.append(q)
                break
        else:
            break

    return suggestions[:3]


def get_time_greeting() -> str:
    """Return a time-appropriate greeting."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    elif 17 <= hour < 21:
        return "Good evening"
    else:
        return "Hey there"


# ── API Routes ──────────────────────────────────────────────────
@app.route("/")
def index():
    """Serve the main frontend page statically."""
    return app.send_static_file("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    """Main RAG chatbot endpoint using ChromaDB."""
    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({"error": "Missing 'message' field"}), 400

    user_message = data["message"].strip()
    session_id = data.get("session_id", str(uuid.uuid4()))

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    logger.info(f"[{session_id[:8]}] User: {user_message}")

    # 1. Retrieve context from ChromaDB
    context, sources, confidence = retrieve_context(user_message)
    confidence_level = classify_confidence(confidence)

    logger.info(f"[{session_id[:8]}] Retrieved {len(sources)} chunks, confidence: {confidence} ({confidence_level})")

    # 2. Build system prompt with injected context
    if context:
        system = SYSTEM_PROMPT.format(context=context)
    else:
        system = SYSTEM_PROMPT.format(
            context="No relevant information found in the knowledge base."
        )

    # 3. Get conversation history & prune oldest sessions if capacity exceeded to prevent memory leaks
    if len(sessions) > 500:
        # Evict the 100 oldest sessions
        oldest_keys = list(sessions.keys())[:100]
        for k in oldest_keys:
            sessions.pop(k, None)
        logger.info("Session store capacity reached: pruned 100 oldest sessions.")

    if session_id not in sessions:
        sessions[session_id] = []
    history = sessions[session_id]

    # 4. Build messages and call Gemini
    messages = build_messages(system, history, user_message)
    answer = call_gemini(system, messages)

    # 4.1 Console-only fallback tracking (if Gemini fails due to quota or connection)
    if "I'm having trouble processing your request" in answer:
        logger.info(f"[{session_id[:8]}] Gemini API unavailable. Using ChromaDB fallback.")
        # Generate the best possible response directly from the retrieved documents naturally (no visible markers)
        if sources:
            answer = sources[0]["raw_answer"]
        else:
            answer = "I don't have that specific information right now. Please contact our front desk directly for assistance."

    # 5. Update conversation history
    history.append({"role": "user", "parts": [{"text": user_message}]})
    history.append({"role": "model", "parts": [{"text": answer}]})

    # Trim history to prevent unbounded growth
    if len(history) > MAX_HISTORY_TURNS * 2:
        sessions[session_id] = history[-(MAX_HISTORY_TURNS * 2):]

    # 6. Generate follow-up suggestions
    follow_ups = generate_follow_ups(user_message, answer, sources)

    # 7. Build response payload (Top 5 sources returned as configured)
    response = {
        "answer": answer,
        "session_id": session_id,
        "confidence": confidence,
        "confidence_level": confidence_level,
        "sources": [
            {"category": s["category"], "subcategory": s["subcategory"], "relevance": s["relevance"]}
            for s in sources[:5]  # Top 5 sources limit
        ],
        "follow_ups": follow_ups,
    }

    logger.info(f"[{session_id[:8]}] Bot: {answer[:80]}...")

    return jsonify(response)


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint reflecting ChromaDB integration."""
    return jsonify({
        "status": "ok",
        "service": "IRONGRID AI",
        "vectors": chroma_collection.count() if chroma_collection else 0,
        "gemini": "connected" if gemini_client else "not configured",
        "embedding_model": EMBEDDING_MODEL,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/greeting", methods=["GET"])
def greeting():
    """Return a time-appropriate greeting message."""
    greet = get_time_greeting()
    now = datetime.now()
    day = now.weekday()  # 0=Mon, 6=Sun
    hour = now.hour + now.minute / 60

    if day == 6:  # Sunday
        is_open = 6 <= hour < 21
    else:
        is_open = 5 <= hour < 23

    return jsonify({
        "greeting": greet,
        "is_open": is_open,
        "message": f"{greet}! Welcome to IRONGRID. I'm your virtual front desk assistant — ask me about **membership plans**, **equipment**, **timings**, **trainers**, **classes**, or anything about the gym!",
    })


# ── Main ────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not GEMINI_API_KEY:
        logger.warning("=" * 50)
        logger.warning("  GEMINI_API_KEY not set!")
        logger.warning("  Create a .env file with:")
        logger.warning("  GEMINI_API_KEY=your_key_here")
        logger.warning("=" * 50)

    logger.info(f"Starting IRONGRID AI on http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
