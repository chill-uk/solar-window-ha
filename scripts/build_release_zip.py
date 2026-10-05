"""Build the HACS integration-only ZIP and validate release version consistency."""
import argparse
import ast
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "solar_window"


def build(output, version=None):
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    expected = manifest["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", expected):
        raise ValueError("Invalid manifest version")
    if version is not None and version.removeprefix("v") != expected:
        raise ValueError("Tag and manifest versions do not match")
    tree = ast.parse((INTEGRATION / "const.py").read_text())
    const_version = next(ast.literal_eval(node.value) for node in tree.body
                         if isinstance(node, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in node.targets))
    if const_version != expected or json.loads((ROOT / "package.json").read_text())["version"] != expected:
        raise ValueError("Manifest, const.py and package.json versions must match")
    files = [p for p in sorted(INTEGRATION.rglob("*")) if p.is_file()
             and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(INTEGRATION))
        archive.write(ROOT / "LICENSE", "LICENSE")
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert "manifest.json" in names and "frontend/solar-window-card.js" in names
        assert not any(n.startswith(("custom_components/", "tests/")) or "__pycache__" in n for n in names)
    print(f"Built {output} for v{expected} ({len(names)} files)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="solar_window.zip")
    parser.add_argument("--version", help="Optional v-prefixed release tag to validate")
    args = parser.parse_args()
    build(args.output, args.version)
