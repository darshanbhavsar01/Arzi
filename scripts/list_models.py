"""List Gemini, Gemma, TTS and Live models the project can use on Vertex AI.

Usage (from the repo root): ``make models`` or
``uv run --project api python scripts/list_models.py --location asia-south1 --location global``

Read-only: it lists models and spends nothing. Requires Application Default Credentials
(``gcloud auth application-default login``) and ``GOOGLE_CLOUD_PROJECT``.
"""

import argparse
import os
import sys

from arzi.adapters.model_catalog import format_table, list_vertex_models


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument(
        "--location",
        action="append",
        help="Vertex AI location; repeatable (default: asia-south1 and global)",
    )
    args = parser.parse_args(argv)
    if not args.project:
        parser.error("set GOOGLE_CLOUD_PROJECT or pass --project")

    for location in args.location or ["asia-south1", "global"]:
        try:
            models = list_vertex_models(args.project, location)
        except Exception as exc:  # report and continue with the next location
            print(f"Vertex AI location: {location} — listing failed ({type(exc).__name__})")
            continue
        print(format_table(models, location), end="\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
