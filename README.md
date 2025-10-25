# Sankey Chart Generator

A simple tool to generate Sankey charts from CSV data with group-based color coding and manual color overrides.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install pandas plotly
   ```

2. **Prepare your data:**
   - Edit `data.csv` with your Source, Target, Value data
   - Edit `color_config.json` to customize colors

3. **Generate chart:**
   ```bash
   python main.py
   ```

## Files

- `main.py` - Main script to generate charts
- `data.csv` - Your data file (Source, Target, Value columns)
- `color_config.json` - Color configuration
- `enhanced_sankey_chart.html` - Generated chart output

## Data Format

Your `data.csv` should have these columns:
```csv
Source,Target,Value
Portfolio A,Strategy X,100
Strategy X,Global Macro Strategy,200
```

## Color Configuration

Edit `color_config.json` to customize colors:

```json
{
  "group_colors": {
    "Global Macro*": "#FF6B6B",
    "Global Equity*": "#4ECDC4"
  },
  "manual_colors": {
    "Strategy Y": "#000000"
  },
  "default_color": "#808080"
}
```

- `group_colors`: Colors for nodes matching patterns (e.g., "Global Macro*")
- `manual_colors`: Specific colors for individual nodes
- `default_color`: Color for uncategorized nodes

## Usage

```bash
# Generate chart
python main.py

# Show color summary
python main.py --show-summary

# Use custom files
python main.py --data my_data.csv --config my_colors.json --output my_chart.html
```