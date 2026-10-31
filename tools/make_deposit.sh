#!/usr/bin/env bash
#
# Build a Zenodo payload and refuse to hand over a bad one.
#
#   tools/make_deposit.sh v1.1.0
#
# The v1.0.0 deposit shipped a 149 KB archive whose CSV members were 134-byte
# Git-LFS pointers. It passed every check that was applied to it, because the
# checks were "did the file upload" rather than "does the file contain anything".
# This script replaces recall with measurement.
#
# Exit codes: 0 clean payload, 1 build/verification failure, 2 usage error.
set -euo pipefail

REF="${1:-}"
if [ -z "$REF" ]; then
    echo "usage: tools/make_deposit.sh <tag-or-ref>   e.g. tools/make_deposit.sh v1.1.0" >&2
    exit 2
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

DIST="$ROOT/dist"
NAME="sarai-framework-${REF#v}"
ARCHIVE="$DIST/$NAME.tar.gz"

fail() { echo "FAIL  $*" >&2; exit 1; }
note() { echo "  ok  $*"; }

# ---------------------------------------------------------------- preconditions
[ -z "$(git status --porcelain)" ] || \
    fail "working tree is dirty; commit or stash before building a payload"

git rev-parse -q --verify "refs/tags/$REF" >/dev/null 2>&1 || \
    git rev-parse -q --verify "$REF" >/dev/null 2>&1 || \
    fail "$REF is neither a tag nor a commit in this repository"

REF_SHA="$(git rev-parse "$REF^{commit}")"
echo "building $NAME from $REF ($(git rev-parse --short "$REF_SHA"))"

# ---------------------------------------------------------------- build
mkdir -p "$DIST"
rm -f "$ARCHIVE"
git archive --format=tar.gz --prefix="$NAME/" -o "$ARCHIVE" "$REF_SHA"
note "archived $(du -h "$ARCHIVE" | cut -f1)"

LIST="$(tar -tzf "$ARCHIVE")"

# ---------------------------------------------------------------- 1. no secrets
if echo "$LIST" | grep -qE '(^|/)\.env$'; then
    fail "payload contains a .env file"
fi
note "no .env"

if echo "$LIST" | grep -qE '(^|/)\.git/'; then
    fail "payload contains a .git directory"
fi
note "no .git"

# Scan content, by value, for the shape of a credential -- filenames are not
# evidence. The token in this project is a 60-character lowercase hex string.
if tar -xzOf "$ARCHIVE" \
    | grep -aoE '\b[0-9a-f]{60}\b' \
    | head -1 | grep -q .; then
    fail "payload contains a 60-hex-character string (credential shape)"
fi
note "no credential-shaped strings"

# ---------------------------------------------------------------- 2. no stubs
# A Git-LFS pointer is 130-140 bytes and begins with this exact line. If one is
# present, the archive is advertising data it does not carry.
if tar -xzOf "$ARCHIVE" 2>/dev/null | head -c 2000 \
    | grep -q 'version https://git-lfs.github.com/spec'; then
    fail "payload contains a Git-LFS pointer stub"
fi

STUBS="$(tar -xzOf "$ARCHIVE" --wildcards '*.csv' 2>/dev/null \
    | grep -c 'version https://git-lfs.github.com/spec' || true)"
[ "${STUBS:-0}" -eq 0 ] || fail "$STUBS CSV member(s) are LFS pointers"
note "no LFS pointers in any CSV member"

# ---------------------------------------------------------------- 3. no nesting
if echo "$LIST" | grep -qE '\.(tar\.gz|tgz|zip)$'; then
    fail "payload contains a nested archive"
fi
note "no nested archives"

# ---------------------------------------------------------------- 4. no data claim
# A code-only deposit must not contain data directories; if it does, the licence
# field is wrong. This catches an archive where LFS happened to expand.
if echo "$LIST" | grep -qE '^[^/]+/datasets/(sources|raw_tables)/'; then
    fail "payload contains dataset paths; decide the licence question before uploading"
fi
note "no dataset paths (code-only deposit, as DATA_SOURCES.md states)"

# ---------------------------------------------------------------- 5. substance
# A code-only artefact of this repository is ~100-400 KB. Anything under 20 KB
# is an empty archive that passed the checks above by containing nothing.
SIZE="$(stat -c %s "$ARCHIVE")"
[ "$SIZE" -gt 20000 ] || fail "archive is only $SIZE bytes; it holds almost nothing"
note "archive size $SIZE bytes is plausible for code-only"

FILES="$(echo "$LIST" | grep -vc '/$' || true)"
note "$FILES files"

# ---------------------------------------------------------------- manifest
{
    echo "# payload manifest"
    echo "ref:      $REF"
    echo "commit:   $REF_SHA"
    echo "archive:  $(basename "$ARCHIVE")"
    echo "bytes:    $SIZE"
    echo "md5:      $(md5sum "$ARCHIVE" | cut -d' ' -f1)"
    echo "sha256:   $(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
    echo "files:    $FILES"
} > "$DIST/$NAME.manifest.txt"

echo
echo "  ok  payload verified"
echo "      $ARCHIVE"
echo "      $DIST/$NAME.manifest.txt"
echo
echo "Upload with Content-Type: application/octet-stream, then compare the md5"
echo "Zenodo reports against the manifest."
