"""Legacy filesystem document backfill command.

Document chunks and embeddings are now stored in PostgreSQL. Development data
was explicitly classified as disposable, so this tool intentionally does not
import old filesystem catalogs or FAISS vectors. Re-upload PDFs that need to be
used with the current schema.
"""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raise SystemExit(
        "Filesystem backfill is no longer supported. Upload PDFs through the application to create pgvector chunks."
    )


if __name__ == "__main__":
    main()
