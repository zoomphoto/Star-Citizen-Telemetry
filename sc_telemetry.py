"""Typed gRPC client for Star Citizen's local GameTelemetryService.

Usage:
    python sc_telemetry.py                              # Stream live telemetry (JSON)
    python sc_telemetry.py stream --max-frames 5        # Stream 5 frames and exit
    python sc_telemetry.py stream --filter actor        # Only print frames containing 'actor'
    python sc_telemetry.py stream --compact             # Single-line JSONL output
    python sc_telemetry.py actions                      # List all triggerable game actions
    python sc_telemetry.py trigger <action_name> [--hold-ms 250]
"""

import argparse
import json
import sys
from collections import defaultdict

import grpc
from google.protobuf.json_format import MessageToDict

from sc.game.telemetry.v1 import api_pb2, api_pb2_grpc

DEFAULT_TARGET = "127.0.0.1:50051"
FRAME_TYPES = ("vehicle", "weapons", "events", "actor", "force_feedback", "turret")


def cmd_stream(stub: api_pb2_grpc.GameTelemetryServiceStub, args: argparse.Namespace) -> None:
    print(f"Connecting to {args.target} (TelemetryStream)...", file=sys.stderr)
    request = api_pb2.TelemetryStreamRequest()
    count = 0

    for frame in stub.TelemetryStream(request):
        data = MessageToDict(frame, preserving_proto_field_name=True)
        if args.filter and args.filter not in data:
            continue

        count += 1
        if args.compact:
            print(json.dumps(data), flush=True)
        else:
            print(f"\n--- Frame #{count} ---")
            print(json.dumps(data, indent=2), flush=True)

        if args.max_frames and count >= args.max_frames:
            break


def cmd_actions(stub: api_pb2_grpc.GameTelemetryServiceStub, args: argparse.Namespace) -> None:
    response = stub.ListTriggerableActions(api_pb2.ListTriggerableActionsRequest())

    if args.json:
        print(json.dumps(MessageToDict(response, preserving_proto_field_name=True), indent=2))
        return

    by_category: dict[str, list[api_pb2.TriggerableAction]] = defaultdict(list)
    for action in response.actions:
        by_category[action.category or "uncategorized"].append(action)

    total = len(response.actions)
    print(f"Found {total} triggerable actions across {len(by_category)} categories:\n")
    for category in sorted(by_category):
        print(f"[{category}]")
        for action in sorted(by_category[category], key=lambda a: a.action_name):
            hold = " (holdable)" if action.holdable else ""
            print(f"  - {action.action_name}{hold}")
        print()


def cmd_trigger(stub: api_pb2_grpc.GameTelemetryServiceStub, args: argparse.Namespace) -> None:
    kwargs = {"action_name": args.action_name}
    if args.hold_ms is not None:
        kwargs["hold_ms"] = args.hold_ms

    response = stub.TriggerGameAction(api_pb2.TriggerGameActionRequest(**kwargs))
    status_name = api_pb2.TriggerGameActionStatus.Name(response.status)
    print(f"Status: {status_name}")
    if response.message:
        print(f"Message: {response.message}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Star Citizen local gRPC telemetry reader & action client."
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"gRPC server host:port (default: {DEFAULT_TARGET})",
    )

    subparsers = parser.add_subparsers(dest="command")

    p_stream = subparsers.add_parser("stream", help="Stream live telemetry frames (default)")
    p_stream.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Stop after N frames (0 = unlimited)",
    )
    p_stream.add_argument(
        "--filter",
        choices=FRAME_TYPES,
        default=None,
        help="Only print frames containing the specified section",
    )
    p_stream.add_argument(
        "--compact",
        action="store_true",
        help="Print one JSON object per line (JSONL)",
    )

    p_actions = subparsers.add_parser("actions", help="List triggerable game actions")
    p_actions.add_argument("--json", action="store_true", help="Output raw JSON")

    p_trigger = subparsers.add_parser("trigger", help="Trigger an in-game action")
    p_trigger.add_argument("action_name", help="Name of the action (see 'actions' subcommand)")
    p_trigger.add_argument("--hold-ms", type=int, default=None, help="Optional hold duration in ms")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Default to `stream` when no subcommand is given
    if args.command is None:
        args.command = "stream"
        args.max_frames = 0
        args.filter = None
        args.compact = False

    with grpc.insecure_channel(args.target) as channel:
        stub = api_pb2_grpc.GameTelemetryServiceStub(channel)
        try:
            if args.command == "stream":
                cmd_stream(stub, args)
            elif args.command == "actions":
                cmd_actions(stub, args)
            elif args.command == "trigger":
                cmd_trigger(stub, args)
        except grpc.RpcError as e:
            print(f"gRPC error [{e.code().name}]: {e.details()}", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nStopped.", file=sys.stderr)


if __name__ == "__main__":
    main()

