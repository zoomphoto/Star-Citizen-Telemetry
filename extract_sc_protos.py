"""Extract embedded Protobuf FileDescriptorProto definitions for sc.game.telemetry.v1
from StarCitizen.exe and reconstruct clean .proto files.
"""

import argparse
import re
from pathlib import Path
from google.protobuf import descriptor_pb2

DEFAULT_EXE_PATH = r"D:\StarCitizen\StarCitizen\PTU\Bin64\StarCitizen.exe"
DEFAULT_OUT_DIR = Path("sc_protos")
PREFIX = b"sc/game/telemetry/v1/"

# Valid (field_number: expected_wire_types) for google.protobuf.FileDescriptorProto
FDP_FIELDS = {
    1: {2},     # name (string)
    2: {2},     # package (string)
    3: {2},     # dependency (string)
    4: {2},     # message_type (DescriptorProto)
    5: {2},     # enum_type (EnumDescriptorProto)
    6: {2},     # service (ServiceDescriptorProto)
    7: {2},     # extension (FieldDescriptorProto)
    8: {2},     # options (FileOptions)
    9: {2},     # source_code_info (SourceCodeInfo)
    10: {0, 2}, # public_dependency (int32 / packed)
    11: {0, 2}, # weak_dependency (int32 / packed)
    12: {2},    # syntax (string)
    14: {0},    # edition (enum)
}

TYPE_MAP = {
    1: "double",
    2: "float",
    3: "int64",
    4: "uint64",
    5: "int32",
    6: "fixed64",
    7: "fixed32",
    8: "bool",
    9: "string",
    12: "bytes",
    13: "uint32",
    15: "sfixed32",
    16: "sfixed64",
    17: "sint32",
    18: "sint64",
}


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result, shift = 0, 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("Varint overflow")
    raise ValueError("Truncated varint")


def extract_fdp_blob(data: bytes, start: int) -> bytes:
    """Walk valid top-level FileDescriptorProto fields from `start` until the descriptor ends."""
    pos = start
    end_valid = start
    n = len(data)
    while pos < n:
        try:
            tag, pos = read_varint(data, pos)
        except ValueError:
            break
        field_num = tag >> 3
        wire_type = tag & 0x07
        if field_num not in FDP_FIELDS or wire_type not in FDP_FIELDS[field_num]:
            break
        try:
            if wire_type == 0:
                _, pos = read_varint(data, pos)
            elif wire_type == 2:
                length, pos = read_varint(data, pos)
                if length < 0 or pos + length > n:
                    break
                pos += length
        except ValueError:
            break
        end_valid = pos
        if field_num == 12:
            continue
    return data[start:end_valid]


