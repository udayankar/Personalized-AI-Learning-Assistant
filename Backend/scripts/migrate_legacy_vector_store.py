"""Deprecated FAISS migration command.

Old MiniLM vectors are incompatible with Gemini embeddings. This project has
no need to preserve its development-only vectors. Re-upload PDFs to produce
Gemini embeddings and pgvector rows; existing files are never changed here.
"""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--trusted-local-files", action="store_true")
    parser.parse_args()
    raise SystemExit(
        "FAISS migration is unsupported because MiniLM embeddings cannot be reused. Re-upload source PDFs."
    )


if __name__ == "__main__":
    main()
