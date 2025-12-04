# Fuzzy Matcher V7.4.1 - GSS ↔ Opera

A PyQt6-based desktop application for fuzzy matching between GSS (Guest Satisfaction Survey) and Opera PMS (Property Management System) data files.

## Features

- **Multiple Fuzzy Matching Algorithms**: 
  - Ensemble (recommended - combines multiple algorithms)
  - Weighted Ratio
  - Partial Ratio
  - Jaro-Winkler
  - Semantic Matching (ML-based)
  - Record Linkage (statistical/probabilistic)
  - Double Metaphone (phonetic matching)

- **Auto Column Mapping**: Automatically detects and maps columns from GSS and Opera files
- **Data Preview**: Preview first 5 rows of loaded data in Excel-like format
- **Date Tolerance**: Configurable date matching with tolerance (0-7 days)
- **Multi-Pass Matching**: Iterative matching with increasing leniency for better coverage
- **Algorithm Comparison**: Run all algorithms and export results to separate Excel workbooks for comparison
- **Excel Export**: Color-coded results with confidence levels (High, Medium, Low, Very Low, No Match)
- **Plugin System**: Extensible plugin architecture for custom post-processing

## Requirements

- Python 3.8+
- See `requirements.txt` for dependencies

## Installation

1. Clone this repository:
```bash
git clone <your-repo-url>
cd fuzzy_matcher_pyqt_v7_4_1_full
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the application:
```bash
python main.py
```

### Basic Workflow

1. **Load Files**:
   - Click "Browse" to select your GSS file (Excel format)
   - Click "Browse" to select your Opera file (Excel or TXT log format)

2. **Column Mapping**:
   - The application will attempt to auto-detect columns
   - Manually adjust if needed using the dropdown menus
   - Click "Hide Column Mapping" to collapse the mapping section

3. **Configure Matching**:
   - Select algorithm (Ensemble recommended)
   - Set threshold (default: 85)
   - Set date tolerance (0-7 days)
   - Choose "Show all matches" if you want multiple matches per GSS row

4. **Run Match**:
   - Click "Run Match" for single algorithm
   - Or check "Run All Algorithms & Export Comparison" to compare all algorithms

5. **Export**:
   - Set export folder and base filename
   - Results are automatically exported to Excel format

## Supported File Formats

### GSS Files
- Excel (.xlsx, .xls)
- Headers may start from row 3
- Supports "NAME" column that gets auto-split into "First name" and "Last name"

### Opera Files
- Excel (.xlsx, .xls)
- Text log files (.txt) with format:
  ```
  USERID,00:00,DD/MM/YY,ROOM,ACTION,Last, First has checked in...
  ```

## Algorithm Details

### Ensemble (Recommended)
Combines multiple fuzzy matching algorithms:
- Jaro-Winkler (35% weight) - best for names with typos
- Weighted Ratio (30% weight) - general purpose
- Token Sort Ratio (20% weight) - handles word order
- Partial Ratio (15% weight) - substring matching

### Semantic Matching
Uses sentence-transformers (paraphrase-MiniLM-L6-v2) for semantic similarity.

### Record Linkage
Statistical/probabilistic matching using the recordlinkage library.

### Double Metaphone
Advanced phonetic matching for names with different spellings.

## Configuration

Settings are saved in `config.json` in the application directory. You can access settings via the "Settings" button in the UI.

## Plugins

The application supports plugins for custom export formatting and post-processing. Plugins are located in `matcher/plugins/`.

## License

[Add your license here]

## Contributing

[Add contribution guidelines if desired]

## Author

[Add your name/info here]

