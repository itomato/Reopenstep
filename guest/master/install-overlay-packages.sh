#!/bin/sh
set -eu

if test "$#" -lt 4; then
    echo "usage: $0 SOURCE_ROOT TARGET_ROOT STATE_DIR PACKAGE..." >&2
    exit 2
fi

source_root=$1
target_root=$2
state_dir=$3
shift 3

for value in "$source_root" "$target_root" "$state_dir"; do
    if test -z "$value"; then
        echo "source, target, and state paths must be explicit" >&2
        exit 1
    fi
done
if test "$target_root" = /; then
    echo "target root must not be /" >&2
    exit 1
fi
for directory in "$source_root" "$target_root"; do
    if test ! -d "$directory"; then
        echo "filesystem root not found: $directory" >&2
        exit 1
    fi
done
if test "$source_root" = "$target_root"; then
    echo "source and target roots must be different" >&2
    exit 1
fi

PATH=${REOPENSTEP_NATIVE_PATH-/usr/etc:/usr/bin:/bin}
export PATH
for command in ditto lsbom; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "required native command not found: $command" >&2
        exit 1
    fi
done

mkdir -p "$state_dir"
packages_file="$state_dir/packages.list"
collisions_file="$state_dir/collisions.list"
: > "$packages_file"
: > "$collisions_file"
paths=/tmp/reopenstep-package-paths.$$
trap 'rm -f "$paths"' 0 1 2 3 15

for supplied in "$@"; do
    package=`basename "$supplied" .pkg`
    case "$package" in
        ""|*/*|*..*)
            echo "invalid package name: $supplied" >&2
            exit 1 ;;
    esac
    receipt="$source_root/NextLibrary/Receipts/$package.pkg"
    target_receipt="$target_root/NextLibrary/Receipts/$package.pkg"
    bom="$receipt/$package.bom"
    for suffix in .info .bom .sizes; do
        if test ! -f "$receipt/$package$suffix"; then
            echo "$receipt: missing $package$suffix" >&2
            exit 1
        fi
    done

    lsbom -f -l -b -c -s "$bom" > "$paths"
    while read path; do
        case "$path" in
            /*|../*|*/../*|*/..)
                echo "$package: unsafe BOM path: $path" >&2
                exit 1 ;;
        esac
        if test -e "$target_root/$path" -o -L "$target_root/$path"; then
            echo "$package $path" >> "$collisions_file"
        fi
    done < "$paths"
    : > "$paths"

    ditto -bom "$bom" "$source_root" "$target_root"
    mkdir -p "$target_root/NextLibrary/Receipts"
    ditto "$receipt" "$target_receipt"
    echo "$package" >> "$packages_file"
    echo "installed overlay package $package"
done

echo "package order: $packages_file"
echo "pre-existing path report: $collisions_file"
