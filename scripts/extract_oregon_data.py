#!/usr/bin/env python3
"""
Extract the full Oregon geopackage from the compressed archive.

This script extracts data/archive/preliminary_or_field_geopackage.7z
to create data/preliminary_or_field_geopackage.gpkg (23GB uncompressed).

Usage:
    python scripts/extract_oregon_data.py
"""

import os
import sys
import subprocess
from pathlib import Path


def check_7z_installed():
    """Check if 7z is installed"""
    try:
        result = subprocess.run(['7z', '--help'], 
                              capture_output=True, 
                              timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_file_size_gb(path):
    """Get file size in GB"""
    if not path.exists():
        return 0
    size_bytes = path.stat().st_size
    return size_bytes / (1024 ** 3)


def main():
    # Get project root
    project_root = Path(__file__).parent.parent
    
    # File paths
    archive_file = project_root / "data" / "archive" / "preliminary_or_field_geopackage.7z"
    output_file = project_root / "data" / "preliminary_or_field_geopackage.gpkg"
    
    print("=" * 70)
    print("SmartTap Oregon Data Extraction")
    print("=" * 70)
    print()
    
    # Check if 7z is installed
    if not check_7z_installed():
        print("❌ ERROR: 7-Zip is not installed")
        print()
        print("Please install 7-Zip:")
        print("  macOS:   brew install p7zip")
        print("  Linux:   sudo apt install p7zip-full")
        print("  Windows: Download from https://www.7-zip.org/")
        sys.exit(1)
    
    print("✓ 7-Zip is installed")
    
    # Check if archive exists
    if not archive_file.exists():
        print(f"❌ ERROR: Archive file not found")
        print(f"   Expected: {archive_file}")
        print()
        print("Please ensure preliminary_or_field_geopackage.7z is in data/archive/")
        sys.exit(1)
    
    archive_size = get_file_size_gb(archive_file)
    print(f"✓ Archive file found ({archive_size:.1f} GB)")
    
    # Check if already extracted
    if output_file.exists():
        output_size = get_file_size_gb(output_file)
        print(f"✓ Output file already exists ({output_size:.1f} GB)")
        print()
        
        response = input("File already extracted. Re-extract? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("Extraction skipped.")
            print()
            print("✓ Ready to use! Run: python smarttap.py \"What crops are grown in Corvallis?\"")
            return
        
        print("Removing existing file...")
        output_file.unlink()
    
    # Extract
    print()
    print(f"Extracting to: {output_file}")
    print("This will take 10-20 minutes and create a ~23 GB file...")
    print()
    
    try:
        # Run 7z extraction
        # -o specifies output directory (data/)
        # -aoa means overwrite all
        cmd = [
            '7z', 'x',
            str(archive_file),
            f'-o{output_file.parent}',
            '-aoa'
        ]
        
        result = subprocess.run(cmd, check=True)
        
        if result.returncode == 0 and output_file.exists():
            output_size = get_file_size_gb(output_file)
            print()
            print("=" * 70)
            print(f"✓ SUCCESS! Extracted {output_size:.1f} GB")
            print("=" * 70)
            print()
            print("Next steps:")
            print("  1. Test it: python smarttap.py \"What crops are grown in Corvallis?\"")
            print("  2. Or query: python smarttap.py \"Show ETa in Hood River in 2023\"")
            print()
        else:
            print("❌ Extraction failed - output file not found")
            sys.exit(1)
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Extraction failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        print("⚠️  Extraction interrupted")
        if output_file.exists():
            print("Cleaning up partial file...")
            output_file.unlink()
        sys.exit(1)


if __name__ == "__main__":
    main()
