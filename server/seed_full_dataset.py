from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from import_csv import get_default_data_dir, import_all


def main() -> int:
    parser = argparse.ArgumentParser(description='Seed the full ESG dataset from CSV fixtures.')
    parser.add_argument(
        'data_dir',
        nargs='?',
        default=str(get_default_data_dir()),
        help='Directory containing the CSV fixtures. Defaults to server/fixtures when present.',
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    import_all(data_dir)
    print(f'Full dataset seeded from {data_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
