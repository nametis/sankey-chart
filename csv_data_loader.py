"""
CSV Data Loader for Sankey Chart
Handles loading and validation of data from CSV files
"""

import pandas as pd
import os
from typing import Optional, Dict, Any


class CSVDataLoader:
    """Handles loading and validation of Sankey chart data from CSV files"""
    
    def __init__(self, csv_path: str):
        """
        Initialize the CSV data loader
        
        Args:
            csv_path: Path to the CSV file containing the data
        """
        self.csv_path = csv_path
        self.data = None
        self.validation_errors = []
    
    def load_data(self) -> bool:
        """
        Load data from CSV file
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not os.path.exists(self.csv_path):
                self.validation_errors.append(f"CSV file not found: {self.csv_path}")
                return False
            
            # Load CSV data
            self.data = pd.read_csv(self.csv_path)
            
            # Validate data structure
            return self._validate_data()
            
        except Exception as e:
            self.validation_errors.append(f"Error loading CSV file: {str(e)}")
            return False
    
    def _validate_data(self) -> bool:
        """
        Validate that the CSV data has the required structure
        
        Returns:
            bool: True if valid, False otherwise
        """
        if self.data is None:
            self.validation_errors.append("No data loaded")
            return False
        
        # Check for required columns
        required_columns = ['Source', 'Target', 'Value']
        missing_columns = [col for col in required_columns if col not in self.data.columns]
        
        if missing_columns:
            self.validation_errors.append(f"Missing required columns: {missing_columns}")
            return False
        
        # Check for empty values
        for col in required_columns:
            if self.data[col].isnull().any():
                self.validation_errors.append(f"Column '{col}' contains empty values")
                return False
        
        # Check that Value column is numeric
        try:
            self.data['Value'] = pd.to_numeric(self.data['Value'])
        except (ValueError, TypeError):
            self.validation_errors.append("Value column must contain numeric data")
            return False
        
        # Check for negative values
        if (self.data['Value'] < 0).any():
            self.validation_errors.append("Value column contains negative values")
            return False
        
        # Check for zero values
        if (self.data['Value'] == 0).any():
            self.validation_errors.append("Value column contains zero values")
            return False
        
        return True
    
    def get_data(self) -> Optional[pd.DataFrame]:
        """
        Get the loaded and validated data
        
        Returns:
            pd.DataFrame: The loaded data or None if not loaded/valid
        """
        return self.data
    
    def get_validation_errors(self) -> list:
        """
        Get list of validation errors
        
        Returns:
            list: List of validation error messages
        """
        return self.validation_errors
    
    def get_data_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics about the loaded data
        
        Returns:
            dict: Summary statistics
        """
        if self.data is None:
            return {}
        
        return {
            'total_rows': len(self.data),
            'unique_sources': self.data['Source'].nunique(),
            'unique_targets': self.data['Target'].nunique(),
            'total_value': self.data['Value'].sum(),
            'min_value': self.data['Value'].min(),
            'max_value': self.data['Value'].max(),
            'mean_value': self.data['Value'].mean()
        }
    
    def get_unique_nodes(self) -> set:
        """
        Get all unique nodes (sources and targets) from the data
        
        Returns:
            set: Set of unique node names
        """
        if self.data is None:
            return set()
        
        sources = set(self.data['Source'].unique())
        targets = set(self.data['Target'].unique())
        return sources | targets


def load_sankey_data(csv_path: str) -> tuple[Optional[pd.DataFrame], list]:
    """
    Convenience function to load Sankey data from CSV
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        tuple: (dataframe, validation_errors)
    """
    loader = CSVDataLoader(csv_path)
    success = loader.load_data()
    
    if success:
        return loader.get_data(), []
    else:
        return None, loader.get_validation_errors()


if __name__ == "__main__":
    # Test the CSV data loader
    test_csv_path = "data.csv"
    
    if os.path.exists(test_csv_path):
        loader = CSVDataLoader(test_csv_path)
        success = loader.load_data()
        
        if success:
            print("✅ Data loaded successfully!")
            print(f"Summary: {loader.get_data_summary()}")
            print(f"Unique nodes: {len(loader.get_unique_nodes())}")
        else:
            print("❌ Data loading failed:")
            for error in loader.get_validation_errors():
                print(f"  - {error}")
    else:
        print(f"❌ Test CSV file not found: {test_csv_path}")
