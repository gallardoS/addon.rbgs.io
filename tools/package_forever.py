"""Build a player-only Forever ZIP; never uploads or changes the local game."""
import argparse
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "rbgs.io.toc", "CaptureStore.lua", "ForeverAdapter.lua", "RBGS.lua",
    "Panel.lua", "ScoreboardButton.lua", "Media/logo.tga", "Media/logo-minimap-32.tga",
)


def package(version=None, output=None):
    source = ROOT / "rbgs.io"
    toc = (source / "rbgs.io.toc").read_text(encoding="utf-8")
    current = re.search(r"^## Version: (\S+)$", toc, re.MULTILINE)
    if not current:
        raise ValueError("Missing TOC version")
    version = version or current[1]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid release version")
    if "## Interface: 16001" not in toc:
        raise ValueError("Unexpected Forever interface; review compatibility before packaging")
    payload = {name: (source / name).read_bytes() for name in FILES}
    toc = re.sub(r"^## Version: \S+$", "## Version: " + version, toc, flags=re.MULTILINE)
    payload["rbgs.io.toc"] = toc.encode("utf-8")
    lua = payload["ForeverAdapter.lua"].decode("utf-8")
    lua, count = re.subn(r'addonVersion="[^"]+"', 'addonVersion="' + version + '"', lua)
    if count != 1:
        raise ValueError("Cannot stamp capture addonVersion")
    payload["ForeverAdapter.lua"] = lua.encode("utf-8")
    # Every file listed by the Forever TOC must be shipped; no test-client TOC.
    for name in toc.splitlines():
        name = name.strip().replace("\\", "/")
        if name and not name.startswith("#") and name not in payload:
            raise ValueError("TOC file missing from package: " + name)
    payload["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    payload["CHANGELOG.md"] = (ROOT / "CHANGELOG.md").read_bytes()
    output = Path(output) if output else ROOT / "releases" / ("rbgs.io-" + version + "-forever.zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(payload.items()):
            info = ZipInfo("rbgs.io/" + name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        assert set(archive.namelist()) == {"rbgs.io/" + name for name in payload}
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Stamp this version into the ZIP only (for CI builds)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(package(args.version, args.output))
