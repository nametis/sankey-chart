"""
Color Configuration System for Sankey Chart
Handles color definitions and group-based coloring logic
"""

import json
import os
from typing import Dict, List, Optional, Tuple
import colorsys


class ColorConfig:
    """Handles color configuration and group-based coloring for Sankey charts"""
    
    def __init__(self, config_path: str = "color_config.json"):
        """
        Initialize the color configuration system
        
        Args:
            config_path: Path to the color configuration JSON file
        """
        self.config_path = config_path
        self.group_colors = {}
        self.manual_colors = {}  # Manual color overrides for specific nodes
        self.default_color = "#808080"  # Grey for uncategorized nodes
        self.load_config()
    
    def load_config(self) -> bool:
        """
        Load color configuration from JSON file
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not os.path.exists(self.config_path):
                # Create default config if it doesn't exist
                self._create_default_config()
                return True
            
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            self.group_colors = config.get('group_colors', {})
            # Load manual colors, filtering out comment entries (starting with _)
            raw_manual_colors = config.get('manual_colors', {})
            self.manual_colors = {k: v for k, v in raw_manual_colors.items() if not k.startswith('_')}
            self.default_color = config.get('default_color', "#808080")
            
            return True
            
        except Exception as e:
            print(f"Error loading color config: {e}")
            return False
    
    def _create_default_config(self):
        """Create a default color configuration file"""
        default_config = {
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
            "manual_colors": {
                "Strategy Y": "#000000"
            },
            "default_color": "#808080"
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        self.group_colors = default_config['group_colors']
        self.default_color = default_config['default_color']
    
    def get_node_color(self, node_name: str) -> str:
        """
        Get color for a node based on manual colors, groups, or default
        
        Args:
            node_name: Name of the node
            
        Returns:
            str: Hex color code for the node
        """
        # First check for manual color override
        if node_name in self.manual_colors:
            return self.manual_colors[node_name]
        
        # Then check for group pattern match
        for group_pattern, color in self.group_colors.items():
            if node_name.startswith(group_pattern.rstrip('*')):
                return color
        
        # Finally use default color
        return self.default_color
    
    def get_group_for_node(self, node_name: str) -> Optional[str]:
        """
        Get the group name for a node
        
        Args:
            node_name: Name of the node
            
        Returns:
            str: Group name if found, None otherwise
        """
        for group_pattern in self.group_colors.keys():
            if node_name.startswith(group_pattern.rstrip('*')):
                return group_pattern
        
        return None
    
    def is_final_level_node(self, node_name: str) -> bool:
        """
        Check if a node is a final level node (has a defined group color)
        
        Args:
            node_name: Name of the node
            
        Returns:
            bool: True if it's a final level node
        """
        return self.get_group_for_node(node_name) is not None
    
    def mix_colors(self, colors: List[str], weights: List[float]) -> str:
        """
        Mix multiple colors based on their weights
        
        Args:
            colors: List of hex color codes
            weights: List of weights (should sum to 1.0)
            
        Returns:
            str: Mixed color as hex code
        """
        if len(colors) != len(weights):
            raise ValueError("Number of colors must match number of weights")
        
        if len(colors) == 0:
            return self.default_color
        
        if len(colors) == 1:
            return colors[0]
        
        # Normalize weights
        total_weight = sum(weights)
        if total_weight == 0:
            return self.default_color
        
        normalized_weights = [w / total_weight for w in weights]
        
        # Convert hex colors to RGB
        rgb_colors = []
        for color in colors:
            rgb = self._hex_to_rgb(color)
            rgb_colors.append(rgb)
        
        # Mix colors
        mixed_rgb = [0, 0, 0]
        for i, (r, g, b) in enumerate(rgb_colors):
            weight = normalized_weights[i]
            mixed_rgb[0] += r * weight
            mixed_rgb[1] += g * weight
            mixed_rgb[2] += b * weight
        
        # Convert back to hex (ensure integer values)
        mixed_rgb_int = [int(round(x)) for x in mixed_rgb]
        return self._rgb_to_hex(tuple(mixed_rgb_int))
    
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def _rgb_to_hex(self, rgb: Tuple[int, int, int]) -> str:
        """Convert RGB tuple to hex color"""
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    
    def get_all_group_colors(self) -> Dict[str, str]:
        """
        Get all defined group colors
        
        Returns:
            dict: Mapping of group patterns to colors
        """
        return self.group_colors.copy()
    
    def add_group_color(self, group_pattern: str, color: str):
        """
        Add a new group color definition
        
        Args:
            group_pattern: Group pattern (e.g., "Technology*")
            color: Hex color code
        """
        self.group_colors[group_pattern] = color
        self._save_config()
    
    def remove_group_color(self, group_pattern: str):
        """
        Remove a group color definition
        
        Args:
            group_pattern: Group pattern to remove
        """
        if group_pattern in self.group_colors:
            del self.group_colors[group_pattern]
            self._save_config()
    
    def _save_config(self):
        """Save current configuration to file"""
        config = {
            "group_colors": self.group_colors,
            "manual_colors": self.manual_colors,
            "default_color": self.default_color
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def update_default_color(self, color: str):
        """
        Update the default color for uncategorized nodes
        
        Args:
            color: Hex color code
        """
        self.default_color = color
        self._save_config()
    
    def add_manual_color(self, node_name: str, color: str):
        """
        Add a manual color for a specific node
        
        Args:
            node_name: Name of the node
            color: Hex color code
        """
        self.manual_colors[node_name] = color
        self._save_config()
    
    def remove_manual_color(self, node_name: str):
        """
        Remove a manual color for a specific node
        
        Args:
            node_name: Name of the node
        """
        if node_name in self.manual_colors:
            del self.manual_colors[node_name]
            self._save_config()
    
    def get_manual_colors(self) -> Dict[str, str]:
        """
        Get all manual color overrides
        
        Returns:
            dict: Mapping of node names to colors
        """
        return self.manual_colors.copy()


def create_sample_color_config():
    """Create a sample color configuration file"""
    config = ColorConfig("sample_color_config.json")
    print("Sample color configuration created!")
    print("Groups defined:")
    for group, color in config.get_all_group_colors().items():
        print(f"  {group}: {color}")
    print(f"Default color: {config.default_color}")


if __name__ == "__main__":
    # Test the color configuration system
    config = ColorConfig()
    
    print("Color Configuration Test:")
    print("=" * 40)
    
    # Test nodes
    test_nodes = [
        "Global Macro Strategy",
        "Global Equity Long/Short", 
        "Quantitative Research Alpha",
        "Fixed Income Credit",
        "Technology Infrastructure",
        "Some Random Node"
    ]
    
    for node in test_nodes:
        color = config.get_node_color(node)
        group = config.get_group_for_node(node)
        is_final = config.is_final_level_node(node)
        print(f"{node:25} | {color:7} | {str(group):20} | Final: {is_final}")
    
    # Test color mixing
    print("\nColor Mixing Test:")
    print("=" * 40)
    colors = ["#FF6B6B", "#4ECDC4", "#808080"]
    weights = [0.5, 0.3, 0.2]
    mixed = config.mix_colors(colors, weights)
    print(f"Mixing {colors} with weights {weights} = {mixed}")
