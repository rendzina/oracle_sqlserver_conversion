#!/usr/bin/env python3
"""

Sample

Extract sample INSERT statements for each table from any SQL Server file.
Creates a sample.sql file with a configurable number of INSERT statements per table.
The script processes tables sequentially as they are encountered in the input file.

The script will automatically:
- create an output file with a configurable number of INSERT statements per table (default: 3)
- process tables in the order they appear in the input file (sequential processing)
- handle tables with fewer rows than the requested sample count gracefully
- the output file will be in the same directory as the input file
- the output file will be named the same as the input file but with the extension _sample.sql
- the output file will contain only select INSERT statements for the tables in the input file

The code is provided as part of the open source output of the Landis Portal database conversion project.

Author: Stephen Hallett, Cranfield University
Date: 2025-10-19
License: MIT License - see LICENSE file for details
http://www.landis.org.uk
"""

import re
import sys
import argparse
import os

def extract_sample_inserts(input_file, output_file, samples_per_table=3, schema_name='ADMIN'):
    """
    Extract sample INSERT statements for each table.
    
    Args:
        input_file: Path to the input SQL file
        output_file: Path to the output sample file
        samples_per_table: Number of sample INSERT statements per table
        schema_name: Schema name to look for in INSERT statements
    """
    
    print(f"Extracting sample INSERT statements from {input_file}...")
    
    # Dictionary to track INSERT statements per table
    table_inserts = {}
    # List to maintain order of tables as they're encountered
    table_order = []
    
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as infile:
        for line_num, line in enumerate(infile, 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('--'):
                continue
            
            # Skip table definitions (CREATE TABLE, IF EXISTS, DROP TABLE, GO)
            if any(keyword in line.upper() for keyword in [
                'CREATE TABLE', 'IF EXISTS', 'DROP TABLE', 'GO'
            ]):
                continue
            
            # Look for INSERT statements
            if line.upper().startswith('INSERT INTO'):
                # Extract table name from INSERT statement
                # Pattern: INSERT INTO [SCHEMA].[TABLE_NAME] ...
                pattern = rf'INSERT INTO \[{schema_name}\]\.\[([^\]]+)\]'
                match = re.search(pattern, line)
                if match:
                    table_name = match.group(1)
                    
                    # Initialize list for this table if not exists
                    if table_name not in table_inserts:
                        table_inserts[table_name] = []
                        table_order.append(table_name)  # Track order of first encounter
                    
                    # Add INSERT statement if we haven't reached the limit
                    if len(table_inserts[table_name]) < samples_per_table:
                        table_inserts[table_name].append(line)
            
            # Progress indicator
            if line_num % 100000 == 0:
                print(f"Processed {line_num:,} lines...")
    
    # Write sample file
    print(f"Writing sample INSERT statements to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        # Write header
        outfile.write(f"-- Sample INSERT statements extracted from {input_file}\n")
        outfile.write(f"-- This file contains sample data for each table (max {samples_per_table} samples per table)\n")
        outfile.write("-- Table definitions (CREATE TABLE statements) are excluded\n")
        outfile.write("-- Generated automatically for testing and reference purposes\n\n")
        
        # Process tables in the order they were encountered (sequential processing)
        for table_name in table_order:
            inserts = table_inserts[table_name]
            if inserts:  # Only write tables that have data
                outfile.write(f"-- Table: {table_name} ({len(inserts)} sample(s))\n")
                
                for insert in inserts:
                    outfile.write(insert + '\n')
                
                outfile.write('\n')
        
        # Write summary
        total_tables = len(table_inserts)
        total_samples = sum(len(inserts) for inserts in table_inserts.values())
        
        outfile.write(f"-- Summary\n")
        outfile.write(f"-- Total tables with data: {total_tables}\n")
        outfile.write(f"-- Total sample INSERT statements: {total_samples}\n")
        outfile.write(f"-- Samples per table: {samples_per_table}\n")
    
    print(f"\nSample extraction completed!")
    print(f"Tables processed: {total_tables}")
    print(f"Sample INSERT statements: {total_samples}")
    print(f"Output file: {output_file}")

def main():
    parser = argparse.ArgumentParser(
        description='Extract sample INSERT statements from SQL Server file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s my_database_inserts.sql
  %(prog)s database.sql -o test_sample.sql
  %(prog)s hr_data.sql --schema HR --samples 5
  %(prog)s production.sql --schema PROD --output prod_sample.sql --samples 2

The script extracts sample INSERT statements from any SQL Server file
and creates a smaller test file for development and testing purposes.
        """
    )
    
    parser.add_argument('input_file', 
                       help='Input SQL file containing INSERT statements')
    parser.add_argument('-o', '--output', 
                       help='Output sample file (default: sample.sql)')
    parser.add_argument('--schema', 
                       default='ADMIN', 
                       help='Schema name to look for (default: ADMIN)')
    parser.add_argument('--samples', 
                       type=int, 
                       default=3, 
                       help='Number of sample INSERT statements per table (default: 3)')
    parser.add_argument('--version', 
                       action='version', 
                       version='SQL INSERT Sample Extractor 1.0')
    
    args = parser.parse_args()
    
    # Validate input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        return 1
    
    # Set output file
    if args.output:
        output_file = args.output
    else:
        # Auto-generate output filename based on input
        base_name = os.path.splitext(args.input_file)[0]
        output_file = f"{base_name}_sample.sql"
    
    try:
        extract_sample_inserts(args.input_file, output_file, args.samples, args.schema)
        return 0
    except Exception as e:
        print(f"Error during extraction: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
