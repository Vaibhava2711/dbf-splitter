"""
cli.py  —  Command-line interface for DBF Splitter
Usage:
  python cli.py info  MYFILE.dbf
  python cli.py cams  NFT.dbf   --field 77 --out ./output
  python cli.py karvy KARVY.dbf --start 1  --prefix "row_" --out ./output
"""

import argparse
import os
import sys
from dbf_engine import read_dbf_header, split_cams, split_karvy


def cmd_info(args):
    path = args.file
    if not os.path.exists(path):
        print(f"ERROR: file not found - {path}", file=sys.stderr)
        sys.exit(1)

    hdr = read_dbf_header(path)
    print(f"\n{'─'*52}")
    print(f"  File   : {os.path.basename(path)}")
    print(f"  Records: {hdr.num_records}")
    print(f"  Fields : {len(hdr.fields)}")
    print(f"  Header : {hdr.header_len} bytes  |  Record: {hdr.record_len} bytes")
    print(f"{'─'*52}")
    print(f"  {'#':>4}  {'Name':<14}  {'Type':^4}  {'Len':>4}  {'Dec':>4}")
    print(f"{'─'*52}")
    for i, (name, ftype, flen, fdec) in enumerate(hdr.fields, 1):
        print(f"  {i:>4}  {name:<14}  {ftype:^4}  {flen:>4}  {fdec:>4}")
    print(f"{'─'*52}\n")


def cmd_cams(args):
    if not os.path.exists(args.file):
        print(f"ERROR: file not found - {args.file}", file=sys.stderr)
        sys.exit(1)

    hdr = read_dbf_header(args.file)
    print(f"CAMS mode  |  {len(hdr.fields)} fields  |  {hdr.num_records} records")
    print(f"Naming by field {args.field}  ({hdr.fields[args.field-1][0]})")
    print(f"Output -> {args.out}\n")

    ok = err = 0
    for res in split_cams(args.file, args.field, args.out):
        if res.success:
            ok += 1
            print(f"  OK  {os.path.basename(res.output_file)}")
        else:
            err += 1
            print(f"  ERR Row {res.row_index}: {res.error}", file=sys.stderr)

    print(f"\nDone. {ok} created, {err} error(s).")


def cmd_karvy(args):
    if not os.path.exists(args.file):
        print(f"ERROR: file not found - {args.file}", file=sys.stderr)
        sys.exit(1)

    hdr = read_dbf_header(args.file)
    print(f"Karvy mode  |  {len(hdr.fields)} fields  |  {hdr.num_records} records")
    print(f"Naming: {args.prefix or ''}<n>.dbf  starting at {args.start}")
    print(f"Output -> {args.out}\n")

    ok = err = 0
    for res in split_karvy(args.file, args.out, args.start, args.prefix or ""):
        if res.success:
            ok += 1
            print(f"  OK  {os.path.basename(res.output_file)}")
        else:
            err += 1
            print(f"  ERR Row {res.row_index}: {res.error}", file=sys.stderr)

    print(f"\nDone. {ok} created, {err} error(s).")


def main():
    parser = argparse.ArgumentParser(
        description="DBF Splitter - split a DBF file into one file per row.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="Show field structure of a DBF file")
    p_info.add_argument("file", help="Path to DBF file")

    p_cams = sub.add_parser("cams", help="CAMS mode: name output by field value")
    p_cams.add_argument("file")
    p_cams.add_argument("--field", "-f", type=int, default=77,
                        help="Field number whose value becomes the filename (default: 77)")
    p_cams.add_argument("--out", "-o", default="output",
                        help="Output directory (default: ./output)")

    p_karvy = sub.add_parser("karvy", help="Karvy mode: name output sequentially")
    p_karvy.add_argument("file")
    p_karvy.add_argument("--start", "-s", type=int, default=1,
                         help="Starting number (default: 1)")
    p_karvy.add_argument("--prefix", "-p", default="",
                         help='Filename prefix e.g. "row_" gives row_1.dbf')
    p_karvy.add_argument("--out", "-o", default="output",
                         help="Output directory (default: ./output)")

    args = parser.parse_args()
    {"info": cmd_info, "cams": cmd_cams, "karvy": cmd_karvy}[args.command](args)


if __name__ == "__main__":
    main()
