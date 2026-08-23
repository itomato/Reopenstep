from __future__ import annotations

import tempfile
from pathlib import Path

from .errors import ReopenstepError
from .ufs import extract_file, replace_file


DEFAULT_DEVELOPER_PACKAGES = (
    "DeveloperTools",
    "DeveloperLibs",
    "DeveloperDoc",
    "GNUSource",
    "ProfileLibs",
)

INSERTION_MARKER = "RECEIPT_DIR=/NextLibrary/Receipts\n"
PATCH_MARKER = "# Reopenstep Developer partition overlay v1"


def _validate_packages(packages: tuple[str, ...]) -> None:
    if not packages:
        raise ReopenstepError("at least one Developer package is required")
    if len(packages) != len(set(packages)):
        raise ReopenstepError("Developer package list contains duplicates")
    invalid = [name for name in packages if not name or "/" in name or ".." in name]
    if invalid:
        raise ReopenstepError(f"invalid Developer package name: {', '.join(invalid)}")


def patch_rc_cdrom(text: str, packages: tuple[str, ...], *, persist_drivers: bool = True) -> str:
    _validate_packages(packages)
    if PATCH_MARKER in text:
        return text
    if text.count(INSERTION_MARKER) != 1:
        raise ReopenstepError("unknown rc.cdrom: RECEIPT_DIR signature did not match exactly once")
    if "ROOTDEV=`${FINDROOT}`" not in text or "${DITTO} -T -arch ${ARCH} -bom" not in text:
        raise ReopenstepError("unknown rc.cdrom: required CDIS installation signatures are absent")

    package_words = " ".join(packages)
    block = f'''\

{PATCH_MARKER}
# The hybrid disc label exposes the original Developer UFS as partition b of
# the same device that supplies the partition-a installation root. Keep the
# original package BOMs separate from BaseSystem.bom, as Installer does.
DEVELOPER_ROOT=${{FD}}
DEVELOPER_DEV=`echo "${{ROOTDEV}}" | ${{SED}} 's/a$/b/'`
if [ "${{DEVELOPER_DEV}}" = "${{ROOTDEV}}" ]; then
    echo "Cannot derive the Developer partition from ${{ROOTDEV}}."
    ${{SYNC}} ; ${{REBOOT}}
    exit 1
fi
${{MKDIRS}} ${{DEVELOPER_ROOT}}
${{MOUNT}} -r -n ${{DEVELOPER_DEV}} ${{DEVELOPER_ROOT}}
if [ $? -ne 0 ]; then
    echo "Cannot mount Developer partition ${{DEVELOPER_DEV}}."
    ${{SYNC}} ; ${{REBOOT}}
    exit 1
fi

DEVELOPER_PACKAGES="{package_words}"
for package in ${{DEVELOPER_PACKAGES}}
do
    source_receipt=${{DEVELOPER_ROOT}}${{RECEIPT_DIR}}/${{package}}.pkg
    source_bom=${{source_receipt}}/${{package}}.bom
    target_receipt=${{HD}}${{RECEIPT_DIR}}/${{package}}.pkg
    output_bom=${{HD}}/${{package}}.bom
    if [ ! -f ${{source_bom}} ]; then
        echo "Developer package BOM is missing: ${{source_bom}}"
        ${{SYNC}} ; ${{REBOOT}}
        exit 1
    fi
    ${{DITTO}} -T -arch ${{ARCH}} -bom ${{source_bom}} -outBom ${{output_bom}} ${{DEVELOPER_ROOT}} ${{HD}}
    if [ $? -ne 0 ]; then
        echo "Developer package copy failed: ${{package}}"
        ${{SYNC}} ; ${{REBOOT}}
        exit 1
    fi
    ${{MKDIRS}} ${{target_receipt}}
    ${{DITTO}} ${{source_receipt}} ${{target_receipt}}
    ${{MV}} ${{output_bom}} ${{target_receipt}}/${{package}}.bom
done
'''
    if persist_drivers:
        block += '''\

# BaseSystem.bom may not name newly slipstreamed bundles. Copy the complete
# selected architecture directory before CDIS writes its installed boot table.
INSTALLED_DRIVER_ROOT=/private/Drivers/${ARCH}
if [ -d ${INSTALLED_DRIVER_ROOT} ]; then
    ${MKDIRS} ${HD}${INSTALLED_DRIVER_ROOT}
    ${DITTO} ${INSTALLED_DRIVER_ROOT} ${HD}${INSTALLED_DRIVER_ROOT}
    if [ $? -ne 0 ]; then
        echo "Installed driver copy failed: ${INSTALLED_DRIVER_ROOT}"
        ${SYNC} ; ${REBOOT}
        exit 1
    fi
fi
'''
    return text.replace(INSERTION_MARKER, INSERTION_MARKER + block, 1)


def patch_cdis_image(
    image: Path,
    output: Path,
    packages: tuple[str, ...] = DEFAULT_DEVELOPER_PACKAGES,
    *,
    persist_drivers: bool = True,
) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reopenstep-cdis-", dir=output.parent) as directory:
        extracted = Path(directory) / "rc.cdrom"
        extract_file(image, "/etc/rc.cdrom", extracted)
        original = extracted.read_text(encoding="latin-1")
        patched = patch_rc_cdrom(original, packages, persist_drivers=persist_drivers)
        state = "already-patched" if patched == original else "patched"
        extracted.write_text(patched, encoding="latin-1", newline="")
        report = replace_file(image, "/etc/rc.cdrom", extracted, output, mode=0o444)
    return {
        **report,
        "source": str(image),
        "state": state,
        "developer_packages": list(packages),
        "persist_installed_drivers": persist_drivers,
    }
