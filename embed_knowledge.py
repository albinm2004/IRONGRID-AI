"""
IRONGRID AI — Embedding Pipeline
Loads knowledge_base.json and embeds all chunks into a persistent ChromaDB database
using SentenceTransformer all-MiniLM-L6-v2.

Run once: python embed_knowledge.py
"""

import json
import os
import sys
import time
from collections import Counter

import chromadb
from sentence_transformers import SentenceTransformer

# ── Config ──────────────────────────────────────────────────────
KNOWLEDGE_FILE = os.path.join(os.path.dirname(__file__), "knowledge_base.json")
DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "irongrid_knowledge"


def load_knowledge(path: str) -> list[dict]:
    """Load and validate the JSON knowledge base."""
    if not os.path.exists(path):
        print(f"[ERROR] Knowledge file not found: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or len(data) == 0:
        print("[ERROR] Knowledge base is empty or not a JSON array.")
        sys.exit(1)

    # Validate required fields
    required = {"id", "category", "subcategory", "question", "answer"}
    for i, chunk in enumerate(data):
        missing = required - set(chunk.keys())
        if missing:
            print(f"[WARN] Chunk {i} missing fields: {missing}")

    return data


def print_stats(chunks):
    """Print category statistics."""
    cats = Counter(c["category"] for c in chunks)
    print("\n[STATS] Knowledge Base Statistics:")
    print(f"    Total chunks: {len(chunks)}")
    print(f"    Categories:   {len(cats)}")
    print("    ---------------------------------")
    for cat, count in cats.most_common():
        print(f"    {cat:<25} {count:>4} chunks")
    print()


def embed_and_store(chunks, model_name, db_dir, collection_name):
    """Embed documents and store them in a persistent ChromaDB database."""
    print(f"\n[*] Initializing persistent ChromaDB client at: {db_dir}")
    client = chromadb.PersistentClient(path=db_dir)

    print(f"[*] Fetching or creating collection: {collection_name}")
    # Use cosine similarity space ("hnsw:space": "cosine")
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

    # If collection already has data, recreate it to optimize index storage and clear records
    existing_count = collection.count()
    if existing_count > 0:
        print(f"[*] Drop and recreate collection to optimize index storage (clearing {existing_count} documents)...")
        try:
            client.delete_collection(collection_name)
            collection = client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            print("[OK] Collection re-created and cleared.")
        except Exception as e:
            print(f"[WARN] Failed to drop collection: {e}. Clearing manually...")
            all_ids = collection.get()["ids"]
            if all_ids:
                collection.delete(ids=all_ids)
            print("[OK] Collection cleared manually.")

    print(f"\n[*] Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)

    # Prepare document text, ids, and metadata structures
    documents = []
    ids = []
    metadatas = []

    for chunk in chunks:
        doc_text = f"Q: {chunk['question']}\nA: {chunk['answer']}"
        documents.append(doc_text)
        ids.append(chunk["id"])
        metadatas.append({
            "category": chunk["category"],
            "subcategory": chunk["subcategory"],
            "title": f"{chunk['category']} > {chunk['subcategory']}",
            "source": f"{chunk['category']}_{chunk['id']}",
            "chunk_id": chunk["id"],
            "raw_answer": chunk["answer"]
        })

    print(f"[*] Generating embeddings for {len(documents)} chunks...")
    start = time.time()
    embeddings = model.encode(documents, show_progress_bar=True, batch_size=64)
    elapsed = time.time() - start
    print(f"[OK] Embeddings generated in {elapsed:.1f}s")

    # Convert numpy arrays to nested lists for ChromaDB
    embeddings_list = embeddings.tolist()

    print("[*] Adding data to ChromaDB...")
    collection.add(
        ids=ids,
        embeddings=embeddings_list,
        documents=documents,
        metadatas=metadatas
    )
    print(f"[OK] Stored {collection.count()} vectors inside ChromaDB.")
    return collection, model


def test_search(collection, model, query="membership plans pricing"):
    """Quick verification — test query."""
    print(f"\n[TEST] Verification -- test query: '{query}'")
    query_embedding = model.encode([query]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=3
    )

    print("    Top 3 results:")
    ids = results["ids"][0] if results["ids"] else []
    metadatas = results["metadatas"][0] if results["metadatas"] else []
    distances = results["distances"][0] if results["distances"] else []

    for rank, (doc_id, meta, dist) in enumerate(zip(ids, metadatas, distances)):
        # Cosine distance = 1 - Cosine similarity.
        # Cosine similarity = 1 - Cosine distance.
        similarity = 1.0 - dist
        print(f"    {rank+1}. [{doc_id}] {meta['title']}  (similarity: {similarity:.4f})")


def main():
    print("=" * 56)
    print("   IRONGRID AI -- ChromaDB Knowledge Embedding Pipeline")
    print("=" * 56)

    # 1. Load knowledge
    print(f"\n[*] Loading knowledge base: {KNOWLEDGE_FILE}")
    chunks = load_knowledge(KNOWLEDGE_FILE)
    print(f"[OK] Loaded {len(chunks)} chunks")

    # 2. Print stats
    print_stats(chunks)

    # 3. Embed and store
    collection, model = embed_and_store(chunks, MODEL_NAME, DB_DIR, COLLECTION_NAME)

    # 4. Quick verification
    test_search(collection, model)

    print("\n" + "=" * 56)
    print("   [OK] Embedding pipeline complete!")
    print("   Next: set your GEMINI_API_KEY in .env, then run:")
    print("         python app.py")
    print("=" * 56 + "\n")


if __name__ == "__main__":
    main()
