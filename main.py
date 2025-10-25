#!/usr/bin/env python3
"""
Main script for Enhanced Sankey Chart with CSV data input and group-based color coding
"""

import argparse
import os
import sys
from pathlib import Path
import pandas as pd
from enhanced_sankey import EnhancedSankeyChart, create_enhanced_sankey_from_csv


def main():
    """Main function to run the enhanced Sankey chart generator"""
    parser = argparse.ArgumentParser(
        description="Generate Enhanced Sankey Charts from CSV data with group-based color coding"
    )
    
    parser.add_argument(
        "--data", "-d",
        type=str,
        default="data.csv",
        help="Path to the CSV data file (default: data.csv)"
    )
    
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="color_config.json",
        help="Path to the color configuration file (default: color_config.json)"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="enhanced_sankey_chart.html",
        help="Output HTML file name (default: enhanced_sankey_chart.html)"
    )
    
    parser.add_argument(
        "--title", "-t",
        type=str,
        default="Enhanced Sankey Chart",
        help="Chart title (default: Enhanced Sankey Chart)"
    )
    
    parser.add_argument(
        "--show-summary",
        action="store_true",
        help="Show color assignment summary"
    )
    
    parser.add_argument(
        "--create-sample",
        action="store_true",
        help="Create sample data and configuration files"
    )
    
    args = parser.parse_args()
    
    # Create sample files if requested
    if args.create_sample:
        create_sample_files()
        print("✅ Sample files created!")
        print("  - data.csv: Sample data file")
        print("  - color_config.json: Sample color configuration")
        return
    
    # Check if data file exists
    if not os.path.exists(args.data):
        print(f"❌ Data file not found: {args.data}")
        print("Use --create-sample to create sample files, or provide a valid data file.")
        return
    
    # Check if config file exists
    if not os.path.exists(args.config):
        print(f"❌ Config file not found: {args.config}")
        print("Use --create-sample to create sample files, or provide a valid config file.")
        return
    
    try:
        # Create the enhanced Sankey chart
        print(f"📊 Loading data from {args.data}...")
        chart = EnhancedSankeyChart(args.config)
        
        if not chart.load_data_from_csv(args.data):
            print("❌ Failed to load data from CSV file")
            return
        
        print("✅ Data loaded successfully!")
        
        # Show summary if requested
        if args.show_summary:
            show_color_summary(chart)
        
        # Create the chart
        print(f"🎨 Creating chart: {args.title}")
        fig = chart.create_chart(args.title)
        
        # Save the chart with post-processing
        html_content = fig.to_html()
        processed_html = chart._post_process_html(html_content)
        
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(processed_html)
        print(f"✅ Chart saved as: {args.output}")
        
        # Show data summary
        show_data_summary(chart)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def create_sample_files():
    """Create sample data and configuration files"""
    # Create sample data
    sample_data = pd.DataFrame({
        'Source': [
            'Portfolio A', 'Portfolio B', 'Portfolio A', 'Portfolio B',
            'Strategy X', 'Strategy Y', 'Portfolio C', 'Portfolio C',
            'Portfolio D', 'Portfolio D', 'Fixed Income Credit',
            'Alternative Investments Fund', 'Technology Infrastructure',
            'Operations Management'
        ],
        'Target': [
            'Strategy X', 'Strategy Y', 'Global Macro Strategy', 'Global Equity Long/Short',
            'Global Macro Strategy', 'Quantitative Research Alpha', 'Fixed Income Credit',
            'Alternative Investments Fund', 'Technology Infrastructure', 'Operations Management',
            'Global Macro Strategy', 'Global Equity Long/Short', 'Quantitative Research Alpha',
            'Risk Management Systems'
        ],
        'Value': [100, 150, 200, 180, 300, 230, 120, 90, 110, 85, 120, 90, 110, 85]
    })
    
    sample_data.to_csv('data.csv', index=False)
    
    # Create sample color config
    import json
    sample_config = {
        "group_colors": {
            "Global Macro*": "#FF6B6B",
            "Global Equity*": "#4ECDC4",
            "Quantitative Research*": "#45B7D1",
            "Fixed Income*": "#96CEB4",
            "Alternative Investments*": "#FFEAA7",
            "Risk Management*": "#DDA0DD",
            "Technology*": "#98D8C8",
            "Operations*": "#F7DC6F"
        },
        "default_color": "#808080"
    }
    
    with open('color_config.json', 'w') as f:
        json.dump(sample_config, f, indent=2)


def show_color_summary(chart):
    """Show color assignment summary"""
    summary = chart.get_color_summary()
    
    print("\n🎨 Color Assignment Summary:")
    print("=" * 50)
    
    print(f"Total nodes: {summary['total_nodes']}")
    
    # Show by level
    print("\nBy Level:")
    for level in sorted(summary['by_level'].keys()):
        nodes = summary['by_level'][level]
        print(f"  Level {level} ({len(nodes)} nodes):")
        for node_info in nodes:
            group = chart.color_config.get_group_for_node(node_info['node'])
            group_str = f" ({group})" if group else " (Uncategorized)"
            print(f"    {node_info['node']}{group_str}: {node_info['color']}")
    
    # Show by group
    print("\nBy Group:")
    for group, nodes in summary['by_group'].items():
        print(f"  {group} ({len(nodes)} nodes):")
        for node_info in nodes:
            print(f"    {node_info['node']}: {node_info['color']}")


def show_data_summary(chart):
    """Show data summary"""
    if chart.data is not None:
        print(f"\n📈 Data Summary:")
        print("=" * 30)
        print(f"Total flows: {len(chart.data)}")
        print(f"Unique sources: {chart.data['Source'].nunique()}")
        print(f"Unique targets: {chart.data['Target'].nunique()}")
        print(f"Total value: {chart.data['Value'].sum():,.0f}")
        print(f"Average flow value: {chart.data['Value'].mean():,.0f}")


if __name__ == "__main__":
    main()
