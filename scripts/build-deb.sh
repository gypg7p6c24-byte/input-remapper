#!/usr/bin/env bash
set -euo pipefail

pick_python() {
  local candidate

  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "$PYTHON_BIN"
    return 0
  fi

  for candidate in python3 python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import tomllib" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done

  echo "python3"
}

build_deb() {
  # https://www.devdungeon.com/content/debian-package-tutorial-dpkgdeb
  # that was really easy actually
  local python_bin
  python_bin="$(pick_python)"

  rm -rf build
  mkdir -p dist
  INPUT_REMAPPER_PACKAGES_DIR=/usr/lib/python3/dist-packages \
    "$python_bin" -m install --root build/deb
  find build/deb/usr/lib/python3/dist-packages -name '__pycache__' -type d -prune -exec rm -rf {} +
  find build/deb/usr/lib/python3/dist-packages -name '*.pyc' -delete
  find build/deb/usr/lib/python3/dist-packages -path '*/direct_url.json' -delete
  cp -r ./DEBIAN build/deb
  local installed_size
  installed_size="$(du -sk build/deb | awk '{print $1}')"
  printf 'Installed-Size: %s\n' "$installed_size" >> build/deb/DEBIAN/control
  dpkg-deb --root-owner-group -Z gzip -b build/deb dist/input-remapper-2.2.0.deb
}

build_deb
