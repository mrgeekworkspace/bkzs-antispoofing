#!/usr/bin/env python3
"""
Dataset preparation helper.
Usage:
    python scripts/prepare_dataset.py --source mendeley --input data/raw/ --output data/processed/
"""
import sys, argparse
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from backend.ml.dataset_loader import load_or_generate, FEATURE_COLS, LABEL_COL
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', choices=['mendeley', 'jammertest', 'simulate'], default='simulate')
    parser.add_argument('--input', type=str, default='data/raw/')
    parser.add_argument('--output', type=str, default='data/processed/')
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {args.source} dataset from {input_dir}...")
    df = load_or_generate(input_dir, args.source)

    output_file = output_dir / f"{args.source}_features.csv"
    df.to_csv(output_file, index=False)
    print(f"Saved {len(df)} rows to {output_file}")
    print(f"Label distribution:\n{df[LABEL_COL].value_counts()}")

if __name__ == '__main__':
    main()
