"""Minimal raw wire-format Star Citizen gRPC telemetry reader (no compiled .proto stubs required)."""

import argparse
import json
import struct
import grpc

DEFAULT_TARGET = "127.0.0.1:50051"
METHOD = "/sc.game.telemetry.v1.GameTelemetryService/TelemetryStream"


def decode_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def decode_proto_wire(buf: bytes, field_names: dict[int, str] | None = None) -> dict:
    """Minimal Protobuf wire-format decoder for inspecting unknown/uncompiled messages."""
    pos = 0
    out: dict = {}
    n = len(buf)
    while pos < n:
        tag, pos = decode_varint(buf, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07
        key = (
            field_names.get(field_num, f"field_{field_num}")
            if field_names
            else f"field_{field_num}"
        )

        if wire_type == 0:  # Varint (int, bool, enum)
            val, pos = decode_varint(buf, pos)
        elif wire_type == 1:  # 64-bit (double / fixed64)
            val = struct.unpack("<d", buf[pos : pos + 8])[0]
            pos += 8
        elif wire_type == 2:  # Length-delimited (nested message, string, or bytes)
            length, pos = decode_varint(buf, pos)
            chunk = buf[pos : pos + length]
            pos += length
            try:
                nested = decode_proto_wire(chunk)
                val = nested if nested else chunk.decode("utf-8")
            except Exception:
                try:
                    val = chunk.decode("utf-8")
                except UnicodeDecodeError:
                    val = chunk.hex()
        elif wire_type == 5:  # 32-bit (float / fixed32)
            val = round(struct.unpack("<f", buf[pos : pos + 4])[0], 4)
            pos += 4
        else:
            raise ValueError(f"Unsupported wire type {wire_type}")

        if key in out:
            if not isinstance(out[key], list):
                out[key] = [out[key]]
            out[key].append(val)
        else:
            out[key] = val
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Raw wire-format Star Citizen telemetry reader.")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="gRPC host:port")
    args = parser.parse_args()

    channel = grpc.insecure_channel(args.target)
    telemetry_stream = channel.unary_stream(
        METHOD,
        request_serializer=lambda x: x,
        response_deserializer=lambda x: x,
    )

    print(f"Connecting to {args.target} ({METHOD})...")
    try:
        for i, raw_frame in enumerate(telemetry_stream(b""), start=1):
            try:
                decoded = decode_proto_wire(raw_frame)
                print(f"\n--- Frame #{i} ({len(raw_frame)} bytes) ---")
                print(json.dumps(decoded, indent=2))
            except Exception as e:
                print(f"\n--- Frame #{i} ({len(raw_frame)} bytes) [raw hex, decode err: {e}] ---")
                print(raw_frame.hex())
    except grpc.RpcError as e:
        print(f"gRPC error [{e.code().name}]: {e.details()}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        channel.close()


if __name__ == "__main__":
    main()

