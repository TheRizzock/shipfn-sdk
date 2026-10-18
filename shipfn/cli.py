"""`shipfn manifest` and `shipfn run` are what the platform calls inside the image; `shipfn local` is for builders."""
import argparse
import json
import sys
import traceback
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shipfn")
    sub = parser.add_subparsers(dest="command", required=True)

    p_manifest = sub.add_parser("manifest", help="Print the JSON manifest of every @deploy function")
    p_manifest.add_argument("--root", default=".")

    p_run = sub.add_parser("run", help="Run one function with inputs from $SHIPFN_INPUTS")
    p_run.add_argument("entrypoint", help="module:function")
    p_run.add_argument("--root", default=".")

    p_local = sub.add_parser("local", help="Run a function by name on this machine")
    p_local.add_argument("name")
    p_local.add_argument("--root", default=".")
    p_local.add_argument("--input", "-i", action="append", default=[], metavar="KEY=VALUE",
                         help="An input value; JSON is parsed when it can be (-i days=7 -i region=NA)")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.command == "manifest":
        from shipfn.manifest import build_manifest

        print(json.dumps(build_manifest(root)))
        return 0

    if args.command == "run":
        from shipfn.runtime import run

        return run(args.entrypoint, root)

    if args.command == "local":
        from shipfn.decorator import registry
        from shipfn.manifest import build_manifest
        from shipfn.runtime import to_jsonable

        manifest = build_manifest(root)
        for err in manifest["errors"]:
            print(f"warning: {err}", file=sys.stderr)
        if args.name not in registry:
            print(f"No function named '{args.name}'. Found: {', '.join(sorted(registry)) or 'none'}", file=sys.stderr)
            return 1
        inputs = {}
        for pair in args.input:
            key, _, raw = pair.partition("=")
            try:
                inputs[key] = json.loads(raw)
            except json.JSONDecodeError:
                inputs[key] = raw
        # Same validation as the platform, but print the result for a person instead of the marker line
        try:
            result = to_jsonable(registry[args.name].call(inputs))
        except Exception:
            traceback.print_exc()
            return 1
        if result is not None:
            print(result if isinstance(result, str) else json.dumps(result, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
