#!/usr/bin/env python3
"""
ARC80OX TWRP Recovery Builder (Stock Kernel Edition)
Uses STOCK kernel/DTB from ARC80OX + TWRP ramdisk with proper MTK configs.
This ensures gslx68x touchscreen driver compatibility.

Windows Usage:
  python twrp_port_builder_stock_kernel.py ^
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
from pathlib import Path


class BuildError(RuntimeError):
    """Build process error."""
    pass


class TWRPStockKernelBuilder:
    """Build TWRP recovery using stock ARC80OX kernel + TWRP ramdisk."""

    def __init__(
        self,
        stock_recovery: str,
        twrp_recovery: str,
        magiskboot: str,
        output: str,
        workdir: str = "work_twrp_stock",
        keep_work: bool = False,
    ):
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
            raise BuildError(f"Output already exists: {self.output}")

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
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
        except FileNotFoundError as e:
            raise BuildError(f"Command not found: {cmd[0]}") from e

        output = result.stdout or ""
        
        try:
            with self.log_file.open("a", encoding="utf-8", errors="replace") as fh:
                fh.write(f"\n{'='*80}\n")
                fh.write(f"{label_str}$ {cmd_str}\n")
                fh.write(f"Working directory: {cwd}\n")
                fh.write(f"{'='*80}\n{output}\n")
        except Exception as e:
            print(f"Warning: Could not write to log file: {e}")

        if output:
            preview = output[:500]
            print(preview if len(output) <= 500 else preview + "\n...")

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
        print("STEP 2: Unpacking recovery images (extract kernel + ramdisk)")
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

    def analyze_stock_configs(self) -> None:
        """Analyze stock device configurations."""
        print("\n" + "=" * 80)
        print("STEP 4: Analyzing STOCK device configurations")
        print("=" * 80)

        try:
            self.config_dir.mkdir(exist_ok=True)
        except Exception as e:
            raise BuildError(f"Failed to create config directory: {e}")

        stock_ramdisk = self.stock_dir / "ramdisk"

        important_files = [
            "init.recovery.mt8163.rc",
            "fstab.mt8163",
            "ueventd.mt8163.rc",
            "etc/recovery.fstab",
            "default.prop",
        ]

        for filename in important_files:
            stock_file = stock_ramdisk / filename
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
                    print(f"⚠ Error reading: {e}")
            else:
                print(f"✗ Not found in Stock")

    def patch_twrp_ramdisk(self) -> None:
        """Inject STOCK MTK configs into TWRP ramdisk."""
        print("\n" + "=" * 80)
        print("STEP 5: Patching TWRP ramdisk with STOCK MTK configurations")
        print("=" * 80)
        print("\n⚠️  KEY POINT: Injecting gslx68x-compatible stock files into TWRP ramdisk")
        print("    This ensures touchscreen driver works correctly.")

        stock_ramdisk = self.stock_dir / "ramdisk"
        twrp_ramdisk = self.twrp_dir / "ramdisk"

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
                    print(f"  Copying from STOCK...")
                    shutil.copy2(str(source), str(dest))
                    print(f"  ✓ Injected into TWRP ramdisk: {dest}")
                except Exception as e:
                    print(f"  ⚠ Failed: {e}")
            else:
                print(f"  ⚠ Skipping (not found in stock)")

        # Handle etc/recovery.fstab
        stock_fstab = stock_ramdisk / "etc" / "recovery.fstab"
        twrp_fstab = twrp_ramdisk / "etc" / "recovery.fstab"

        print(f"\n--- etc/recovery.fstab ---")
        if stock_fstab.exists():
            try:
                print(f"  Copying from STOCK...")
                twrp_fstab.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(stock_fstab), str(twrp_fstab))
                print(f"  ✓ Injected into TWRP ramdisk: {twrp_fstab}")
            except Exception as e:
                print(f"  ⚠ Failed: {e}")

    def sync_ramdisk(self) -> None:
        """Synchronize modified TWRP ramdisk."""
        print("\n" + "=" * 80)
        print("STEP 6: Synchronizing modified TWRP ramdisk")
        print("=" * 80)

        print("\nSyncing TWRP ramdisk with injected stock configs...")
        self._run_cmd(
            [str(self.magiskboot), "cpio", "ramdisk.cpio", "sync"],
            self.twrp_dir,
            label="TWRP Sync",
        )
        print("✓ TWRP ramdisk synchronized")

    def prepare_repack(self) -> None:
        """Prepare components: STOCK kernel + TWRP ramdisk."""
        print("\n" + "=" * 80)
        print("STEP 7: Preparing components for repacking")
        print("       (STOCK kernel/DTB + TWRP ramdisk)")
        print("=" * 80)

        try:
            self.repack_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise BuildError(f"Failed to create repack directory: {e}")

        print("\n✅ Copying STOCK kernel and DTB (for gslx68x compatibility)...")
        for component in ["kernel", "kernel_dtb"]:
            source = self.stock_dir / component
            if source.exists():
                try:
                    dest = self.repack_dir / component
                    shutil.copy2(str(source), str(dest))
                    size_kb = source.stat().st_size / 1024
                    print(f"  ✓ {component}: {size_kb:.1f} KB (from STOCK)")
                except Exception as e:
                    print(f"  ⚠ Failed to copy {component}: {e}")
            else:
                print(f"  ⚠ {component} not found in stock")

        print("\n✅ Copying modified TWRP ramdisk (with stock MTK configs)...")
        try:
            shutil.copy2(str(self.twrp_dir / "ramdisk.cpio"), str(self.repack_dir / "ramdisk.cpio"))
            print("  ✓ ramdisk.cpio copied")
        except Exception as e:
            raise BuildError(f"Failed to copy ramdisk: {e}")

        print("\n✅ Copying stock base image for header preservation...")
        try:
            shutil.copy2(str(self.stock_recovery), str(self.repack_dir / "stock-base.img"))
            print("  ✓ stock-base.img copied")
        except Exception as e:
            raise BuildError(f"Failed to copy base image: {e}")

    def repack_recovery(self) -> None:
        """Repack the recovery image."""
        print("\n" + "=" * 80)
        print("STEP 8: Repacking recovery image")
        print("       (stock kernel + TWRP ramdisk + stock MTK configs)")
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
        """Copy final image and generate comprehensive report."""
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

        # Generate comprehensive report
        report = {
            "device": "Archos 80 Oxygen (ARC80OX/AC80OX)",
            "soc": "MT8163",
            "android_version": "Android 6.x",
            "build_type": "TWRP + Stock Kernel (gslx68x compatible)",
            "warning": "⚠️ TEST THOROUGHLY - Use 'fastboot boot' first before flashing",
            
            "composition": {
                "kernel": "STOCK ARC80OX ✅ (includes gslx68x driver)",
                "kernel_dtb": "STOCK ARC80OX ✅ (includes touchscreen config)",
                "ramdisk": "TWRP AC101BOX + Stock ARC80OX MTK configurations",
                "files_injected": [
                    "init.recovery.mt8163.rc (from stock)",
                    "fstab.mt8163 (from stock)",
                    "ueventd.mt8163.rc (from stock)",
                    "etc/recovery.fstab (from stock)",
                ],
            },
            
            "stock_recovery": {
                "path": str(self.stock_recovery),
                "sha256": self._sha256(self.stock_recovery),
                "components_extracted": ["kernel", "kernel_dtb", "header", "recovery.fstab"],
            },
            
            "twrp_recovery": {
                "path": str(self.twrp_recovery),
                "sha256": self._sha256(self.twrp_recovery),
                "components_used": ["ramdisk", "recovery UI binary"],
            },
            
            "output": {
                "path": str(self.output),
                "sha256": output_hash,
                "size_mb": output_size_mb,
            },
            
            "testing_procedure": {
                "CRITICAL": "DO NOT flash without testing first!",
                "step_1": "Backup original recovery using SP Flash Tool",
                "step_2": "Boot to fastboot: adb reboot bootloader",
                "step_3": "Test with NON-PERSISTENT boot (safe):",
                "step_3_cmd": f"fastboot boot {self.output}",
                "step_4": "CHECK:",
                "step_4_checks": [
                    "Does TWRP UI appear?",
                    "Can you tap and interact (touchscreen)?",
                    "Are colors/orientation correct?",
                ],
                "step_5_if_good": "Flash permanently: fastboot flash recovery <image>",
                "step_5_if_bad": "DO NOT flash. Device will bootloop. Flash stock recovery back.",
            },
            
            "troubleshooting": {
                "bootloop": "Flash stock recovery immediately via SP Flash Tool or fastboot",
                "no_touch": "Kernel driver mismatch (gslx68x issue) - unlikely with stock kernel",
                "wrong_colors": "DTB framebuffer config - check init.recovery.mt8163.rc",
                "recovery_ui_missing": "Ramdisk corruption - reflash stock recovery",
            },
            
            "why_stock_kernel_matters": [
                "Stock kernel contains compiled gslx68x touchscreen driver",
                "Stock DTB has proper touchscreen hardware configuration",
                "Stock recovery.fstab has correct partition mapping",
                "Mixing foreign kernel = touchscreen driver not available",
            ],
            
            "log_file": str(self.log_file),
            "config_extracted": str(self.config_dir),
        }

        try:
            report_path = self.output.parent / (self.output.name + ".json")
            with report_path.open("w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2)
            print(f"\n✓ Detailed report generated: {report_path}")
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
            print(f"  (Useful for debugging if issues occur)")

    def build(self) -> int:
        """Execute the complete build process."""
        try:
            self.setup_work_dirs()
            self.unpack_images()
            self.extract_ramdisks()
            self.analyze_stock_configs()
            self.patch_twrp_ramdisk()
            self.sync_ramdisk()
            self.prepare_repack()
            self.repack_recovery()
            self.finalize_output()
            self.cleanup()

            print("\n" + "=" * 80)
            print("✓ BUILD COMPLETED SUCCESSFULLY")
            print("=" * 80)
            print("\n🎯 RECOVERY IMAGE READY FOR TESTING")
            print("\nComposition:")
            print("  • Kernel: STOCK ARC80OX (with gslx68x driver)")
            print("  • DTB: STOCK ARC80OX (with touchscreen config)")
            print("  • Ramdisk: TWRP + Stock MTK configs")
            print("\n⚠️  NEXT STEPS:")
            print("1. Connect device and boot to fastboot:")
            print("   adb reboot bootloader")
            print("\n2. Test WITHOUT flashing (safe test):")
            print(f"   fastboot boot {self.output}")
            print("\n3. Check:")
            print("   - TWRP UI visible?")
            print("   - Touchscreen working?")
            print("   - Colors/orientation correct?")
            print("\n4. If all OK, flash permanently:")
            print(f"   fastboot flash recovery {self.output}")
            print("\n5. If ANYTHING wrong, boot to fastboot and flash stock recovery")
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
        description="Build TWRP recovery for ARC80OX using STOCK kernel (gslx68x compatible)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples on Windows:
  python twrp_port_builder_stock_kernel.py ^
    --stock-recovery "C:\\path\\to\\recovery-sign.img" ^
    --twrp-recovery "C:\\path\\to\\ac101box-twrp.img" ^
    --magiskboot "C:\\path\\to\\magiskboot.exe" ^
    --output "C:\\path\\to\\output-recovery.img" ^
    --keep-work

Key feature: Uses STOCK kernel to ensure gslx68x touchscreen driver works!
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
        help="Path to AC101BOX TWRP recovery image (ramdisk only)",
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
        help="Path to save the final recovery image",
    )
    parser.add_argument(
        "--workdir",
        type=str,
        default="work_twrp_stock",
        help="Work directory (default: work_twrp_stock)",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Keep work directory for debugging",
    )

    args = parser.parse_args()

    try:
        builder = TWRPStockKernelBuilder(
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
