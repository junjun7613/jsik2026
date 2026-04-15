#!/usr/bin/env python3
"""
Embed rdfs:comment values from all.ttl and upsert to Pinecone.

For each epig:Inscription in the TTL file, this script:
1. Parses the TTL file with rdflib
2. Extracts rdfs:comment (and metadata) for each Inscription
3. Embeds the comment text via the OpenAI Embeddings API
4. Upserts each vector to a Pinecone index

Required environment variables:
    OPENAI_API_KEY      – OpenAI API key
    PINECONE_API_KEY    – Pinecone API key
    PINECONE_INDEX_NAME – Name of the target Pinecone index
                         (must already exist with dimension=1536, metric=cosine)

Usage:
    python upsert_to_pinecone.py
    python upsert_to_pinecone.py --ttl rdf_output/claude/all.ttl
    python upsert_to_pinecone.py --ttl rdf_output/claude/all.ttl --batch-size 50 --limit 100
    python upsert_to_pinecone.py --ttl rdf_output/claude/all.ttl --resume
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (inscription_llm/.env)
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Optional dependency check – give friendly error messages
# ---------------------------------------------------------------------------
try:
    import rdflib
    from rdflib import RDF, RDFS, Namespace, URIRef
except ImportError:
    print("Error: rdflib is required.  Install with: pip install rdflib")
    sys.exit(1)

try:
    import openai
except ImportError:
    print("Error: openai is required.  Install with: pip install openai")
    sys.exit(1)

try:
    from pinecone import Pinecone
except ImportError:
    print("Error: pinecone is required.  Install with: pip install pinecone")
    sys.exit(1)

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent

# RDF namespaces used in all.ttl
EPIG = Namespace("http://example.org/epigraphy/")
DCTERMS = Namespace("http://purl.org/dc/terms/")

# OpenAI embedding model and its output dimension
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

# Default paths
DEFAULT_TTL = SCRIPT_DIR / "rdf_output" / "claude" / "all.ttl"
DEFAULT_PROGRESS_FILE = SCRIPT_DIR / "upsert_to_pinecone_progress.json"


# ---------------------------------------------------------------------------
# TTL parsing
# ---------------------------------------------------------------------------
def parse_inscriptions(ttl_path: Path) -> list[dict]:
    """
    Parse all.ttl and return a list of inscription dicts.

    Each dict contains:
        id        – EDCS-ID string (used as Pinecone vector ID)
        comment   – rdfs:comment text (to be embedded)
        text      – epig:text (inscription text)
        place     – local name of epig:place URI
        province  – local name of epig:province URI
        pleiades  – epig:pleiadesId value
        dating_from – epig:datingFrom value
        dating_to   – epig:datingTo value
        citation  – dcterms:bibliographicCitation value
    """
    print(f"Parsing TTL file: {ttl_path}")
    g = rdflib.Graph()
    g.parse(str(ttl_path), format="turtle")
    print(f"  Loaded {len(g)} triples")

    inscriptions = []

    for subj in g.subjects(RDF.type, EPIG.Inscription):
        # EDCS-ID (dcterms:identifier)
        edcs_id = str(g.value(subj, DCTERMS.identifier) or "")

        # rdfs:comment
        comment = str(g.value(subj, RDFS.comment) or "")

        # Skip inscriptions without a comment
        if not comment:
            continue

        # epig:text
        text = str(g.value(subj, EPIG.text) or "")

        # place (local name of URI)
        place_uri = g.value(subj, EPIG.place)
        place = _local_name(place_uri) if place_uri else ""

        # province (local name of URI)
        province_uri = g.value(subj, EPIG.province)
        province = _local_name(province_uri) if province_uri else ""

        # Pleiades ID
        pleiades = str(g.value(subj, EPIG.pleiadesId) or "")

        # Dating
        dating_from = g.value(subj, EPIG.datingFrom)
        dating_to = g.value(subj, EPIG.datingTo)
        dating_from = int(dating_from) if dating_from is not None else None
        dating_to = int(dating_to) if dating_to is not None else None

        # Bibliographic citation
        citation = str(g.value(subj, DCTERMS.bibliographicCitation) or "")

        inscriptions.append({
            "id": edcs_id,
            "comment": comment,
            "text": text,
            "place": place,
            "province": province,
            "pleiades": pleiades,
            "dating_from": dating_from,
            "dating_to": dating_to,
            "citation": citation,
        })

    print(f"  Found {len(inscriptions)} inscriptions with rdfs:comment")
    return inscriptions


def _local_name(uri: URIRef) -> str:
    """Extract local name from a URI (part after last / or #)."""
    s = str(uri)
    for sep in ("#", "/"):
        if sep in s:
            return s.rsplit(sep, 1)[-1]
    return s


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
def embed_texts(texts: list[str], client: openai.OpenAI) -> list[list[float]]:
    """
    Embed a batch of texts using the OpenAI Embeddings API.

    Returns a list of float vectors (one per input text).
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [e.embedding for e in response.data]


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------
def load_progress(progress_file: Path) -> set:
    """Return a set of EDCS-IDs that have already been upserted."""
    if progress_file.exists():
        with open(progress_file, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_progress(progress_file: Path, done_ids: set):
    """Persist the set of completed EDCS-IDs to disk."""
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(sorted(done_ids), f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------
def upsert_inscriptions(
    inscriptions: list[dict],
    anthropic_client: openai.OpenAI,
    pinecone_index,
    batch_size: int,
    resume: bool,
    progress_file: Path,
    limit: int | None,
):
    """Embed and upsert all inscriptions to Pinecone in batches."""

    # Load already-processed IDs if resuming
    done_ids: set = load_progress(progress_file) if resume else set()
    if done_ids:
        print(f"Resume mode: {len(done_ids)} inscriptions already upserted, skipping.")

    # Filter to-do list
    todo = [ins for ins in inscriptions if ins["id"] not in done_ids]
    if limit:
        todo = todo[:limit]

    total = len(todo)
    print(f"Inscriptions to upsert: {total}")

    if total == 0:
        print("Nothing to do.")
        return

    # Iterate in batches
    iterator = range(0, total, batch_size)
    if TQDM_AVAILABLE:
        iterator = tqdm(iterator, desc="Upserting batches", unit="batch")

    for start in iterator:
        batch = todo[start: start + batch_size]

        texts = [ins["comment"] for ins in batch]

        # --- Embed ---
        try:
            vectors = embed_texts(texts, anthropic_client)
        except Exception as e:
            print(f"  Embedding error at batch starting {start}: {e}")
            time.sleep(5)
            continue

        # --- Build Pinecone upsert payload ---
        upsert_items = []
        for ins, vec in zip(batch, vectors):
            metadata = {
                "edcs_id":    ins["id"],
                "place":      ins["place"],
                "province":   ins["province"],
                "pleiades":   ins["pleiades"],
                "citation":   ins["citation"],
                "comment":    ins["comment"],    # store for retrieval
                "text":       ins["text"],
            }
            if ins["dating_from"] is not None:
                metadata["dating_from"] = ins["dating_from"]
            if ins["dating_to"] is not None:
                metadata["dating_to"] = ins["dating_to"]

            upsert_items.append({
                "id":       ins["id"],
                "values":   vec,
                "metadata": metadata,
            })

        # --- Upsert to Pinecone ---
        try:
            pinecone_index.upsert(vectors=upsert_items)
        except Exception as e:
            print(f"  Pinecone upsert error at batch starting {start}: {e}")
            time.sleep(5)
            continue

        # Mark as done
        for ins in batch:
            done_ids.add(ins["id"])

        # Persist progress after every batch
        save_progress(progress_file, done_ids)

        if not TQDM_AVAILABLE:
            print(f"  Upserted {min(start + batch_size, total)}/{total}")

    print(f"\nDone. Total upserted this run: {len(done_ids) - (len(inscriptions) - total - len(done_ids.intersection({ins['id'] for ins in inscriptions})))}")
    print(f"Progress saved to: {progress_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Embed rdfs:comment values from all.ttl and upsert to Pinecone"
    )
    parser.add_argument(
        "--ttl",
        type=str,
        default=str(DEFAULT_TTL),
        help=f"Path to the TTL file (default: {DEFAULT_TTL})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of inscriptions per embedding / upsert batch (default: 50)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of inscriptions to process (for testing)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip inscriptions already recorded in the progress file",
    )
    parser.add_argument(
        "--progress-file",
        type=str,
        default=str(DEFAULT_PROGRESS_FILE),
        help=f"Path to progress JSON file (default: {DEFAULT_PROGRESS_FILE})",
    )
    parser.add_argument(
        "--index-name",
        type=str,
        default=None,
        help="Pinecone index name (overrides PINECONE_INDEX_NAME env var)",
    )
    args = parser.parse_args()

    # --- API keys ---
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("Error: OPENAI_API_KEY is not set.")
        sys.exit(1)

    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    if not pinecone_api_key:
        print("Error: PINECONE_API_KEY is not set.")
        sys.exit(1)

    index_name = args.index_name or os.environ.get("PINECONE_INDEX_NAME")
    if not index_name:
        print("Error: PINECONE_INDEX_NAME is not set (env var or --index-name).")
        sys.exit(1)

    # --- Parse TTL ---
    ttl_path = Path(args.ttl)
    if not ttl_path.exists():
        print(f"Error: TTL file not found: {ttl_path}")
        sys.exit(1)

    inscriptions = parse_inscriptions(ttl_path)
    if not inscriptions:
        print("No inscriptions with rdfs:comment found.")
        sys.exit(0)

    # --- Init clients ---
    print(f"\nConnecting to OpenAI API (model: {EMBEDDING_MODEL})...")
    openai_client = openai.OpenAI(api_key=openai_api_key)

    print(f"Connecting to Pinecone index: {index_name}...")
    pc = Pinecone(api_key=pinecone_api_key)
    index = pc.Index(index_name)
    stats = index.describe_index_stats()
    print(f"  Index stats: {stats.total_vector_count} vectors currently stored")

    # --- Upsert ---
    print(f"\nBatch size : {args.batch_size}")
    if args.limit:
        print(f"Limit      : {args.limit}")
    print()

    upsert_inscriptions(
        inscriptions=inscriptions,
        anthropic_client=openai_client,
        pinecone_index=index,
        batch_size=args.batch_size,
        resume=args.resume,
        progress_file=Path(args.progress_file),
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
