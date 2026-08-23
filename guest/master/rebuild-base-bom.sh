#!/bin/sh
set -eu

if test "$#" -lt 3; then
    echo "usage: $0 MEDIA_ROOT STAGING_ROOT STATE_DIR [EXTRA_TREE...]" >&2
    exit 2
fi

media_root=$1
staging_root=$2
state_dir=$3
shift 3

for value in "$media_root" "$staging_root" "$state_dir"; do
    if test -z "$value"; then
        echo "media, staging, and state paths must be explicit" >&2
        exit 1
    fi
done
if test "$staging_root" = /; then
    echo "staging root must not be /" >&2
    exit 1
fi
if test "$media_root" = "$staging_root"; then
    echo "media and staging roots must be different" >&2
    exit 1
fi

PATH=${REOPENSTEP_NATIVE_PATH-/usr/etc:/usr/bin:/bin}
export PATH
for command in ditto lsbom mkbom; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "required native command not found: $command" >&2
        exit 1
    fi
done

base_bom="$media_root/usr/lib/NextStep/BaseSystem.bom"
packages_file="$state_dir/packages.list"
if test ! -f "$base_bom"; then
    echo "base system BOM not found: $base_bom" >&2
    exit 1
fi
if test ! -f "$packages_file"; then
    echo "package state not found: $packages_file" >&2
    exit 1
fi
if test -d "$staging_root" && test -n "`ls -A "$staging_root" 2>/dev/null`"; then
    echo "staging root must be empty: $staging_root" >&2
    exit 1
fi
mkdir -p "$staging_root" "$state_dir"

# Materialize only the installable base. Running mkbom over media_root itself
# would incorrectly add NextCD and other installation-only content.
ditto -bom "$base_bom" "$media_root" "$staging_root"

while read package; do
    test -n "$package" || continue
    case "$package" in
        *[!A-Za-z0-9_.+-]*|*..*)
            echo "unsafe package in state: $package" >&2
            exit 1 ;;
    esac
    receipt="NextLibrary/Receipts/$package.pkg"
    bom="$media_root/$receipt/$package.bom"
    if test ! -f "$bom"; then
        echo "installed package BOM missing: $bom" >&2
        exit 1
    fi
    ditto -bom "$bom" "$media_root" "$staging_root"
    mkdir -p "$staging_root/NextLibrary/Receipts"
    ditto "$media_root/$receipt" "$staging_root/$receipt"
done < "$packages_file"

for tree in "$@"; do
    case "$tree" in
        ""|/*|../*|*/../*|*/..)
            echo "extra tree must be relative and remain below media root: $tree" >&2
            exit 1 ;;
    esac
    if test ! -d "$media_root/$tree"; then
        echo "extra tree not found: $media_root/$tree" >&2
        exit 1
    fi
    parent=`dirname "$tree"`
    mkdir -p "$staging_root/$parent"
    ditto "$media_root/$tree" "$staging_root/$tree"
done

new_bom=/tmp/reopenstep-BaseSystem.bom.$$
trap 'rm -f "$new_bom"' 0 1 2 3 15
mkbom "$staging_root" "$new_bom"
lsbom -s "$new_bom" >/dev/null

if test ! -f "$base_bom.pre-reopenstep"; then
    cp -p "$base_bom" "$base_bom.pre-reopenstep"
fi
cp "$new_bom" "$base_bom"
chmod 444 "$base_bom"

old_sum=`cksum "$base_bom.pre-reopenstep" | awk '{print $1 " " $2}'`
new_sum=`cksum "$base_bom" | awk '{print $1 " " $2}'`
collision_count=0
if test -f "$state_dir/collisions.list"; then
    collision_count=`wc -l < "$state_dir/collisions.list" | awk '{print $1}'`
fi
report="$state_dir/native-report.plist"
{
    echo '{'
    echo '    Format = 1;'
    echo '    BaseSystemBOM = {'
    echo "        PreviousCKSUMAndSize = \"$old_sum\";"
    echo "        MasteredCKSUMAndSize = \"$new_sum\";"
    echo '    };'
    echo "    PreexistingPackagePaths = $collision_count;"
    echo '    Packages = ('
    while read package; do
        test -n "$package" && echo "        \"$package\","
    done < "$packages_file"
    echo '    );'
    echo '    ExtraTrees = ('
    for tree in "$@"; do
        echo "        \"$tree\","
    done
    echo '    );'
    echo '}'
} > "$report"

echo "rebuilt $base_bom from installable staging root"
echo "native report: $report"
