"""
Enhanced Sankey Chart with Group-Based Color Coding
Implements the new color system with final level group colors and intermediate mixing
"""

import pandas as pd
import plotly.graph_objects as go
from typing import Dict, List, Set, Optional
from color_config import ColorConfig
from csv_data_loader import CSVDataLoader


class EnhancedSankeyChart:
    """Enhanced Sankey chart with group-based color coding and intermediate color mixing"""
    
    def __init__(self, color_config_path: str = "color_config.json"):
        """
        Initialize the enhanced Sankey chart
        
        Args:
            color_config_path: Path to the color configuration file
        """
        self.color_config = ColorConfig(color_config_path)
        self.data = None
        self.node_levels = {}
        self.node_colors = {}
        self.link_colors = []
    
    def load_data_from_csv(self, csv_path: str) -> bool:
        """
        Load data from CSV file
        
        Args:
            csv_path: Path to the CSV file
            
        Returns:
            bool: True if successful, False otherwise
        """
        loader = CSVDataLoader(csv_path)
        success = loader.load_data()
        
        if success:
            self.data = loader.get_data()
            self._analyze_data_structure()
            return True
        else:
            print("Error loading data:")
            for error in loader.get_validation_errors():
                print(f"  - {error}")
            return False
    
    def _analyze_data_structure(self):
        """Analyze the data structure to determine node levels and relationships"""
        if self.data is None:
            return
        
        # Get all unique nodes
        sources = set(self.data['Source'].unique())
        targets = set(self.data['Target'].unique())
        all_nodes = sources | targets
        
        # Determine node levels
        self.node_levels = self._determine_node_levels(all_nodes)
        
        # Calculate node flow totals
        self._calculate_node_flow_totals()
        
        # Calculate node colors based on the new system
        self._calculate_node_colors()
        
        # Calculate link colors
        self._calculate_link_colors()
    
    def _determine_node_levels(self, all_nodes: Set[str]) -> Dict[str, int]:
        """
        Determine the level of each node in the hierarchy
        
        Args:
            all_nodes: Set of all unique nodes
            
        Returns:
            dict: Mapping of node names to their levels
        """
        node_levels = {}
        
        # Start with sources (level 0)
        sources = set(self.data['Source'].unique())
        targets = set(self.data['Target'].unique())
        
        # Level 0: Pure sources (never appear as targets)
        level_0 = sources - targets
        for node in level_0:
            node_levels[node] = 0
        
        # Level 2: Pure targets (never appear as sources) - these are final level
        level_2 = targets - sources
        for node in level_2:
            node_levels[node] = 2
        
        # Level 1: Intermediate nodes (appear as both source and target)
        level_1 = sources & targets
        for node in level_1:
            node_levels[node] = 1
        
        return node_levels
    
    def _calculate_node_flow_totals(self):
        """Calculate total flow values for each node"""
        if self.data is None:
            return
        
        self.node_flow_totals = {}
        all_nodes = set(self.data['Source'].unique()) | set(self.data['Target'].unique())
        
        for node in all_nodes:
            # Calculate incoming flow (as target)
            incoming = self.data[self.data['Target'] == node]['Value'].sum()
            # Calculate outgoing flow (as source)  
            outgoing = self.data[self.data['Source'] == node]['Value'].sum()
            # Total flow is the maximum of incoming or outgoing
            self.node_flow_totals[node] = max(incoming, outgoing)
    
    def _calculate_node_colors(self):
        """Calculate colors for all nodes based on the new color system"""
        if self.data is None:
            return
        
        all_nodes = set(self.data['Source'].unique()) | set(self.data['Target'].unique())
        
        # Step 1: Check for manual color overrides first (from config)
        for node in all_nodes:
            if node in self.color_config.manual_colors:
                self.node_colors[node] = self.color_config.manual_colors[node]
        
        # Step 2: Assign colors to final level nodes (level 2) based on groups
        for node in all_nodes:
            if self.node_levels.get(node, 0) == 2 and node not in self.node_colors:
                self.node_colors[node] = self.color_config.get_node_color(node)
        
        # Step 3: Calculate colors for intermediate nodes (level 1) by mixing recipient colors
        for node in all_nodes:
            if self.node_levels.get(node, 0) == 1 and node not in self.node_colors:
                self.node_colors[node] = self._calculate_intermediate_color(node)
        
        # Step 4: Assign colors to source nodes (level 0) - use default or inherit from targets
        for node in all_nodes:
            if self.node_levels.get(node, 0) == 0 and node not in self.node_colors:
                self.node_colors[node] = self._calculate_source_color(node)
    
    def _calculate_intermediate_color(self, node: str) -> str:
        """
        Calculate color for an intermediate node by mixing its recipients' colors
        
        Args:
            node: Name of the intermediate node
            
        Returns:
            str: Mixed color as hex code
        """
        # Find all targets of this node
        node_targets = self.data[self.data['Source'] == node]
        
        if len(node_targets) == 0:
            return self.color_config.default_color
        
        # Get colors and weights for each target
        colors = []
        weights = []
        
        for _, row in node_targets.iterrows():
            target = row['Target']
            value = row['Value']
            
            # Get color for the target
            target_color = self.node_colors.get(target, self.color_config.default_color)
            colors.append(target_color)
            weights.append(value)
        
        # Mix the colors
        return self.color_config.mix_colors(colors, weights)
    
    def _calculate_source_color(self, node: str) -> str:
        """
        Calculate color for a source node
        
        Args:
            node: Name of the source node
            
        Returns:
            str: Color for the source node
        """
        # For now, use default color for source nodes
        # Could be enhanced to inherit from primary target or use a different strategy
        return self.color_config.default_color
    
    def _calculate_link_colors(self):
        """Calculate colors for all links based on target node colors"""
        if self.data is None:
            return
        
        self.link_colors = []
        for _, row in self.data.iterrows():
            target = row['Target']
            target_color = self.node_colors.get(target, self.color_config.default_color)
            self.link_colors.append(target_color)
    
    def create_chart(self, title: str = "Enhanced Sankey Chart") -> go.Figure:
        """
        Create the enhanced Sankey chart
        
        Args:
            title: Title for the chart
            
        Returns:
            go.Figure: Plotly figure object
        """
        if self.data is None:
            raise ValueError("No data loaded. Call load_data_from_csv() first.")
        
        # Get all unique nodes
        sources = self.data['Source'].unique()
        targets = self.data['Target'].unique()
        all_nodes = list(set(sources) | set(targets))
        
        # Create node mapping
        node_map = {node: i for i, node in enumerate(all_nodes)}
        
        # Prepare data for Plotly
        source_indices = [node_map[source] for source in self.data['Source']]
        target_indices = [node_map[target] for target in self.data['Target']]
        values = self.data['Value'].tolist()
        
        # Create node colors list in the correct order
        node_color_list = [self.node_colors.get(node, self.color_config.default_color) for node in all_nodes]
        
        # Create enhanced labels with flow totals
        enhanced_labels = []
        for node in all_nodes:
            flow_total = self.node_flow_totals.get(node, 0)
            if flow_total > 0:
                # Data is already in k€, just add the suffix
                enhanced_label = f"<b>{node}</b><br><span style='font-size:10px; font-weight:normal;'>{flow_total}k€</span>"
            else:
                enhanced_label = f"<b>{node}</b>"
            enhanced_labels.append(enhanced_label)
        
        # Create slightly transparent link colors
        transparent_link_colors = []
        for color in self.link_colors:
            # Convert hex to rgba with 70% opacity
            if color.startswith('#'):
                hex_color = color.lstrip('#')
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                transparent_color = f"rgba({r}, {g}, {b}, 0.7)"
            else:
                transparent_color = color
            transparent_link_colors.append(transparent_color)
        
        # Create the Sankey diagram with custom level positioning
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=35,
                thickness=30,
                line=dict(color="rgba(0,0,0,0)", width=0),
                label=enhanced_labels,
                color=node_color_list,
                hovertemplate='<b>%{label}</b><br>Value: %{value}<br>Level: %{customdata}<extra></extra>',
                customdata=[self.node_levels.get(node, 0) for node in all_nodes],
                x=self._calculate_node_positions(all_nodes),
                y=self._calculate_node_y_positions(all_nodes)
            ),
            link=dict(
                source=source_indices,
                target=target_indices,
                value=values,
                color=transparent_link_colors,
                line=dict(color="rgba(0,0,0,0)", width=0),
                hovertemplate='<b>%{source.label}</b> → <b>%{target.label}</b><br>Value: %{value}<extra></extra>'
            )
        )])
        
        # Update layout
        fig.update_layout(
            title={
                'text': title,
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 18, 'color': '#2c3e50'}
            },
            font_size=12,
            width=1400,
            height=800,
            margin=dict(l=50, r=50, t=100, b=50),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        
        
        
        return fig
    
    def _calculate_node_positions(self, all_nodes: List[str]) -> List[float]:
        """
        Calculate X positions for nodes based on their levels
        
        Args:
            all_nodes: List of all node names
            
        Returns:
            List of X positions (0-1 range)
        """
        x_positions = []
        
        for node in all_nodes:
            level = self.node_levels.get(node, 0)
            
            if level == 0:
                # Level 0 at 20% of working area
                x_positions.append(0.2)
            elif level == 1:
                # Level 1 at 45% of working area
                x_positions.append(0.45)
            elif level == 2:
                # Level 2 at 70% of working area
                x_positions.append(0.7)
            else:
                # Default positioning for other levels
                x_positions.append(0.5)
        
        return x_positions
    
    def _calculate_node_y_positions(self, all_nodes: List[str]) -> List[float]:
        """
        Calculate Y positions for nodes to distribute them evenly within each level
        
        Args:
            all_nodes: List of all node names
            
        Returns:
            List of Y positions (0-1 range)
        """
        # Group nodes by level
        level_groups = {}
        for i, node in enumerate(all_nodes):
            level = self.node_levels.get(node, 0)
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(i)
        
        y_positions = [0.0] * len(all_nodes)
        
        # Distribute nodes evenly within each level
        for level, node_indices in level_groups.items():
            if len(node_indices) == 1:
                # Single node: center it
                y_positions[node_indices[0]] = 0.5
            else:
                # Multiple nodes: distribute evenly
                for i, node_idx in enumerate(node_indices):
                    # Space nodes evenly with some padding
                    spacing = 0.8 / (len(node_indices) - 1) if len(node_indices) > 1 else 0
                    y_positions[node_idx] = 0.1 + (i * spacing)
        
        return y_positions
    
    def _post_process_html(self, html_content: str) -> str:
        """Post-process HTML to add styling and label positioning control"""
        # Add HTML comment and control button
        comment = "<!-- Sankey Chart Label Control -->"
        button_and_script = """
<div style="position: fixed; top: 10px; right: 10px; z-index: 1000;">
    <button id="fixLabelsBtn" onclick="fixAllLabels()" 
            style="background: #4CAF50; color: white; border: none; padding: 10px 15px; 
                   border-radius: 5px; cursor: pointer; font-size: 14px;">
        Fix All Labels
    </button>
</div>

<style>
/* Basic label styling */
.sankey-node text {
    font-weight: bold !important;
    filter: none !important;
    text-shadow: none !important;
}

.sankey-node text tspan {
    font-weight: bold !important;
    fill: #2c3e50 !important;
}
</style>

<script>
function fixAllLabels() {
    const nodes = document.querySelectorAll('.sankey-node');
    let fixedCount = 0;
    
    // Find the rightmost x position to identify last level nodes
    let maxX = 0;
    nodes.forEach(node => {
        const rect = node.querySelector('rect');
        if (rect) {
            const bbox = rect.getBoundingClientRect();
            if (bbox.left > maxX) maxX = bbox.left;
        }
    });
    
    // Fix labels for all nodes
    nodes.forEach(node => {
        const data = node.__data__;
        if (!data) return;
        
        const rect = node.querySelector('rect');
        if (!rect) return;
        
        const bbox = rect.getBoundingClientRect();
        const isRightmost = Math.abs(bbox.left - maxX) < 20;
        
        const label = node.querySelector('text');
        if (!label) return;
        
        // Position labels based on level
        const rectY = bbox.top;
        const rectHeight = bbox.height;
        const centerY = rectY + (rectHeight / 2);
        
        if (isRightmost) {
            // Last level: align to the right
            const offsetX = bbox.width + 10;
            const offsetY = centerY - rectY;
            label.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
            label.style.textAnchor = 'start';
            label.style.dominantBaseline = 'middle';
        } else {
            // Other levels: align to the left
            const offsetX = -10;
            const offsetY = centerY - rectY;
            label.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
            label.style.textAnchor = 'end';
            label.style.dominantBaseline = 'middle';
        }
        
        fixedCount++;
    });
    
    // Update button feedback
    const btn = document.getElementById('fixLabelsBtn');
    if (btn) {
        btn.textContent = `Fixed ${fixedCount} labels`;
        btn.style.background = '#2196F3';
        setTimeout(() => {
            btn.textContent = 'Fix All Labels';
            btn.style.background = '#4CAF50';
        }, 2000);
    }
}
</script>"""
        
        # Find the closing body tag and insert comment and button before it
        if "</body>" in html_content:
            html_content = html_content.replace("</body>", f"{comment}\n{button_and_script}\n</body>")
        
        return html_content
    
    
    def get_color_summary(self) -> Dict[str, any]:
        """
        Get a summary of the color assignments
        
        Returns:
            dict: Summary of color assignments by level and group
        """
        if not self.node_colors:
            return {}
        
        summary = {
            'by_level': {},
            'by_group': {},
            'total_nodes': len(self.node_colors)
        }
        
        # Group by level
        for node, color in self.node_colors.items():
            level = self.node_levels.get(node, 0)
            if level not in summary['by_level']:
                summary['by_level'][level] = []
            summary['by_level'][level].append({'node': node, 'color': color})
        
        # Group by color group
        for node, color in self.node_colors.items():
            group = self.color_config.get_group_for_node(node)
            group_key = group if group else 'Uncategorized'
            if group_key not in summary['by_group']:
                summary['by_group'][group_key] = []
            summary['by_group'][group_key].append({'node': node, 'color': color})
        
        return summary


