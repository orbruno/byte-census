# Duplicate Finder CLI

A fast, reliable command-line tool for finding duplicate files using cryptographic hashing (SHA256).

## Features

- **Hash-based detection**: Uses SHA256 for accurate duplicate identification regardless of filename
- **Efficient processing**: Chunked file reading handles large files (GB+) without memory issues
- **Two modes**:
  - **Single directory**: Find duplicates within one folder
  - **Compare mode**: Find duplicates between two directories
- **Multiple output formats**: Table (human-readable), JSON (machine-readable), CSV (spreadsheet-compatible)
- **Flexible filtering**: Recursive/non-recursive search, minimum file size threshold
- **Rich terminal output**: Color-coded results, progress tracking, summary statistics

## Installation

### Using UV (Recommended)

```bash
cd duplicate-finder-cli
uv sync
```

This will:
- Create a virtual environment
- Install all dependencies
- Make the `dupfind` command available

### Manual Installation

```bash
cd duplicate-finder-cli
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

## Usage

### Basic Usage

Find duplicates in the current directory:
```bash
dupfind .
```

Find duplicates in a specific directory:
```bash
dupfind /Users/orlando/Downloads
```

### Compare Two Directories

Find files that exist in both directories:
```bash
dupfind /path/folder1 --compare /path/folder2
dupfind ~/Documents --compare ~/Backup/Documents
```

### Search Options

**Non-recursive search** (don't scan subdirectories):
```bash
dupfind /path --no-recursive
```

**Ignore small files** (e.g., smaller than 1MB):
```bash
dupfind /path --min-size 1048576
```

**Quiet mode** (suppress progress bars):
```bash
dupfind /path --quiet
```

### Output Formats

**Table format** (default, human-readable):
```bash
dupfind /path
dupfind /path --format table
```

**JSON format** (for scripting and automation):
```bash
dupfind /path --format json
dupfind /path --format json --output results.json
```

**CSV format** (for spreadsheets):
```bash
dupfind /path --format csv
dupfind /path --format csv --output duplicates.csv
```

### Combined Examples

```bash
# Find large duplicate images (>100KB) in Photos, save as JSON
dupfind ~/Photos --min-size 102400 --format json --output photo-dups.json

# Compare two backup folders, non-recursive, CSV output
dupfind ~/Backup/2024 --compare ~/Backup/2025 --no-recursive --format csv

# Find all duplicates recursively, quiet mode, save results
dupfind ~/Documents --quiet --format json --output ~/docs-duplicates.json
```

## Output Examples

### Table Format
```
Found 3 duplicate groups (6 files, 45.2 MB wasted):

Hash: a3f5b8c... (3 files, 15.4 MB each)
  /Users/orlando/Downloads/report.pdf
  /Users/orlando/Documents/report.pdf
  /Users/orlando/Desktop/report-copy.pdf

Hash: 9d2e1f4... (2 files, 7.2 MB each)
  /Users/orlando/Photos/IMG_001.jpg
  /Users/orlando/Photos/backup/IMG_001.jpg
```

### JSON Format
```json
{
  "summary": {
    "duplicate_groups": 3,
    "duplicate_files": 6,
    "wasted_bytes": 47448064,
    "wasted_human": "45.2 MB"
  },
  "duplicates": {
    "a3f5b8c...": {
      "count": 3,
      "size": 16140288,
      "files": [
        "/Users/orlando/Downloads/report.pdf",
        "/Users/orlando/Documents/report.pdf",
        "/Users/orlando/Desktop/report-copy.pdf"
      ]
    }
  }
}
```

### CSV Format
```csv
hash,file_count,size_bytes,file_path
a3f5b8c...,3,16140288,/Users/orlando/Downloads/report.pdf
a3f5b8c...,3,16140288,/Users/orlando/Documents/report.pdf
a3f5b8c...,3,16140288,/Users/orlando/Desktop/report-copy.pdf
```

## Command Reference

```
Usage: dupfind [OPTIONS] PATH

  Find duplicate files using cryptographic hashing.

  PATH is the directory to scan for duplicates.

Options:
  -c, --compare PATH              Compare with another directory
  -r, --recursive / -R, --no-recursive
                                  Search recursively (default: recursive)
  -f, --format [table|json|csv]   Output format (default: table)
  -o, --output PATH               Save results to file
  --min-size INTEGER              Minimum file size in bytes (default: 0)
  -q, --quiet                     Suppress progress output
  --help                          Show this message and exit
```

## How It Works

1. **File Collection**: Scans the specified directory for files, optionally recursively
2. **Hash Calculation**: Computes SHA256 hash for each file using chunked reading (8KB chunks)
3. **Duplicate Detection**: Groups files by hash; files with identical hashes are duplicates
4. **Statistics**: Calculates wasted space (duplicate files × file size)
5. **Output**: Presents results in requested format

### Why SHA256?

- **Collision-resistant**: Virtually impossible for two different files to have the same hash
- **Industry standard**: Widely used for file integrity verification
- **Fast**: Optimized implementations in Python's `hashlib`
- **Reliable**: Works on any file type (images, documents, videos, etc.)

## Technical Details

- **Language**: Python 3.11+
- **Dependencies**: Click (CLI), Rich (terminal output)
- **Hash Algorithm**: SHA256
- **Memory Efficiency**: Chunked file reading (handles GB+ files)
- **Symlinks**: Skipped by default (prevents double-counting)
- **Performance**: ~100-200 files/second on typical hardware

## Specification

See [SPECIFICATION.md](SPECIFICATION.md) for the complete specification, test cases, and design rationale.

## Use Cases

- **Clean up Downloads folder**: Find and remove duplicate downloads
- **Backup verification**: Compare backup directories to ensure completeness
- **Photo library**: Find duplicate photos across different folders
- **Storage audit**: Identify wasted disk space from duplicates
- **Archive management**: Deduplicate before archiving to save space

## Limitations

- **Read-only**: Does not delete files (by design for safety)
- **Symlinks**: Skipped by default
- **Hidden files**: Included in scan (use .gitignore-like exclusions in future version)
- **Large directories**: May take time to hash thousands of files

## Roadmap (Future Enhancements)

- [ ] Interactive deletion mode with preview
- [ ] Auto-deletion with keep strategy (newest/oldest/smallest/largest)
- [ ] Parallel hashing for speed (multiprocessing)
- [ ] Exclude patterns (e.g., `--exclude "*.tmp"`)
- [ ] Dry-run mode for deletion operations
- [ ] Follow symlinks option

## Author

**Orlando Bruno**

## License

MIT License (or specify your preferred license)

---

**Built with specification-first development** - See [SPECIFICATION.md](SPECIFICATION.md) for details
