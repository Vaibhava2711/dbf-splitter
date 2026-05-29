"""
dbf_engine.py
-------------
Core DBF splitting engine used by both CAMS and Karvy modes.
Works with any DBF file regardless of number of fields.
"""

import os
import shutil
import zipfile
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
    One output DBF per row. Output filename = AMC code (column 1) for that row.
    If multiple rows share the same AMC code, suffixes _2, _3 ... are appended
    so no file is ever overwritten.
    Works with any number of fields — full original header preserved.
    Yields SplitResult for each row processed.
    """
    header = read_dbf_header(input_file)
    out_header = _make_output_header(header, 1)

    os.makedirs(output_dir, exist_ok=True)

    # Track how many times each AMC code has been seen this run
    amc_counts: dict = {}

    # AMC code is always field 1 — offset 1 (skip delete flag), length = fields[0][2]
    amc_offset = 1
    amc_length = header.fields[0][2] if header.fields else 0

    with open(input_file, "rb") as f:
        f.seek(header.header_len)
        row_index = 0

        while True:
            record = f.read(header.record_len)
            if not record or len(record) < header.record_len or record[0] == 0x1A:
                break

            # Read AMC code from column 1
            raw_amc = record[amc_offset: amc_offset + amc_length]
            amc_code = raw_amc.decode("ascii", errors="ignore").strip()
            if not amc_code:
                amc_code = f"row_{row_index + 1}"

            amc_code = _sanitize_filename(amc_code)

            # First occurrence = no suffix, subsequent = _2, _3 ...
            count = amc_counts.get(amc_code, 0) + 1
            amc_counts[amc_code] = count

            if count == 1:
                filename = f"{amc_code}.dbf"
            else:
                filename = f"{amc_code}_{count}.dbf"

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
                    field_value=amc_code,
                )
            except Exception as e:
                yield SplitResult(
                    success=False,
                    output_file=out_path,
                    row_index=row_index,
                    field_value=amc_code,
                    error=str(e),
                )

            row_index += 1
            if progress_callback:
                progress_callback(row_index, header.num_records)


@dataclass
class ZipResult:
    success: bool
    zip_file: str
    name: str
    error: str = ""


def create_cams_zips(
    split_results: list,
    tiff_source: str,
    output_dir: str = ".",
    progress_callback=None,
) -> Generator[ZipResult, None, None]:
    """
    CAMS zip creation.
    For each SplitResult, creates:
      <output_dir>/<name>.zip
        └── <name>/
              └── <name>.tiff   (copied from tiff_source)

    split_results : list of SplitResult from split_cams()
    tiff_source   : path to the single master TIFF file
    Yields ZipResult for each zip created.
    """
    if not os.path.exists(tiff_source):
        raise FileNotFoundError(f"TIFF file not found: {tiff_source}")

    tiff_ext = os.path.splitext(tiff_source)[1]   # preserve .tiff or .tif

    total = len(split_results)
    for idx, result in enumerate(split_results):
        name = os.path.splitext(os.path.basename(result.output_file))[0]
        zip_path = os.path.join(output_dir, f"{name}.zip")

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # folder/file path inside the zip
                inner_tiff = f"{name}/{name}{tiff_ext}"
                zf.write(tiff_source, inner_tiff)

            yield ZipResult(success=True, zip_file=zip_path, name=name)

        except Exception as e:
            yield ZipResult(success=False, zip_file=zip_path, name=name, error=str(e))

        if progress_callback:
            progress_callback(idx + 1, total)


def create_karvy_zips(
    split_results: list,
    ref_numbers: list,
    folio_numbers: list,
    tiff_source: str,
    output_dir: str = ".",
    progress_callback=None,
) -> Generator[ZipResult, None, None]:
    """
    Karvy zip creation.
    For each split DBF, creates:
      <output_dir>/<ref_number>.zip
        └── <ref_number>/
              └── <folio_number>.tiff   (copied from tiff_source)

    split_results : list of SplitResult from split_karvy()
    ref_numbers   : list of strings, one per row — used as zip name and folder name
    folio_numbers : list of strings, one per row — used as tiff filename inside folder
    tiff_source   : path to the single master TIFF file

    Raises ValueError if counts don't match.
    Yields ZipResult for each zip created.
    """
    if not os.path.exists(tiff_source):
        raise FileNotFoundError(f"TIFF file not found: {tiff_source}")

    n_splits = len(split_results)
    n_refs   = len(ref_numbers)
    n_folios = len(folio_numbers)

    if n_refs != n_splits:
        raise ValueError(
            f"Ref number count ({n_refs}) does not match "
            f"number of split DBFs ({n_splits})."
        )
    if n_folios != n_splits:
        raise ValueError(
            f"Folio number count ({n_folios}) does not match "
            f"number of split DBFs ({n_splits})."
        )

    tiff_ext = os.path.splitext(tiff_source)[1]   # preserve .tiff or .tif

    for idx, (result, ref, folio) in enumerate(
            zip(split_results, ref_numbers, folio_numbers)):

        # Sanitize ref for use as filename/folder
        safe_ref = ref.strip()
        for ch in r'<>:"/\\|?*':
            safe_ref = safe_ref.replace(ch, "")
        safe_ref = safe_ref.strip(". ") or f"ref_{idx + 1}"

        safe_folio = folio.strip()
        for ch in r'<>:"/\\|?*':
            safe_folio = safe_folio.replace(ch, "")
        safe_folio = safe_folio.strip(". ") or f"folio_{idx + 1}"

        zip_path = os.path.join(output_dir, f"{safe_ref}.zip")

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                inner_tiff = f"{safe_ref}/{safe_folio}{tiff_ext}"
                zf.write(tiff_source, inner_tiff)

            yield ZipResult(success=True, zip_file=zip_path, name=safe_ref)

        except Exception as e:
            yield ZipResult(success=False, zip_file=zip_path, name=safe_ref, error=str(e))

        if progress_callback:
            progress_callback(idx + 1, n_splits)
