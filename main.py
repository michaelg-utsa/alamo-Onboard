"""AlamoOnboard entry point.

Usage:
    python main.py            # build the index if missing, then launch the UI
    python main.py --rebuild  # force a rebuild of the index from SA Utilities output
    python main.py --cli      # text-only REPL instead of Gradio

The retrieval index is built from data produced by the sibling
``sa_utilities`` package (chunks JSON + ChromaDB). See the SA Utilities
README for how to run that pipeline; once it has produced output, this
project consumes it automatically.
"""

from __future__ import annotations

import argparse
import sys

from config import banner
from src.indexer.retriever import HybridRetriever
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def cmd_build_index(rebuild: bool) -> None:
    """Build (or reload) the FAISS + BM25 retrieval index.

    Parameters
    ----------
    rebuild : bool
        When True, ignore any existing on-disk index and rebuild from the
        SA Utilities pipeline output.
    """
    retriever = HybridRetriever()
    if not rebuild and retriever.load():
        logger.info("loaded existing index from disk")
        return
    logger.info("building index from SA Utilities pipeline output...")
    retriever.build_from_sa_utilities()
    logger.info("index build complete")


def cmd_run_ui() -> None:
    from src.ui.gradio_app import main as ui_main

    ui_main()


def cmd_run_cli() -> None:
    from src.agent.orchestrator import AlamoAgent

    agent = AlamoAgent()
    print(banner())  # noqa: T201 — intentional CLI output
    print("AlamoOnboard CLI - type 'quit' to exit.\n")  # noqa: T201
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()  # noqa: T201
            return
        if user.lower() in ("quit", "exit"):
            return
        reply = agent.handle_user_message(user)
        print(f"\nassistant> {reply.text}\n")  # noqa: T201


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AlamoOnboard - San Antonio move-in concierge"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="rebuild the index from SA Utilities pipeline output",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="launch text-only REPL instead of Gradio",
    )
    args = parser.parse_args()

    cmd_build_index(rebuild=args.rebuild)
    if args.cli:
        cmd_run_cli()
    else:
        cmd_run_ui()


if __name__ == "__main__":
    sys.exit(main())
