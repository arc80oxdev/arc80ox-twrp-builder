#!/usr/bin/env python3
"""
ARC80OX TWRP Recovery Manual Port Builder (Windows Edition)
Automatically extracts, patches, and rebuilds TWRP recovery for Archos 80 Oxygen
using stock recovery and kernel sources - optimized for Windows.

Usage on Windows CMD:
  python twrp_port_builder_windows.py ^
    --stock-recovery "C:\path\to\recovery-sign.img" ^
    --twrp-recovery "C:\path\to\ac101box-twrp.img" ^
    --magiskboot "C:\path\to\magiskboot.exe" ^
    --output "C:\path\to\output-recovery.img" ^
    --keep-work
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath


class BuildError(RuntimeError):
    """Build process error."""
    pass


class TWRPBuilder:
    """Port TWRP recovery for ARC80OX with proper MTK device configurations."""

    def __init__(
        self,
        stock_recovery: str,
        twrp_recovery: str,
        magiskboot: str,
        output: str,
        workdir: str = "work_twrp",
        keep_work: bool = False,
    ):
        # Convert to Path objects with proper Windows handling
        self.stock_recovery = Path(stock_recovery).resolve()
        self.twrp_recovery = Path(twrp_recovery).resolve()
        self.magiskboot = Path(magiskboot).resolve()
        self.output = Path(output).resolve()
        self.workdir = Path(workdir).resolve()
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
        print("\n" + "="*80)
        print("VALIDATION: Checking input files")
        print("="*80)
        
        for path, label in [
            (self.stock_recovery, "Stock recovery"),
            (self.twrp_recovery, "TWRP recovery"),
            (self.magiskboot, "magiskboot"),
        ]:
            print(f"\nChecking {label}...")
            print(f"  Path: {path}")
            
            if not path.exists():
                raise BuildError(f"{label} not found: {path}")
            
            if not path.is_file():
                raise BuildError(f"{label} is not a file: {path}")
            
            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"  ✓ Found ({size_mb:.2f} MB)")

        if not os.access(self.magiskboot, os.X_OK):
            raise BuildError(f"magiskboot not executable: {self.magiskboot}")

        print(f"\nOutput path: {self.output}")
        if self.output.exists():
            raise BuildError(f"Output already exists, refusing to overwrite: {self.output}")

        print(f"Work directory: {self.workdir}")
        if self.workdir.exists():
            raise BuildError(f"Work directory exists, remove it first: {self.workdir}")

        print("\n✓ All validations passed")

    def _run_cmd(self, cmd: list, cwd: Path, label: str = "") -> str:
        """Execute a command and log output."""
        label_str = f"[{label}] " if label else ""
        cmd_str = " ".join(str(c) for c in cmd)
        print(f"\n{label_str}$ {cmd_str}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=0x08000000 if sys.platform == "win32" else 0,  # CREATE_NO_WINDOW
            )
        except FileNotFoundError as e:
            raise BuildError(f"Command not found: {cmd[0]}") from e

        output = result.stdout or ""
        
        # Log to file
        try:
            with self.log_file.open("a", encoding="utf-8", errors="replace") as fh:
                fh.write(f"\n{'='*80}\n")
                fh.write(f"{label_str}$ {cmd_str}\n")
                fh.write(f"Working directory: {cwd}\n")
                fh.write(f"{'='*80}\n{output}\n")
        except Exception as e:
            print(f"Warning: Could not write to log file: {e}")

        # Print first 500 chars of output
        if output:
            preview = output[:500]
            print(preview if len(output) <= 500 else preview + "\n... (see log for full output)")

        if result.returncode != 0:
            raise BuildError(
                f"Command failed (exit {result.returncode}): {label or cmd[0]}\n"
                f"See log: {self.log_file}"
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
        
        try:
            self.workdir.mkdir(parents=True, exist_ok=False)
            self.log_file.touch()
            print(f"✓ Work directory: {self.workdir}")
            print(f"✓ Log file: {self.log_file}")
        except Exception as e:
            raise BuildError(f"Failed to create work directories: {e}")

    def unpack_images(self) -> None:
        """Unpack both stock and TWRP recovery images."""
        print("\n" + "=" * 80)
        print("STEP 2: Unpacking recovery images")
        print("=" * 80)

        for image, out_dir, label in [
            (self.stock_recovery, self.stock_dir, "Stock ARC80OX"),
            (self.twrp_recovery, self.twrp_dir, "TWRP AC101BOX"),
        ]:
            print(f"\n{'─'*40}")
            print(f"Unpacking {label} recovery...")
            print(f"{'─'*40}")
            
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(image), str(out_dir / "original.img"))
                print(f"  ✓ Copied to: {out_dir / 'original.img'}")
                
                self._run_cmd(
                    [str(self.magiskboot), "unpack", "original.img"],
                    out_dir,
                    label=label,
                )
                print(f"✓ Unpacked {label} successfully")
            except Exception as e:
                raise BuildError(f"Failed to unpack {label}: {e}")

    def extract_ramdisks(self) -> None:
        """Extract ramdisk.cpio contents to directories."""
        print("\n" + "=" * 80)
        print("STEP 3: Extracting ramdisk contents")
        print("=" * 80)

        for base_dir, label in [
            (self.stock_dir, "Stock"),
            (self.twrp_dir, "TWRP"),
        ]:
            print(f"\n{'─'*40}")
            print(f"Extracting {label} ramdisk...")
            print(f"{'─'*40}")
            
            try:
                self._run_cmd(
                    [str(self.magiskboot), "cpio", "ramdisk.cpio", "extract"],
                    base_dir,
                    label=f"{label} Extract",
                )
                print(f"✓ Extracted {label} ramdisk")
                print(f"  Location: {base_dir / 'ramdisk'}")
            except Exception as e:
                raise BuildError(f"Failed to extract {label} ramdisk: {e}")

    def analyze_configs(self) -> None:
        """Analyze and display important config files."""
        print("\n" + "=" * 80)
        print("STEP 4: Analyzing device configurations")
        print("=" * 80)

        try:
            self.config_dir.mkdir(exist_ok=True)
        except Exception as e:
            raise BuildError(f"Failed to create config directory: {e}")

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
                try:
                    with stock_file.open("r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                    print(f"✓ Found in Stock")
                    print(f"  Size: {len(content)} bytes")
                    if filename.endswith(".rc") or filename.endswith(".fstab"):
                        preview = content[:300]
                        print(f"  Preview:\n{preview}...")
                    # Copy to config directory
                    shutil.copy2(str(stock_file), str(self.config_dir / f"STOCK_{filename}"))
                except Exception as e:
                    print(f"⚠ Error reading stock file: {e}")
            else:
                print(f"✗ Not found in Stock")

            if twrp_file.exists():
                print(f"✓ Found in TWRP")
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

            print(f"\n--- {filename} ---")
            if source.exists():
                try:
                    print(f"  Copying...")
                    shutil.copy2(str(source), str(dest))
                    print(f"  ✓ Copied to: {dest}")
                except Exception as e:
                    print(f"  ⚠ Failed to copy: {e}")
            else:
                print(f"  ⚠ Skipping (not found in stock)")

        # Handle etc/recovery.fstab
        stock_fstab = stock_ramdisk / "etc" / "recovery.fstab"
        twrp_fstab = twrp_ramdisk / "etc" / "recovery.fstab"

        print(f"\n--- etc/recovery.fstab ---")
        if stock_fstab.exists():
            try:
                print(f"  Copying...")
                twrp_fstab.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(stock_fstab), str(twrp_fstab))
                print(f"  ✓ Copied to: {twrp_fstab}")
            except Exception as e:
                print(f"  ⚠ Failed to copy: {e}")

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

        try:
            self.repack_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise BuildError(f"Failed to create repack directory: {e}")

        print("\nCopying stock kernel and DTB...")
        for component in ["kernel", "kernel_dtb"]:
            source = self.stock_dir / component
            if source.exists():
                try:
                    dest = self.repack_dir / component
                    shutil.copy2(str(source), str(dest))
                    size_kb = source.stat().st_size / 1024
                    print(f"  ✓ {component}: {size_kb:.1f} KB")
                except Exception as e:
                    print(f"  ⚠ Failed to copy {component}: {e}")
            else:
                print(f"  ⚠ {component} not found")

        print("\nCopying modified TWRP ramdisk...")
        try:
            shutil.copy2(str(self.twrp_dir / "ramdisk.cpio"), str(self.repack_dir / "ramdisk.cpio"))
            print("  ✓ ramdisk.cpio copied")
        except Exception as e:
            raise BuildError(f"Failed to copy ramdisk.cpio: {e}")

        print("\nCopying stock base image for header preservation...")
        try:
            shutil.copy2(str(self.stock_recovery), str(self.repack_dir / "stock-base.img"))
            print("  ✓ stock-base.img copied")
        except Exception as e:
            raise BuildError(f"Failed to copy stock base image: {e}")

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

        try:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(candidate), str(self.output))
        except Exception as e:
            raise BuildError(f"Failed to copy output image: {e}")

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
                "step_5": "If touch fails: The issue is likely in the kernel/DTB or touchscreen driver.",
            },
            "troubleshooting": {
                "bootloop": "Flash stock recovery back via SP Flash Tool",
                "no_touch": "Touchscreen driver mismatch - needs kernel/DTB recompilation",
                "wrong_orientation": "Edit init.recovery.mt8163.rc if rebuilding",
            },
            "log_file": str(self.log_file),
        }

        try:
            report_path = self.output.parent / (self.output.name + ".json")
            with report_path.open("w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2)
            print(f"\n✓ Report generated: {report_path}")
        except Exception as e:
            print(f"⚠ Warning: Failed to generate report: {e}")

    def cleanup(self) -> None:
        """Clean up work directory if requested."""
        if not self.keep_work and self.workdir.exists():
            print("\n" + "=" * 80)
            print("Cleaning up work directory...")
            print("=" * 80)
            try:
                shutil.rmtree(str(self.workdir), ignore_errors=True)
                print("✓ Work directory removed")
            except Exception as e:
                print(f"⚠ Warning: Could not remove work directory: {e}")
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
            print(f"\nNext steps:")
            print(f"1. Backup your original recovery using SP Flash Tool")
            print(f"2. Test via: fastboot boot {self.output}")
            print(f"3. Check for TWRP UI and touchscreen response")
            print(f"4. If OK: fastboot flash recovery {self.output}")
            print("=" * 80)
            return 0

        except Exception as exc:
            print(f"\n✗ BUILD FAILED: {exc}", file=sys.stderr)
            if self.log_file.exists():
                print(f"✗ See log for details: {self.log_file}", file=sys.stderr)
            return 2


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Port TWRP recovery for Archos 80 Oxygen (ARC80OX) - Windows Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python twrp_port_builder_windows.py ^
    --stock-recovery "C:\\path\\to\\recovery-sign.img" ^
    --twrp-recovery "C:\\path\\to\\ac101box-twrp.img" ^
    --magiskboot "C:\\path\\to\\magiskboot.exe" ^
    --output "C:\\path\\to\\output-recovery.img"
        """,
    )
    parser.add_argument(
        "--stock-recovery",
        required=True,
        type=str,
        help="Path to original ARC80OX stock recovery image",
    )
    parser.add_argument(
        "--twrp-recovery",
        required=True,
        type=str,
        help="Path to AC101BOX TWRP recovery image (as base)",
    )
    parser.add_argument(
        "--magiskboot",
        required=True,
        type=str,
        help="Path to magiskboot executable",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=str,
        help="Path to save the ported recovery image",
    )
    parser.add_argument(
        "--workdir",
        type=str,
        default="work_twrp",
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
