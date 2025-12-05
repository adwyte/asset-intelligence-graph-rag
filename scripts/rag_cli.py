# scripts/rag_cli.py
import argparse

from backend.rag.retrieval import retrieve_context
from backend.rag.synthesis import synthesize_answer


def main():
    parser = argparse.ArgumentParser(description="Graph-RAG CLI")
    parser.add_argument("--question", required=True, help="Your question")
    parser.add_argument("--k_parts", type=int, default=5)
    args = parser.parse_args()

    ctx = retrieve_context(args.question, k_parts=args.k_parts)
    answer = synthesize_answer(args.question, ctx)

    print("=== Answer ===")
    print(answer)
    print("\n=== Raw Context ===")
    print(ctx)


if __name__ == "__main__":
    main()