def create_enhanced_sankey_from_csv(csv_path: str, config_path: str = "color_config.json", 
                                  title: str = "Enhanced Sankey Chart") -> go.Figure:
    """
    Convenience function to create an enhanced Sankey chart from CSV data
    
    Args:
        csv_path: Path to the CSV file
        config_path: Path to the color configuration file
        title: Title for the chart
        
    Returns:
        go.Figure: Plotly figure object
    """
    chart = EnhancedSankeyChart(config_path)
    
    if chart.load_data_from_csv(csv_path):
        return chart.create_chart(title)
    else:
        raise ValueError("Failed to load data from CSV file")


if __name__ == "__main__":
    # Test the enhanced Sankey chart
    print("Enhanced Sankey Chart Test")
    print("=" * 40)
    
    # Create sample data if it doesn't exist
    sample_data = pd.DataFrame({
        'Source': ['Portfolio A', 'Portfolio B', 'Portfolio A', 'Portfolio B', 'Strategy X', 'Strategy Y'],
        'Target': ['Strategy X', 'Strategy Y', 'Global Macro Strategy', 'Global Equity Long/Short', 'Global Macro Strategy', 'Quantitative Research Alpha'],
        'Value': [100, 150, 200, 180, 300, 230]
    })
    
    sample_data.to_csv('test_data.csv', index=False)
    print("Created test_data.csv")
    
    # Test the enhanced chart
    try:
        chart = EnhancedSankeyChart()
        if chart.load_data_from_csv('test_data.csv'):
            print("✅ Data loaded successfully!")
            
            # Show color summary
            summary = chart.get_color_summary()
            print(f"\nColor Summary:")
            print(f"Total nodes: {summary['total_nodes']}")
            
            for level, nodes in summary['by_level'].items():
                print(f"\nLevel {level}:")
                for node_info in nodes:
                    print(f"  {node_info['node']}: {node_info['color']}")
            
            # Create and show the chart
            fig = chart.create_chart("Test Enhanced Sankey Chart")
            fig.write_html("enhanced_sankey_test.html")
            print("\n✅ Chart created and saved as enhanced_sankey_test.html")
        else:
            print("❌ Failed to load data")
    except Exception as e:
        print(f"❌ Error: {e}")
