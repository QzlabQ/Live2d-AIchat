import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reranker-engine", required=True)
    parser.add_argument("--log-name", required=True)
    args = parser.parse_args()

    root = Path.cwd()
    log_path = root / "logs" / args.log_name
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["RAG_RERANKER_ENGINE"] = args.reranker_engine

    cmd = [
        sys.executable,
        "-m",
        "scripts.evaluate_rag",
        "--dataset",
        str(root / "evals" / "phase2_rag_eval.50.jsonl"),
        "--target",
        "0",
    ]

    proc = subprocess.run(
        cmd,
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    log_path.write_text(proc.stdout, encoding="utf-8")

    print(f"returncode = {proc.returncode}")
    print(f"log_path = {log_path}")
    for line in proc.stdout.splitlines()[-12:]:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
