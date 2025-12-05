# scripts/compat.py
import argparse
from backend.compatibility.scoring import compute_compatibility_for_product


def main():
    parser = argparse.ArgumentParser(description="Compute compatibility for a product")
    parser.add_argument("--product", required=True, help="Product name in Neo4j")
    args = parser.parse_args()

    compute_compatibility_for_product(args.product)


if __name__ == "__main__":
    main()
