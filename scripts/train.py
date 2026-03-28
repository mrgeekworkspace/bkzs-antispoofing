#!/usr/bin/env python3
"""
One-command model training script.
Usage:
    python scripts/train.py                     # simulate data
    python scripts/train.py --dataset mendeley --data-path data/raw/
    python scripts/train.py --estimators 300
"""
import sys, argparse
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from backend.config import settings
from backend.ml.trainer import train
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Train BKZS anomaly detection models")
    parser.add_argument('--dataset', choices=['simulate', 'mendeley', 'jammertest'],
                        default='simulate', help='Dataset type')
    parser.add_argument('--data-path', type=str, default=None,
                        help='Path to raw dataset directory')
    parser.add_argument('--estimators', type=int, default=150,
                        help='Number of trees in Random Forest')
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  BKZS Anti-Spoofing — Model Training")
    print(f"  Dataset: {args.dataset}")
    print(f"  RF Trees: {args.estimators}")
    print(f"{'='*50}\n")

    data_dir = Path(args.data_path) if args.data_path else settings.DATA_RAW_DIR

    result = train(settings, data_dir=data_dir, dataset_type=args.dataset,
                   n_estimators_rf=args.estimators)

    print(f"\n{'='*50}")
    print(f"  Training Complete!")
    print(f"  Accuracy:  {result['accuracy']*100:.1f}%")
    print(f"  CV F1:     {result['cv_f1_mean']*100:.1f}% +/- {result['cv_f1_std']*100:.1f}%")
    print(f"  Samples:   {result['samples_trained']} train / {result['samples_tested']} test")
    print(f"\n  Top features:")
    for feat, imp in sorted(result['feature_importance'].items(), key=lambda x: -x[1])[:5]:
        print(f"    {feat:30s} {imp:.3f}")
    print(f"{'='*50}")
    print(f"\n  Models saved to: {settings.MODEL_DIR}")
    print(f"  Now run: python -m backend.main  (or: uvicorn backend.main:app --reload)")

if __name__ == '__main__':
    main()
