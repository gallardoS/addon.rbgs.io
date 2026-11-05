"""Convert the provided RGBA logo to bounded WoW and desktop assets."""
import argparse
from pathlib import Path
from PIL import Image

command = argparse.ArgumentParser(description=__doc__)
command.add_argument('source', type=Path)
command.add_argument('--companion', type=Path, required=True)
command.add_argument('--debugger-source', type=Path, help='Red debugger variant; defaults to branding/rbgs.io-debugger.png when present')
args = command.parse_args()
root = Path(__file__).resolve().parents[1]
with Image.open(args.source) as source:
    source.load()
    if source.width != source.height:
        raise ValueError('Logo must be square')
    source = source.convert('RGBA')
    original = root / 'branding/rbgs.io.png'
    original.parent.mkdir(parents=True, exist_ok=True)
    source.save(original, optimize=True)
    texture = source.resize((256, 256), Image.Resampling.LANCZOS)
    for addon in ('rbgs.io', 'RBGSCompatibility'):
        destination = root / addon / 'Media/logo.tga'
        destination.parent.mkdir(parents=True, exist_ok=True)
        selected_texture = texture
        debugger_source = args.debugger_source or root / 'branding/rbgs.io-debugger.png'
        if addon == 'RBGSCompatibility' and debugger_source.exists():
            with Image.open(debugger_source) as debugger:
                debugger.load()
                if debugger.width != debugger.height: raise ValueError('Debugger logo must be square')
                selected_texture = debugger.convert('RGBA').resize((256, 256), Image.Resampling.LANCZOS)
        selected_texture.save(destination, compression=None)
        with Image.open(destination) as encoded:
            assert encoded.mode == 'RGBA' and encoded.size == (256, 256)
            assert encoded.getpixel((0, 0))[3] == 0
    destination = args.companion / 'public/branding/logo.png'
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.resize((256, 256), Image.Resampling.LANCZOS).save(destination, optimize=True)
    print('Preserved RGBA source; generated two 256px uncompressed TGA textures and desktop PNG.')
