"""Compare a mix against a reference and create reports and matched listening clips."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.audio_production import compare_reference, validate_options


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mix', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path, help='Mono or stereo reference audio')
    parser.add_argument('--output', required=True, type=Path, help='A new directory for reports and listening clips')
    parser.add_argument('--listen-seconds', type=float, default=30)
    args = parser.parse_args()
    try:
        validate_options(args)
        if not args.mix.is_file() or not args.reference.is_file():
            raise ValueError('Mix and reference must both exist')
        if args.output.exists():
            raise ValueError('Output directory already exists; select a new directory to preserve previous results')
        compare_reference(args.mix, args.reference, args.output, listen_seconds=args.listen_seconds)
        print(f'Report: {args.output / "comparison.md"}')
    except (ValueError, OSError, RuntimeError) as error:
        print(f'Comparison failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
