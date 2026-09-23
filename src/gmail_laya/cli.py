"""Command-line entry point."""

import argparse
import gc
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .classifier import classify, group_by_model
from .gmail import create_service, iter_messages
from .parser import parse_message


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify Gmail messages locally with Laya")
    parser.add_argument("--query", default="in:inbox", help="Gmail search query")
    parser.add_argument("--max-messages", type=int, default=20)
    parser.add_argument("--credentials", type=Path, default=Path("credentials.json"))
    parser.add_argument("--token", type=Path, default=Path("token.json"))
    parser.add_argument("--output", type=Path, default=Path("data/classifications.json"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto",
                        help="Laya inference device (default: auto)")
    parser.add_argument("--max-loaded-models", type=int, choices=(1, 2), default=None,
                        help="Models kept in memory (default: 1 on CUDA, 2 on CPU)")
    args = parser.parse_args(argv)
    if args.max_messages < 1:
        parser.error("--max-messages must be at least 1")

    try:
        import torch

        cuda_available = torch.cuda.is_available()
        if args.device == "cuda" and not cuda_available:
            raise RuntimeError("CUDA unavailable in this PyTorch installation. Install a CUDA build or use --device cpu.")
        device = "cuda" if args.device == "auto" and cuda_available else (
            "cpu" if args.device == "auto" else args.device
        )
        max_loaded = args.max_loaded_models or (1 if device == "cuda" else 2)
        print(f"Laya device: {device}; models kept in memory: {max_loaded}", flush=True)
        started = perf_counter()
        service = create_service(args.credentials, args.token)
        print(f"Gmail OAuth ready in {perf_counter() - started:.1f}s", flush=True)
        def on_fetch(message_id, elapsed):
            print(f"Gmail fetched {message_id} in {elapsed:.1f}s", flush=True)

        def on_list(elapsed, count):
            print(f"Gmail listed {count} messages in {elapsed:.1f}s", flush=True)

        emails = [parse_message(raw) for raw in iter_messages(
            service, args.query, args.max_messages, on_fetch=on_fetch, on_list=on_list
        )]
        print(f"Gmail fetch complete: {len(emails)} emails. Starting Laya analysis...", flush=True)

        records = [None] * len(emails)
        if emails:
            import laya

            router = laya.Router(device=device, max_loaded=max_loaded)
            work = group_by_model(emails, router, laya)
        else:
            work = []
        active_model = None
        agent = None
        for completed, (model, index, email) in enumerate(work, 1):
            if model != active_model:
                if active_model and max_loaded == 1:
                    router.unload(active_model)
                    agent = None
                    gc.collect()
                    if device == "cuda":
                        torch.cuda.empty_cache()
                print(f"Loading Laya model: {model}...", flush=True)
                load_started = perf_counter()
                agent = router.load(model)
                print(f"Laya model {model} ready on {agent.device} in "
                      f"{perf_counter() - load_started:.1f}s", flush=True)
                active_model = model
            started = perf_counter()
            record = classify(email, router=router, laya_module=laya)
            laya_elapsed = perf_counter() - started
            records[index] = record
            c = record["classification"]
            print(f"Laya {completed}/{len(work)} | {c['category']} ({c['confidence']}) | "
                  f"{laya_elapsed:.1f}s | {record['subject']}", flush=True)
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "query": args.query,
            "count": len(records),
            "messages": records,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {len(records)} results to {args.output}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
