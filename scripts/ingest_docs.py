"""
Document Ingestion Script

Team implements: Doc → chunks → embeddings → FAISS index

Usage:
    python scripts/ingest_docs.py --source data/docs/ --type pdf
    
TODO: Phase 1 implementation
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into vector index")
    parser.add_argument("--source", required=True, help="Path to document(s)")
    parser.add_argument("--type", default="text", choices=["pdf", "word", "text", "web", "swagger"])
    args = parser.parse_args()
    
    print(f"TODO: Ingest {args.type} from {args.source}")
    print("See apps/backend/tools/doc_search/README.md for implementation guide")


if __name__ == "__main__":
    main()
