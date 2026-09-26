#!/usr/bin/env python3
"""
ARC80OX TWRP Recovery Manual Port Builder
Automatically extracts, patches, and rebuilds TWRP recovery for Archos 80 Oxygen (ARC80OX/AC80OX)
using stock recovery and kernel sources.

Usage:
  python3 twrp_port_builder.py \
    --stock-recovery /path/to/recovery-sign.img \
    --twrp-recovery /path/to/ac101box-twrp.img \
    --magiskboot /path/to/magiskboot \
    --output /path/to/output-recovery.img \
    [--workdir /path/to/work] \
    [--keep-work]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


class BuildError(RuntimeError):
    """Build process error."""
    pass


class TWRPBuilder:
    """Port TWRP recovery for ARC80OX with proper MTK device configurations."""

    def __init__(
        self,
        stock_recovery: Path,
        twrp_recovery: Path,
        magiskboot: Path,
        output: Path,
        workdir: Path = Path("work_twrp"),
        keep_work: bool = False,
    ):
        self.stock_recovery = stock_recovery.resolve()
        self.twrp_recovery = twrp_recovery.resolve()
        self.magiskboot = magiskboot.resolve()
        self.output = output.resolve()
        self.workdir = workdir.resolve()
        self.keep_work = keep_work

        # Internal paths
        self.log_file = self.workdir / "build.log"
        self.stock_dir = self.workdir / "stock"
        self.twrp_dir = self.workdir / "twrp"
        self.repack_dir = self.workdir / "repack"
        self.config_dir = self.workdir / "config"

        self._validate_inputs()

    def _validate_inputs(self) -> None:
        """Validate all input files exist and are accessible."""
        for path, label in [
            (self.stock_recovery, "Stock recovery"),
            (self.twrp_recovery, "TWRP recovery"),
            (self.magiskboot, "magiskboot"),
        ]:
            if not path.is_file():
                raise BuildError(f"{label} not found: {path}")

        if not os.access(self.magiskboot, os.X_OK):
            raise BuildError(f"magiskboot not executable: {self.magiskboot}")

        if self.output.exists():
            raise BuildError(f"Output already exists, refusing to overwrite: {self.output}")

        if self.workdir.exists():
            raise BuildError(f"Work directory exists, remove it first: {self.workdir}")

    def _run_cmd(self, cmd: list[str], cwd: Path, label: str = "") -> str:
        """Execute a command and log output."""
        label_str = f"[{label}] " if label else ""
        print(f"{label_str}$ {' '.join(map(str, cmd))}")

        result = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        output = result.stdout or ""
        with self.log_file.open("a", encoding="utf-8") as fh:
            fh.write(f"\n{'='*80}\n")
            fh.write(f"{label_str}$ {' '.join(map(str, cmd))}\n")
            fh.write(f"{'='*80}\n{output}\n")

        if output:
            print(output, end="")

        if result.returncode != 0:
            raise BuildError(
                f"Command failed (exit {result.returncode}): {label or cmd[0]}"
            )

        return output

    def _sha256(self, path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def setup_work_dirs(self) -> None:
        """Create work directory structure."""
        print("\n" + "=" * 80)
        print("STEP 1: Setting up work directories")
        print("=" * 80)
        self.workdir.mkdir(parents=True)
        self.log_file.touch()
        print(f"✓ Work directory: {self.workdir}")
        print(f"✓ Log file: {self.log_file}")

    def unpack_images(self) -> None:
        """Unpack both stock and TWRP recovery images."""
        print("\n" + "=" * 80)
        print("STEP 2: Unpacking recovery images")
        print("=" * 80)

        for image, out_dir, label in [
            (self.stock_recovery, self.stock_dir, "Stock ARC80OX"),
            (self.twrp_recovery, self.twrp_dir, "TWRP AC101BOX"),
        ]:
            print(f"\nUnpacking {label} recovery...")
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image, out_dir / "original.img")
            self._run_cmd(
                [str(self.magiskboot), "unpack", "original.img"],
                out_dir,
                label=label,
            )
            print(f"✓ Unpacked {label}")

    def extract_ramdisks(self) -> None:
        """Extract ramdisk.cpio contents to directories."""
        print("\n" + "=" * 80)
        print("STEP 3: Extracting ramdisk contents")
        print("=" * 80)

        for base_dir, label in [
            (self.stock_dir, "Stock"),
            (self.twrp_dir, "TWRP"),
        ]:
            print(f"\nExtracting {label} ramdisk...")
            self._run_cmd(
                [str(self.magiskboot), "cpio", "ramdisk.cpio", "extract"],
                base_dir,
                label=f"{label} Extract",
            )
            print(f"✓ Extracted {label} ramdisk to {base_dir}/ramdisk/")

    def analyze_configs(self) -> None:
        """Analyze and display important config files."""
        print("\n" + "=" * 80)
        print("STEP 4: Analyzing device configurations")
        print("=" * 80)

        # Create config output directory
        self.config_dir.mkdir(exist_ok=True)

        stock_ramdisk = self.stock_dir / "ramdisk"
        twrp_ramdisk = self.twrp_dir / "ramdisk"

        # Important files to check
        important_files = [
            "init.recovery.mt8163.rc",
            "fstab.mt8163",
            "ueventd.mt8163.rc",
            "etc/recovery.fstab",
            "default.prop",
        ]

        for filename in important_files:
            stock_file = stock_ramdisk / filename
            twrp_file = twrp_ramdisk / filename

            print(f"\n--- {filename} ---")

            if stock_file.exists():
                print(f"✓ Found in Stock: {stock_file}")
                with stock_file.open("r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                    print(f"  Size: {len(content)} bytes")
                    if filename.endswith(".rc") or filename.endswith(".fstab"):
                        print(f"  Preview:\n{content[:500]}")
                # Copy to config directory
                shutil.copy2(stock_file, self.config_dir / f"STOCK_{filename}")
            else:
                print(f"✗ Not found in Stock")

            if twrp_file.exists():
                print(f"✓ Found in TWRP: {twrp_file}")
            else:
                print(f"✗ Not found in TWRP")

    def patch_twrp_ramdisk(self) -> None:
        """Inject stock MTK configs into TWRP ramdisk."""
        print("\n" + "=" * 80)
        print("STEP 5: Patching TWRP ramdisk with stock MTK configurations")
        print("=" * 80)

        stock_ramdisk = self.stock_dir / "ramdisk"
        twrp_ramdisk = self.twrp_dir / "ramdisk"

        # Files to copy from stock to TWRP
        files_to_copy = [
            "init.recovery.mt8163.rc",
            "fstab.mt8163",
            "ueventd.mt8163.rc",
        ]

        for filename in files_to_copy:
            source = stock_ramdisk / filename
            dest = twrp_ramdisk / filename

            if source.exists():
                print(f"\n✓ Copying {filename}...")
                shutil.copy2(source, dest)
                print(f"  Copied to: {dest}")
            else:
                print(f"\n⚠ Skipping {filename} (not found in stock)")

        # Handle etc/recovery.fstab
        stock_fstab = stock_ramdisk / "etc" / "recovery.fstab"
        twrp_fstab = twrp_ramdisk / "etc" / "recovery.fstab"

        if stock_fstab.exists():
            print(f"\n✓ Copying etc/recovery.fstab...")
            twrp_fstab.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stock_fstab, twrp_fstab)
            print(f"  Copied to: {twrp_fstab}")

    def sync_ramdisk(self) -> None:
        """Synchronize modified ramdisk back to cpio archive."""
        print("\n" + "=" * 80)
        print("STEP 6: Synchronizing ramdisk changes")
        print("=" * 80)

        print("\nSyncing TWRP ramdisk...")
        self._run_cmd(
            [str(self.magiskboot), "cpio", "ramdisk.cpio", "sync"],
            self.twrp_dir,
            label="TWRP Sync",
        )
        print("✓ TWRP ramdisk synchronized")

    def prepare_repack(self) -> None:
        """Prepare components for repacking."""
        print("\n" + "=" * 80)
        print("STEP 7: Preparing components for repacking")
        print("=" * 80)

        self.repack_dir.mkdir(parents=True, exist_ok=True)

        print("\nCopying stock kernel and DTB...")
        for component in ["kernel", "kernel_dtb"]:
            source = self.stock_dir / component
            if source.exists():
                dest = self.repack_dir / component
                shutil.copy2(source, dest)
                size_kb = source.stat().st_size / 1024
                print(f"  ✓ {component}: {size_kb:.1f} KB")
            else:
                print(f"  ⚠ {component} not found")

        print("\nCopying modified TWRP ramdisk...")
        shutil.copy2(self.twrp_dir / "ramdisk.cpio", self.repack_dir / "ramdisk.cpio")
        print("  ✓ ramdisk.cpio copied")

        print("\nCopying stock base image for header preservation...")
        shutil.copy2(self.stock_recovery, self.repack_dir / "stock-base.img")
        print("  ✓ stock-base.img copied")

    def repack_recovery(self) -> None:
        """Repack the recovery image."""
        print("\n" + "=" * 80)
        print("STEP 8: Repacking recovery image")
        print("=" * 80)

        print("\nRepacking recovery image...")
        self._run_cmd(
            [str(self.magiskboot), "repack", "stock-base.img"],
            self.repack_dir,
            label="Repack",
        )

        candidate = self.repack_dir / "new-boot.img"
        if not candidate.exists():
            raise BuildError("Repacking failed: new-boot.img not created")

        print("✓ Recovery image repacked successfully")
        print(f"  Output: {candidate}")

    def finalize_output(self) -> None:
        """Copy final image and generate report."""
        print("\n" + "=" * 80)
        print("STEP 9: Finalizing output")
        print("=" * 80)

        candidate = self.repack_dir / "new-boot.img"

        self.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, self.output)

        output_hash = self._sha256(self.output)
        output_size_mb = self.output.stat().st_size / (1024 * 1024)

        print(f"\n✓ Recovery image created successfully!")
        print(f"  Output: {self.output}")
        print(f"  Size: {output_size_mb:.2f} MB")
        print(f"  SHA256: {output_hash}")

        # Generate report
        report = {
            "device": "Archos 80 Oxygen (ARC80OX/AC80OX)",
            "soc": "MT8163",
            "android_version": "Android 6.x",
            "warning": "⚠️ CANDIDATE IMAGE ONLY - Test thoroughly before flashing to device",
            "stock_recovery": {
                "path": str(self.stock_recovery),
                "sha256": self._sha256(self.stock_recovery),
                "components_used": ["kernel", "kernel_dtb", "header"],
            },
            "twrp_recovery": {
                "path": str(self.twrp_recovery),
                "sha256": self._sha256(self.twrp_recovery),
                "components_used": ["ramdisk with stock MTK configs"],
            },
            "output": {
                "path": str(self.output),
                "sha256": output_hash,
                "size_mb": output_size_mb,
            },
            "composition": {
                "kernel": "Stock ARC80OX",
                "kernel_dtb": "Stock ARC80OX",
                "ramdisk": "TWRP AC101BOX + Stock ARC80OX MTK configurations",
                "files_injected": [
                    "init.recovery.mt8163.rc",
                    "fstab.mt8163",
                    "ueventd.mt8163.rc",
                    "etc/recovery.fstab",
                ],
            },
            "testing_procedure": {
                "step_1": "DO NOT flash directly. First backup your original recovery using SP Flash Tool.",
                "step_2": "Test via fastboot boot (non-persistent):",
                "step_2_cmd": f"fastboot boot {self.output}",
                "step_3": "Check if TWRP UI appears and touchscreen responds.",
                "step_4": "If touch works: fastboot flash recovery <image>",
                "step_5": "If touch fails: Extract and compare touchscreen drivers/modules.",
            },
            "troubleshooting": {
                "bootloop": "Flash stock recovery back via SP Flash Tool",
                "no_touch": "Touchscreen driver mismatch - needs kernel/DTB recompilation or module injection",
                "wrong_orientation": "Edit init.recovery.mt8163.rc or BoardConfig.mk if rebuilding",
            },
            "log_file": str(self.log_file),
        }

        report_path = self.output.parent / (self.output.name + ".json")
        with report_path.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

        print(f"\n✓ Report generated: {report_path}")

    def cleanup(self) -> None:
        """Clean up work directory if requested."""
        if not self.keep_work and self.workdir.exists():
            print("\n" + "=" * 80)
            print("Cleaning up work directory...")
            print("=" * 80)
            shutil.rmtree(self.workdir, ignore_errors=True)
            print("✓ Work directory removed")
        else:
            print(f"\n✓ Work directory preserved: {self.workdir}")

    def build(self) -> int:
        """Execute the complete build process."""
        try:
            self.setup_work_dirs()
            self.unpack_images()
            self.extract_ramdisks()
            self.analyze_configs()
            self.patch_twrp_ramdisk()
            self.sync_ramdisk()
            self.prepare_repack()
            self.repack_recovery()
            self.finalize_output()
            self.cleanup()

            print("\n" + "=" * 80)
            print("✓ BUILD COMPLETED SUCCESSFULLY")
            print("=" * 80)
            return 0

        except Exception as exc:
            print(f"\n✗ BUILD FAILED: {exc}", file=sys.stderr)
            print(f"✗ See log for details: {self.log_file}", file=sys.stderr)
            return 2


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Port TWRP recovery for Archos 80 Oxygen (ARC80OX) with proper MTK device configurations."
    )
    parser.add_argument(
        "--stock-recovery",
        required=True,
        type=Path,
        help="Path to original ARC80OX stock recovery image",
    )
    parser.add_argument(
        "--twrp-recovery",
        required=True,
        type=Path,
        help="Path to AC101BOX TWRP recovery image (as base)",
    )
    parser.add_argument(
        "--magiskboot",
        required=True,
        type=Path,
        help="Path to magiskboot executable",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to save the ported recovery image",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("work_twrp"),
        help="Work directory (default: work_twrp)",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Keep work directory after build (for debugging)",
    )

    args = parser.parse_args()

    try:
        builder = TWRPBuilder(
            stock_recovery=args.stock_recovery,
            twrp_recovery=args.twrp_recovery,
            magiskboot=args.magiskboot,
            output=args.output,
            workdir=args.workdir,
            keep_work=args.keep_work,
        )
        return builder.build()
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
