# Duplicate Finder CLI - Specification

---
**Version**: 1.0.0
**Created**: 2025-12-20
**Author**: Orlando Bruno
**Status**: Implementation Ready

---

## Intent

Create a command-line tool that identifies duplicate files within a directory or compares files between two directories using cryptographic hashing. The tool should be fast, reliable, and provide multiple output formats for different use cases (manual review, automated processing, interactive cleanup).

## Core Problem

Users accumulate duplicate files across their filesystem, wasting storage space and creating organizational clutter. Manually identifying duplicates is time-consuming and error-prone. Filename-based comparison is unreliable (files can be renamed). Need byte-level comparison that's efficient for large files.

## Success Criteria

### Functional Requirements

1. **Duplicate Detection**
   - ✅ Correctly identifies files with identical content regardless of filename
   - ✅ Uses SHA256 hashing for collision-resistant comparison
   - ✅ Processes files efficiently (chunked reading, no full file in memory)
   - ✅ Handles large files (GB+) without performance degradation

2. **Operating Modes**
   - ✅ Single directory mode: Find duplicates within one folder
   - ✅ Compare mode: Find duplicates between two folders
   - ✅ Recursive search by default, optional non-recursive
   - ✅ File size filtering (ignore small files below threshold)

3. **Output Formats**
   - ✅ Table format (human-readable, default)
   - ✅ JSON format (machine-readable, for scripting)
   - ✅ CSV format (spreadsheet-compatible)
   - ✅ Optional file output (save results to disk)

4. **User Experience**
   - ✅ Clear progress indicators for long operations
   - ✅ Summary statistics (files scanned, duplicates found, wasted space)
   - ✅ Color-coded output for readability
   - ✅ Helpful error messages

### Non-Functional Requirements

1. **Performance**
   - Process 1000 files in under 10 seconds (typical case)
   - Memory usage scales with number of unique files, not total files
   - Skip already-hashed files when possible (size pre-check)

2. **Reliability**
   - Handle permission errors gracefully
   - Skip symlinks by default (avoid infinite loops)
   - Validate paths before processing
   - No data loss (read-only by default)

3. **Compatibility**
   - Python 3.11+
   - Cross-platform (macOS, Linux, Windows)
   - No external binary dependencies

## Technical Design

### Algorithm

```
For Single Directory Mode:
1. Collect all file paths (recursive or non-recursive)
2. Filter by minimum size threshold
3. For each file:
   a. Read file in 8KB chunks
   b. Calculate SHA256 hash incrementally
   c. Store hash -> [file_paths] mapping
4. Return only hashes with >1 file path (duplicates)
5. Calculate statistics (total duplicates, wasted bytes)

For Compare Mode:
1. Hash all files in directory A
2. Hash all files in directory B
3. Find intersection of hash sets
4. Return files from both directories sharing same hash
```

### Data Structures

```python
# Hash mapping
duplicates: dict[str, list[Path]] = {
    "sha256_hash_1": [Path("/path/file1.txt"), Path("/path/copy.txt")],
    "sha256_hash_2": [Path("/path/image.jpg"), Path("/other/img.jpg")],
}

# File metadata
FileInfo = {
    "path": Path,
    "hash": str,
    "size": int,
    "modified": datetime,
}
```

### Command-Line Interface

```bash
# Basic usage - find duplicates in current directory
dupfind .

# Find duplicates in specific directory
dupfind /Users/orlando/Downloads

# Non-recursive search
dupfind /path --no-recursive

# Compare two directories
dupfind /path/folder1 --compare /path/folder2

# Ignore small files (< 1MB)
dupfind /path --min-size 1048576

# Output formats
dupfind /path --format table    # Default: pretty table
dupfind /path --format json     # JSON output
dupfind /path --format csv      # CSV output

# Save to file
dupfind /path --output results.json --format json

# Quiet mode (only show results, no progress)
dupfind /path --quiet
```

### Dependencies

- **click**: CLI framework (argument parsing, options)
- **rich**: Beautiful terminal output (tables, progress bars, colors)

### File Structure

```
duplicate-finder-cli/
├── SPECIFICATION.md          # This file (source of truth)
├── README.md                 # User documentation
├── pyproject.toml            # Package configuration
├── .gitignore                # Git exclusions
├── uv.lock                   # Dependency lockfile
└── duplicate_finder_cli/
    ├── __init__.py           # Package marker
    └── main.py               # CLI implementation
```

## Test Cases

### Test 1: Basic Duplicate Detection
**Input**: Directory with 3 identical files (different names)
```
/test/
  file1.txt (content: "hello world")
  file2.txt (content: "hello world")
  file3.txt (content: "goodbye")
```
**Expected**: 1 duplicate group with 2 files (file1.txt, file2.txt)

### Test 2: No Duplicates
**Input**: Directory with unique files only
**Expected**: Output "No duplicates found"

### Test 3: Compare Mode
**Input**: Two directories with some overlapping files
```
/dir1/: [a.txt, b.txt, c.txt]
/dir2/: [a.txt, x.txt, y.txt]
```
**Expected**: Report a.txt as duplicate between directories (if content matches)

### Test 4: Large File Handling
**Input**: Files >100MB
**Expected**: Process without memory errors, complete in reasonable time

### Test 5: Permission Errors
**Input**: Directory with unreadable files
**Expected**: Skip unreadable files, continue processing, report errors at end

### Test 6: Size Filtering
**Input**: `dupfind /path --min-size 1000`
**Expected**: Only process files ≥1000 bytes

## Edge Cases

1. **Empty directory**: Return "No files found"
2. **Single file**: Return "No duplicates possible"
3. **Symlinks**: Skip by default (prevent double-counting and infinite loops)
4. **Binary identical but different extensions**: Still consider duplicates (hash-based)
5. **Very large files (10GB+)**: Use chunked reading, don't load into memory
6. **Unicode filenames**: Handle properly on all platforms

## Output Examples

### Table Format (Default)
```
Found 3 duplicate groups (6 files, 45.2 MB wasted):

Hash: a3f5b8c... (3 files, 15.4 MB each)
  /Users/orlando/Downloads/report.pdf
  /Users/orlando/Documents/report.pdf
  /Users/orlando/Desktop/report-copy.pdf

Hash: 9d2e1f4... (2 files, 7.2 MB each)
  /Users/orlando/Photos/IMG_001.jpg
  /Users/orlando/Photos/backup/IMG_001.jpg

Hash: 4c8a9b2... (2 files, 512 KB each)
  /Users/orlando/file.txt
  /Users/orlando/old/file-backup.txt
```

### JSON Format
```json
{
  "summary": {
    "files_scanned": 1250,
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

## Future Enhancements (v2.0)

- Interactive deletion mode (`--interactive-delete`)
- Auto-deletion with keep strategy (`--auto-delete --keep newest`)
- Parallel hashing (multiprocessing for speed)
- Progress bar for large operations
- Exclude patterns (`--exclude "*.tmp"`)
- Follow symlinks option (`--follow-symlinks`)
- Dry-run mode for deletion operations

## References

- SHA256: https://en.wikipedia.org/wiki/SHA-2
- Click documentation: https://click.palletsprojects.com/
- Rich documentation: https://rich.readthedocs.io/

---

**This specification is the source of truth for the duplicate-finder-cli implementation. Code should be generated from this spec and validated against these success criteria.**
