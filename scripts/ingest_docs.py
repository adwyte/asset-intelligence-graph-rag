# scripts/ingest_docs.py
import argparse
from backend.ingestion.docs_ingestor import ingest_docs_for_root


def main():
    parser = argparse.ArgumentParser(description="Ingest docs for parts")
    parser.add_argument("--root", required=True, help="Root folder for part docs")
    args = parser.parse_args()

    ingest_docs_for_root(args.root)


if __name__ == "__main__":
    main()
