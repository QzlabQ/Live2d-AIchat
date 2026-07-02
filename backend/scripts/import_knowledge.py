from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.db.session import AsyncSessionFactory, init_db, shutdown_db
from app.services.knowledge_base import KnowledgeDependencyError, KnowledgeImporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Phase 1 scenic knowledge into ChromaDB.")
    parser.add_argument(
        "--source",
        required=True,
        help="Source file or directory that contains scenic knowledge documents.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear existing knowledge_docs rows and the Chroma collection before importing.",
    )
    return parser


async def run(source: str, reset: bool) -> int:
    await init_db()
    try:
        importer = KnowledgeImporter(AsyncSessionFactory)
        try:
            report = await importer.import_source(Path(source), reset=reset)
        except KnowledgeDependencyError as exc:
            print(f"Knowledge import failed: {exc}")
            return 1
    finally:
        await shutdown_db()

    print("Knowledge import finished.")
    print(f"Imported documents: {len(report.imported)}")
    for item in report.imported:
        print(f"  - {item.filename} [{item.category}] -> {item.chunk_count} chunks")

    print(f"Skipped files: {len(report.skipped)}")
    for filename, reason in report.skipped:
        print(f"  - {filename}: {reason}")

    print(f"Errors: {len(report.errors)}")
    for filename, reason in report.errors:
        print(f"  - {filename}: {reason}")

    print(f"Chroma collection count: {report.collection_count}")
    return 1 if report.errors else 0


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(run(args.source, args.reset)))


if __name__ == "__main__":
    main()
