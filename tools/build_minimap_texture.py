"""Build a small, uncompressed RGBA TGA for the product minimap from its logo.

Requires Pillow. Offline antialiasing avoids sampling a 256px texture into 20px.
"""
import argparse
from pathlib import Path

from PIL import Image


def build(source: Path, destination: Path) -> None:
    with Image.open(source) as original:
        original.load()
        if original.width != original.height or original.width < 256:
            raise ValueError("Use the square original logo, at least 256 pixels wide")
        original = original.convert("RGBA")
        texture = original.resize((32, 32), Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    texture.save(destination, format="TGA", compression=None)
    with Image.open(destination) as decoded:
        assert decoded.mode == "RGBA" and decoded.size == (32, 32)
        assert decoded.tobytes() == texture.tobytes()
    print(f"Wrote {destination}: uncompressed 32x32 RGBA TGA")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "RBGS/Media/logo-minimap-32.tga")
    args = parser.parse_args()
    build(args.source, args.output)
