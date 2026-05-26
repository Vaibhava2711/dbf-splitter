"""
dbf_engine.py
-------------
Core DBF splitting engine used by both CAMS and Karvy modes.
Works with any DBF file regardless of number of fields.
"""

import os
from dataclasses import dataclass, field
from typing import Generator


@dataclass
class DBFHeader:
    version: int
    num_records: int
    header_len: int
    record_len: int
    raw: bytearray
    fields: list = field(default_factory=list)   # list of (name, type, length, decimal)


@dataclass
class SplitResult:
    success: bool
    output_file: str
    row_index: int
    field_value: str = ""
    error: str = ""


def read_dbf_header(filepath: str) -> DBFHeader:
    """
    Read and parse a DBF file header.
    Returns a DBFHeader with all field descriptors resolved.
    Works with any number of fields.
    """
    with open(filepath, "rb") as f:
        core = f.read(32)
        if len(core) < 32:
            raise ValueError("File too small — not a valid DBF.")

        version      = core[0]
        num_records  = int.from_bytes(core[4:8],  byteorder="little")
        header_len   = int.from_bytes(core[8:10], byteorder="little")
        record_len   = int.from_bytes(core[10:12], byteorder="little")

        f.seek(0)
        raw_header = bytearray(f.read(header_len))

        fields = []
        offset = 32
        while offset + 32 <= header_len:
            chunk = raw_header[offset: offset + 32]
            if chunk[0] == 0x0D:          # Header terminator
                break
            name    = chunk[0:11].split(b'\x00')[0].decode("ascii", errors="ignore").strip()
            ftype   = chr(chunk[11])
            flength = chunk[16]
            fdec    = chunk[17]
            fields.append((name, ftype, flength, fdec))
            offset += 32

    return DBFHeader(
        version=version,
        num_records=num_records,
        header_len=header_len,
        record_len=record_len,
        raw=raw_header,
        fields=fields,
    )


def field_offset_in_record(header: DBFHeader, field_number: int) -> tuple:
    """
    Return (byte_offset, byte_length) of field_number (1-based) inside a record.
    Offset starts at 1 because byte 0 is the delete flag.
    """
    if field_number < 1 or field_number > len(header.fields):
        raise ValueError(
            f"Field number {field_number} is out of range "
            f"(file has {len(header.fields)} fields)."
        )
    offset = 1   # skip delete-flag byte
    for i in range(field_number - 1):
        offset += header.fields[i][2]   # add length of each preceding field
    length = header.fields[field_number - 1][2]
    return offset, length


def _make_output_header(header: DBFHeader, record_count: int = 1) -> bytearray:
    """Return a copy of the header with record count patched."""
    out = bytearray(header.raw)
    out[4:8] = record_count.to_bytes(4, byteorder="little")
    return out


def _sanitize_filename(name: str) -> str:
    """Strip characters Windows/Linux disallow in filenames."""
    for ch in r'<>:"/\\|?*':
        name = name.replace(ch, "")
    name = name.strip(". ")
    return name or "unnamed"


def split_cams(
    input_file: str,
    name_field_number: int,
    output_dir: str = ".",
    progress_callback=None,
) -> Generator[SplitResult, None, None]:
    """
    CAMS mode.
    One output DBF per row. Output filename = value of field name_field_number.
    Works with any number of fields — auto-detected from the file.
    Yields SplitResult for each row processed.
    """
    header = read_dbf_header(input_file)
    fld_offset, fld_length = field_offset_in_record(header, name_field_number)
    out_header = _make_output_header(header, 1)

    os.makedirs(output_dir, exist_ok=True)

    with open(input_file, "rb") as f:
        f.seek(header.header_len)
        row_index = 0

        while True:
            record = f.read(header.record_len)
            if not record or len(record) < header.record_len or record[0] == 0x1A:
                break

            raw_val = record[fld_offset: fld_offset + fld_length]
            clean_val = raw_val.decode("ascii", errors="ignore").strip()
            if not clean_val:
                clean_val = f"row_{row_index + 1}"

            filename = _sanitize_filename(clean_val) + ".dbf"
            out_path = os.path.join(output_dir, filename)

            try:
                with open(out_path, "wb") as out:
                    out.write(out_header)
                    out.write(record)
                    out.write(b"\x1A")
                yield SplitResult(
                    success=True,
                    output_file=out_path,
                    row_index=row_index,
                    field_value=clean_val,
                )
            except Exception as e:
                yield SplitResult(
                    success=False,
                    output_file=out_path,
                    row_index=row_index,
                    field_value=clean_val,
                    error=str(e),
                )

            row_index += 1
            if progress_callback:
                progress_callback(row_index, header.num_records)


def split_karvy(
    input_file: str,
    output_dir: str = ".",
    start_index: int = 1,
    prefix: str = "",
    progress_callback=None,
) -> Generator[SplitResult, None, None]:
    """
    Karvy mode.
    One output DBF per row. Output filename = prefix + sequential number.
    Works with any number of fields — full original header preserved.
    Yields SplitResult for each row processed.
    """
    header = read_dbf_header(input_file)
    out_header = _make_output_header(header, 1)

    os.makedirs(output_dir, exist_ok=True)

    with open(input_file, "rb") as f:
        f.seek(header.header_len)
        row_index = 0

        while True:
            record = f.read(header.record_len)
            if not record or len(record) < header.record_len or record[0] == 0x1A:
                break

            seq = start_index + row_index
            filename = f"{prefix}{seq}.dbf"
            out_path = os.path.join(output_dir, filename)

            try:
                with open(out_path, "wb") as out:
                    out.write(out_header)
                    out.write(record)
                    out.write(b"\x1A")
                yield SplitResult(
                    success=True,
                    output_file=out_path,
                    row_index=row_index,
                    field_value=str(seq),
                )
            except Exception as e:
                yield SplitResult(
                    success=False,
                    output_file=out_path,
                    row_index=row_index,
                    field_value=str(seq),
                    error=str(e),
                )

            row_index += 1
            if progress_callback:
                progress_callback(row_index, header.num_records)