def format_enum(enum: descriptor_pb2.EnumDescriptorProto, indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines = [f"{pad}enum {enum.name} {{"]
    for val in enum.value:
        lines.append(f"{pad}  {val.name} = {val.number};")
    lines.append(f"{pad}}}")
    return lines


def format_field(field: descriptor_pb2.FieldDescriptorProto, is_proto3: bool) -> str:
    label = ""
    if field.label == descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED:
        label = "repeated "
    elif getattr(field, "proto3_optional", False):
        label = "optional "
    elif not is_proto3 and field.label == descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL:
        label = "optional "
    elif field.label == descriptor_pb2.FieldDescriptorProto.LABEL_REQUIRED:
        label = "required "

    if field.type in (11, 14):  # MESSAGE or ENUM
        ftype = field.type_name.lstrip(".")
    else:
        ftype = TYPE_MAP.get(field.type, f"unknown_{field.type}")

    return f"{label}{ftype} {field.name} = {field.number};"


def format_message(
    msg: descriptor_pb2.DescriptorProto, is_proto3: bool, indent: int = 0
) -> list[str]:
    pad = "  " * indent
    lines = [f"{pad}message {msg.name} {{"]

    for nested_enum in msg.enum_type:
        lines.extend(format_enum(nested_enum, indent + 1))
        lines.append("")

    for nested_msg in msg.nested_type:
        if nested_msg.options.map_entry:
            continue
        lines.extend(format_message(nested_msg, is_proto3, indent + 1))
        lines.append("")

    # Group real oneofs (skip synthetic oneofs generated for proto3 optional fields)
    oneof_fields: dict[int, list[descriptor_pb2.FieldDescriptorProto]] = {}
    regular_fields: list[descriptor_pb2.FieldDescriptorProto] = []
    for f in msg.field:
        if f.HasField("oneof_index") and not getattr(f, "proto3_optional", False):
            oneof_fields.setdefault(f.oneof_index, []).append(f)
        else:
            regular_fields.append(f)

    for f in regular_fields:
        lines.append(f"{pad}  {format_field(f, is_proto3)}")

    for idx, fields in oneof_fields.items():
        oneof_name = msg.oneof_decl[idx].name
        lines.append(f"{pad}  oneof {oneof_name} {{")
        for f in fields:
            lines.append(f"{pad}    {format_field(f, is_proto3)}")
        lines.append(f"{pad}  }}")

    lines.append(f"{pad}}}")
    return lines


def format_service(svc: descriptor_pb2.ServiceDescriptorProto) -> list[str]:
    lines = [f"service {svc.name} {{"]
    for m in svc.method:
        c_stream = "stream " if m.client_streaming else ""
        s_stream = "stream " if m.server_streaming else ""
        in_type = m.input_type.lstrip(".")
        out_type = m.output_type.lstrip(".")
        lines.append(f"  rpc {m.name} ({c_stream}{in_type}) returns ({s_stream}{out_type});")
    lines.append("}")
    return lines


def render_proto(fdp: descriptor_pb2.FileDescriptorProto) -> str:
    is_proto3 = fdp.syntax == "proto3"
    lines = [f'syntax = "{fdp.syntax or "proto2"}";', ""]
    if fdp.package:
        lines.append(f"package {fdp.package};")
        lines.append("")
    for dep in fdp.dependency:
        lines.append(f'import "{dep}";')
    if fdp.dependency:
        lines.append("")
    for enum in fdp.enum_type:
        lines.extend(format_enum(enum))
        lines.append("")
    for msg in fdp.message_type:
        lines.extend(format_message(msg, is_proto3))
        lines.append("")
    for svc in fdp.service:
        lines.extend(format_service(svc))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Star Citizen telemetry .proto files.")
    parser.add_argument("--exe", default=DEFAULT_EXE_PATH, help="Path to StarCitizen.exe")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="Output directory")
    args = parser.parse_args()

    print(f"Reading {args.exe}...")
    data = Path(args.exe).read_bytes()

    # Match field 1 (0x0A) + 1-byte length + "sc/game/telemetry/v1/<name>.proto"
    pattern = re.compile(rb"\x0a(.)(" + re.escape(PREFIX) + rb"[a-zA-Z0-9_/\-]+\.proto)")
    seen: set[str] = set()

    for match in pattern.finditer(data):
        name_len = match.group(1)[0]
        proto_name = match.group(2)
        if len(proto_name) != name_len:
            continue
        proto_path_str = proto_name.decode("ascii")
        if proto_path_str in seen:
            continue

        blob = extract_fdp_blob(data, match.start())
        fdp = descriptor_pb2.FileDescriptorProto()
        try:
            fdp.ParseFromString(blob)
        except Exception as e:
            print(f"[!] Failed to parse {proto_path_str}: {e}")
            continue

        if fdp.name != proto_path_str:
            continue

        seen.add(proto_path_str)
        out_file = args.out / proto_path_str
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(render_proto(fdp), encoding="utf-8")
        print(
            f"[+] Extracted {out_file} "
            f"({len(blob)} bytes, {len(fdp.message_type)} messages, {len(fdp.service)} services)"
        )

    if not seen:
        print("No matching FileDescriptorProto blobs found.")


if __name__ == "__main__":
    main()

