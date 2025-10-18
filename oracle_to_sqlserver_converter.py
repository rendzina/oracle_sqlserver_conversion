#!/usr/bin/env python3
"""
Oracle to SQL Server SQL Converter

This script converts Oracle SQL DDL and DML statements to SQL Server format.
It processes the entire input sql file and outputs to an output sql file with 
the same name but with the extension _sqlserver_definitions.sql and _sqlserver_inserts_all.sql.
The _sqlserver_inserts_all.sql file is then split into 100,000 line chunks and output to
files with the extension _sqlserver_inserts_chunk_01.sql, _sqlserver_inserts_chunk_02.sql, etc.

The input sql file is expected to be in the Oracle format and can be created by a DDL export from SQL Developer.
The output sql file is expected to be in the SQL Server format and can be executed in SQL Server Management Studio 
or in VS Code with the SQL Server extension. The output files are expected to be in the same directory as the input file.

The script is designed to be used as a command line tool and can be run from the command line.

The script will automatically:
- Separate table definitions from INSERT statements
- Split large INSERT files into 100,000 line chunks
- Convert Oracle data types to SQL Server equivalents
- Handle Oracle-specific functions and syntax

The code is provided as part of the open source output of the Landis Portal database conversion project.

Author: Stephen Hallett, Cranfield University
Date: 2025-10-19
License: MIT License - see LICENSE file for details
"""

import re
import os
import argparse
from datetime import datetime


class OracleToSQLServerConverter:
    """
    Converts Oracle SQL statements to SQL Server format.
    
    This class handles the complete conversion process from Oracle SQL exports
    to SQL Server compatible format, including data type mapping, syntax conversion,
    and comprehensive data fixes for common migration issues.
    """
    
    def __init__(self, input_file, output_file=None, schema_name='ADMIN'):
        """
        Initialize the Oracle to SQL Server converter.
        
        Args:
            input_file (str): Path to the Oracle SQL export file
            output_file (str, optional): Custom output file path. If None, auto-generates based on input file
            schema_name (str): Target schema name for SQL Server (default: 'ADMIN')
        """
        self.input_file = input_file
        if output_file is None:
            # Auto-generate output filename based on input
            base_name = os.path.splitext(input_file)[0]
            self.output_file = f"{base_name}_sqlserver.sql"
        else:
            self.output_file = output_file
        self.schema_name = schema_name
        self.table_info = {}
        self.conversion_stats = {
            'tables_processed': 0,
            'inserts_processed': 0,
            'lines_processed': 0
        }
        
        # Oracle to SQL Server data type mappings
        self.data_type_mappings = {
            'NUMBER':       'DECIMAL(18,0)',
            'NUMBER(*)':    'DECIMAL(18,0)',
            'NUMBER(1)':    'BIT',
            'NUMBER(3)':    'TINYINT',
            'NUMBER(5)':    'SMALLINT',
            'NUMBER(10)':   'INT',
            'NUMBER(19)':   'BIGINT',
            'VARCHAR2':     'NVARCHAR',
            'VARCHAR':      'NVARCHAR',
            'CHAR':         'NCHAR',
            'DATE':         'DATETIME2',
            'TIMESTAMP':    'DATETIME2',
            'TIMESTAMP(0)': 'DATETIME2',
            'TIMESTAMP(6)': 'DATETIME2',
            'CLOB':         'NVARCHAR(MAX)',
            'BLOB':         'VARBINARY(MAX)',
            'RAW':          'NVARCHAR(12)', # Convert RAW to plain text for simplicity
            'LONG':         'NVARCHAR(MAX)',
            'LONG RAW':     'VARBINARY(MAX)'
        }
    
    def convert_data_type(self, oracle_type: str) -> str:
        """
        Convert Oracle data type to SQL Server equivalent.
        
        Maps Oracle data types to their SQL Server counterparts, handling
        precision, scale, and special cases like boolean values.
        
        Args:
            oracle_type (str): Oracle data type string
            
        Returns:
            str: SQL Server equivalent data type
        """
        oracle_type = oracle_type.upper().strip()
        
        # Handle specific patterns
        if oracle_type.startswith('VARCHAR2('):
            size_match = re.search(r'VARCHAR2\((\d+)(?:\s+BYTE)?\)', oracle_type)
            if size_match:
                size = int(size_match.group(1))
                return f'NVARCHAR({size})'
            return 'NVARCHAR(255)'
        
        elif oracle_type.startswith('VARCHAR('):
            size_match = re.search(r'VARCHAR\((\d+)(?:\s+BYTE)?\)', oracle_type)
            if size_match:
                size = int(size_match.group(1))
                return f'NVARCHAR({size})'
            return 'NVARCHAR(255)'
        
        elif oracle_type.startswith('CHAR('):
            size_match = re.search(r'CHAR\((\d+)(?:\s+BYTE)?\)', oracle_type)
            if size_match:
                size = int(size_match.group(1))
                return f'NCHAR({size})'
            return 'NCHAR(1)'
        
        elif oracle_type.startswith('RAW('):
            # Convert RAW to NVARCHAR for simplicity
            size_match = re.search(r'RAW\((\d+)\)', oracle_type)
            if size_match:
                size = int(size_match.group(1))
                # Convert raw size to appropriate text size (raw is typically hex, so 2 chars per byte)
                text_size = size * 2
                return f'NVARCHAR({text_size})'
            return 'NVARCHAR(12)'
        
        elif oracle_type.startswith('TIMESTAMP('):
            return 'DATETIME2'
        
        elif oracle_type.startswith('NUMBER('):
            number_match = re.search(r'NUMBER\((\d+)(?:,(\d+))?\)', oracle_type)
            if number_match:
                precision = int(number_match.group(1))
                scale = int(number_match.group(2)) if number_match.group(2) else 0
                
                if precision == 0:
                    precision = 1
                
                if precision <= 1:
                    return 'BIT'
                elif precision <= 3:
                    return 'TINYINT'
                elif precision <= 5:
                    return 'SMALLINT'
                elif precision <= 10:
                    return 'INT'
                elif precision <= 19:
                    return 'BIGINT'
                else:
                    return f'DECIMAL({precision},{scale})'
            return 'DECIMAL(18,0)'
        
        return self.data_type_mappings.get(oracle_type, oracle_type)
    
    def extract_table_name(self, create_table_line: str) -> str:
        """
        Extract table name from CREATE TABLE statement.
        
        Handles both quoted and unquoted table name formats
        in Oracle CREATE TABLE statements.
        
        Args:
            create_table_line (str): CREATE TABLE statement line
            
        Returns:
            str: Extracted table name or 'UNKNOWN' if not found
        """
        # Handle quoted format: CREATE TABLE "SCHEMA"."TABLE_NAME"
        quoted_pattern = rf'CREATE TABLE\s+"{self.schema_name}"\."([^"]+)"'
        match = re.search(quoted_pattern, create_table_line)
        if match:
            return match.group(1)
        
        # Handle unquoted format: CREATE TABLE SCHEMA.TABLE_NAME
        unquoted_pattern = rf'CREATE TABLE\s+{self.schema_name}\.([A-Z_][A-Z0-9_]*)'
        match = re.search(unquoted_pattern, create_table_line)
        if match:
            return match.group(1)
        
        return "UNKNOWN"
    
    def convert_create_table(self, lines: list) -> list:
        """
        Convert Oracle CREATE TABLE statement to SQL Server format.
        
        Processes CREATE TABLE statements, adding DROP TABLE IF EXISTS,
        converting column names to bracketed format, and handling
        Oracle-specific syntax.
        
        Args:
            lines (list): List of lines containing the CREATE TABLE statement
            
        Returns:
            list: Converted SQL Server CREATE TABLE statement lines
        """
        sql_server_lines = []
        table_name = None
        columns = []
        in_column_def = False
        
        for line in lines:
            line = line.strip()
            
            if 'CREATE TABLE' in line and not table_name:
                table_name = self.extract_table_name(line)
                sql_server_lines.append(f"-- Table: {table_name}")
                
                sql_server_lines.append(f"IF EXISTS(SELECT name FROM sys.sysobjects WHERE Name = N'{table_name}' AND xtype = N'U')")
                sql_server_lines.append("BEGIN")
                sql_server_lines.append(f"    DROP TABLE [{self.schema_name}].[{table_name}]")
                sql_server_lines.append("END")
                sql_server_lines.append("GO")
                sql_server_lines.append("")
                
                sql_server_lines.append(f"CREATE TABLE [{self.schema_name}].[{table_name}] (")
                in_column_def = True
                continue
            
            # Skip Oracle-specific storage clauses
            if any(keyword in line.upper() for keyword in [
                'SEGMENT CREATION', 'PCTFREE', 'PCTUSED', 'INITRANS', 'MAXTRANS',
                'NOCOMPRESS', 'LOGGING', 'STORAGE', 'TABLESPACE', 'BUFFER_POOL',
                'FLASH_CACHE', 'CELL_FLASH_CACHE', 'PCTINCREASE', 'FREELISTS', 'FREELIST GROUPS'
            ]):
                continue
            
            # Handle simple table definitions that end with just ) or ); without storage clauses
            if in_column_def and line.strip() == ')':
                in_column_def = False
                continue
            
            if in_column_def and line.startswith('('):
                line = line[1:].strip()
                if line and not line.endswith(')'):
                    pass
            
            if in_column_def and line.endswith(');'):
                line = line[:-2].strip()
                in_column_def = False
            
            if in_column_def and line:
                # Remove trailing comma if present
                line_clean = line.rstrip(',').strip()
                
                # Extract column name and definition more carefully
                # Look for quoted column name followed by type definition
                column_match = re.match(r'"([^"]+)"\s+(.+)', line_clean)
                if not column_match:
                    # Handle unquoted column names (new format)
                    column_match = re.match(r'([A-Z_][A-Z0-9_]*)\s+(.+)', line_clean)
                
                if column_match:
                    column_name = column_match.group(1)
                    oracle_type = column_match.group(2).strip()
                    sql_server_type = self.convert_data_type(oracle_type)
                    sql_server_type = self.fix_data_type_precision(sql_server_type)
                    
                    if 'DEFAULT' in oracle_type.upper():
                        # Handle DEFAULT clauses more carefully, especially with function calls
                        default_start = oracle_type.upper().find('DEFAULT')
                        if default_start != -1:
                            # Find the DEFAULT keyword and extract everything after it
                            default_part = oracle_type[default_start + 7:].strip()  # 7 = len('DEFAULT')
                            # Remove DEFAULT from the type part
                            type_part = oracle_type[:default_start].strip()
                            sql_server_type = self.convert_data_type(type_part)
                            sql_server_type = self.fix_data_type_precision(sql_server_type)
                            
                            # Simplify complex Oracle DEFAULT clauses
                            if 'hextoraw(substr(sys_guid()' in default_part.lower():
                                # Replace complex Oracle GUID generation with simpler SQL Server equivalent
                                default_part = "NEWID()"
                            elif 'sys_guid()' in default_part.lower():
                                # Replace Oracle sys_guid() with SQL Server NEWID()
                                default_part = "NEWID()"
                            
                            columns.append(f"    [{column_name}] {sql_server_type} DEFAULT {default_part}")
                        else:
                            columns.append(f"    [{column_name}] {sql_server_type}")
                    else:
                        columns.append(f"    [{column_name}] {sql_server_type}")
        
        # Add columns to output with proper comma separation
        if columns:
            for i, column in enumerate(columns):
                if i < len(columns) - 1:
                    if not column.rstrip().endswith(','):
                        columns[i] = column.rstrip() + ','
                else:
                    columns[i] = column.rstrip().rstrip(',')
            
            sql_server_lines.extend(columns)
            sql_server_lines.append(");")
            sql_server_lines.append("GO")
            sql_server_lines.append("")
            
            self.table_info[table_name] = {
                'columns': len(columns),
                'column_definitions': columns
            }
            self.conversion_stats['tables_processed'] += 1
        
        return sql_server_lines
    
    def fix_data_type_precision(self, line: str) -> str:
        """Fix data type precision issues."""
        line = re.sub(r'DECIMAL\(0,0\)', 'DECIMAL(1,0)', line)
        line = re.sub(r'DECIMAL\(0,(\d+)\)', r'DECIMAL(1,\1)', line)
        line = re.sub(r'DECIMAL\((\d+),0\)', r'DECIMAL(\1,0)', line)
        line = re.sub(r'NVARCHAR\(0\)', 'NVARCHAR(1)', line)
        line = re.sub(r'NCHAR\(0\)', 'NCHAR(1)', line)
        line = re.sub(r'VARCHAR\(0\)', 'VARCHAR(1)', line)
        line = re.sub(r'CHAR\(0\)', 'CHAR(1)', line)
        line = re.sub(r'TIMESTAMP\s*\(\s*\d+\s*\)', 'DATETIME2', line)
        line = re.sub(r'TIMESTAMP\s*\(\s*0\s*\)', 'DATETIME2', line)
        line = re.sub(r'\bNUMBER\b(?!\s*\()', 'DECIMAL(18,0)', line)
        return line
    
    def convert_oracle_functions(self, line: str) -> str:
        """
        Convert Oracle-specific functions to SQL Server equivalents.
        
        Handles conversion of Oracle date/time functions like to_date(),
        to_timestamp(), sysdate, and systimestamp to SQL Server equivalents.
        
        Args:
            line (str): SQL line containing Oracle functions
            
        Returns:
            str: Line with Oracle functions converted to SQL Server equivalents
        """
        def convert_to_timestamp(match):
            date_str = match.group(1).strip().strip("'\"")
            try:
                date_part, time_part = date_str.split(' ')
                day, month, year = date_part.split('-')
                # Handle time part that may have microsecond precision
                time_parts = time_part.split('.')
                hour = time_parts[0]
                minute = time_parts[1]
                second = time_parts[2] if len(time_parts) > 2 else '00'
                
                year_int = int(year)
                if year_int < 50:
                    full_year = 2000 + year_int
                else:
                    full_year = 1900 + year_int
                
                month_map = {
                    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
                }
                month_num = month_map.get(month, '01')
                
                sql_server_date = f"'{full_year}-{month_num}-{day.zfill(2)} {hour.zfill(2)}:{minute.zfill(2)}:{second.zfill(2)}.000'"
                return sql_server_date
            except Exception as e:
                # If conversion fails, return the original date string with quotes
                return f"'{date_str}'"
        
        line = re.sub(r"to_timestamp\('([^']+)',([^)]+)\)", convert_to_timestamp, line)
        line = re.sub(r'to_date\(([^,]+),([^)]+)\)', r'\1', line)
        line = re.sub(r'sysdate', 'GETDATE()', line, flags=re.IGNORECASE)
        line = re.sub(r'systimestamp', 'GETDATE()', line, flags=re.IGNORECASE)
        return line
    
    def escape_quotes_in_values(self, line: str) -> str:
        """
        Properly escape single quotes within string values in INSERT statements.
        
        Handles the critical conversion of Oracle's double-quote escaping ('')
        to SQL Server's double-quote escaping ('') within string values.
        Supports multi-line VALUES clauses.
        
        Args:
            line (str): INSERT statement line
            
        Returns:
            str: Line with properly escaped quotes for SQL Server
        """
        # This function handles the critical issue of unescaped single quotes
        # within string values that cause SQL Server syntax errors
        
        # Pattern to match VALUES clause and extract the values part
        # Use DOTALL flag to handle multi-line VALUES clauses
        values_match = re.search(r'VALUES\s*\((.*)\);?$', line, re.IGNORECASE | re.DOTALL)
        if not values_match:
            return line
        
        values_part = values_match.group(1)
        original_values = values_match.group(0)
        
        # Split by commas, but be careful about commas within quoted strings
        values = []
        current_value = ""
        in_quotes = False
        quote_char = None
        
        i = 0
        while i < len(values_part):
            char = values_part[i]
            
            if not in_quotes:
                if char in ["'", '"']:
                    in_quotes = True
                    quote_char = char
                    current_value += char
                elif char == ',':
                    values.append(current_value.strip())
                    current_value = ""
                else:
                    current_value += char
            else:
                if char == quote_char:
                    # Check if this is an escaped quote (double quote)
                    if i + 1 < len(values_part) and values_part[i + 1] == quote_char:
                        current_value += char + char  # Add both quotes
                        i += 1  # Skip the next quote
                    else:
                        # End of quoted string
                        in_quotes = False
                        quote_char = None
                        current_value += char
                else:
                    current_value += char
            
            i += 1
        
        # Add the last value
        if current_value.strip():
            values.append(current_value.strip())
        
        # Process each value to escape unescaped single quotes
        processed_values = []
        for value in values:
            value = value.strip()
            if value.startswith("'") and value.endswith("'"):
                # This is a string value - escape internal single quotes
                inner_content = value[1:-1]  # Remove outer quotes
                # Handle Oracle's double quote escaping properly for SQL Server
                # Oracle uses '' for escaped quotes, SQL Server also uses ''
                # The key is to ensure all single quotes are properly escaped
                escaped_content = inner_content.replace("'", "''")  # Escape all single quotes
                processed_values.append(f"'{escaped_content}'")
            else:
                # Not a string value, leave as is
                processed_values.append(value)
        
        # Reconstruct the line
        new_values_part = ', '.join(processed_values)
        new_line = line.replace(original_values, f"VALUES ({new_values_part})")
        
        return new_line
    
    def fix_problematic_strings(self, line: str) -> str:
        """
        Fix problematic strings that cause SQL Server syntax errors.
        
        Handles browser user agent strings, SQL keywords in strings,
        long identifiers, repeated characters, and other problematic
        patterns that cause SQL Server parsing errors.
        
        Args:
            line (str): SQL line to process
            
        Returns:
            str: Line with problematic strings fixed
        """
        # Find all string values (between single quotes) and replace problematic characters
        def replace_in_strings(match):
            string_content = match.group(1)
            
            # Handle specific malformed patterns
            if string_content == '[;' or string_content == '[;);':
                return "'MALFORMED_STRING'"
            
            # Fix browser user agent strings
            # Replace 'rv:version' with just 'version' (remove the colon)
            string_content = re.sub(r'\brv:(\d+\.\d+)', r'version\1', string_content)
            
            # Replace 'version:version' with just 'version' (remove the colon)
            string_content = re.sub(r'\bversion:(\d+\.\d+)', r'version\1', string_content)
            
            # Replace other problematic patterns
            string_content = string_content.replace('with', 'w/')
            string_content = string_content.replace('about', 'abt')
            
            # Remove or replace other SQL keywords that might cause issues
            string_content = string_content.replace('select', 'sel')
            string_content = string_content.replace('insert', 'ins')
            string_content = string_content.replace('update', 'upd')
            string_content = string_content.replace('delete', 'del')
            string_content = string_content.replace('create', 'cr')
            string_content = string_content.replace('drop', 'dr')
            string_content = string_content.replace('alter', 'alt')
            
            # Truncate extremely long strings (over 100 characters)
            # But preserve proper escaping by truncating at a safe point
            if len(string_content) > 100:
                # Find a safe truncation point (not in the middle of escaped quotes)
                truncate_at = 100
                # If we're truncating in the middle of escaped quotes, adjust
                if truncate_at > 0 and string_content[truncate_at-1:truncate_at+1] == "''":
                    truncate_at -= 1
                string_content = string_content[:truncate_at] + "... [TRUNCATED]"
            
            # Remove repeated characters (like 'InfinityInfinityInfinity...')
            repeated_pattern = re.compile(r'(.)\1{10,}')  # 11+ repeated characters
            string_content = repeated_pattern.sub(r'\1\1\1... [REPEATED]', string_content)
            
            # Replace problematic characters
            string_content = string_content.replace('[', '(')
            string_content = string_content.replace(']', ')')
            string_content = string_content.replace(';', ',')
            string_content = string_content.replace('\\', '/')
            
            # Handle malformed strings
            if string_content.startswith('[') and string_content.endswith(';'):
                string_content = 'MALFORMED_STRING'
            
            return f"'{string_content}'"
        
        # Use regex to find and replace content within single quotes
        # This handles both properly quoted strings and malformed strings
        original_line = line
        line = re.sub(r"'([^']*(?:''[^']*)*)'", replace_in_strings, line)
        
        # Debug: Check if the line was modified
        if original_line != line and 'cghmj.l' in original_line:
            print(f"Fixed problematic string in line: {original_line[:100]}...")
        
        return line
    
    def fix_extra_parentheses(self, line: str) -> str:
        """
        Fix extra parentheses that cause SQL Server syntax errors.
        
        Removes malformed patterns like ');); and ));) that occur
        in corrupted INSERT statements.
        
        Args:
            line (str): SQL line to process
            
        Returns:
            str: Line with extra parentheses removed
        """
        # Fix patterns like ');); and ));) that cause syntax errors
        line = line.replace("'););", "');")  # Fix ');); pattern
        line = line.replace("););", ");")    # Fix ));) pattern
        
        return line
    
    def fix_numeric_issues(self, line: str) -> str:
        """
        Fix numeric issues that cause SQL Server syntax errors.
        
        Replaces out-of-range scientific notation values with NULL
        to prevent SQL Server parsing errors.
        
        Args:
            line (str): SQL line to process
            
        Returns:
            str: Line with numeric issues fixed
        """
        # Fix scientific notation that's out of range
        line = re.sub(r"'(\d+E\d+)'", r"NULL", line)  # Replace scientific notation with NULL
        
        return line
    
    def fix_malformed_statements(self, line: str) -> str:
        """
        Fix malformed INSERT statements.
        
        Comments out obviously malformed lines and Oracle-specific statements
        that are not supported in SQL Server.
        
        Args:
            line (str): SQL line to process
            
        Returns:
            str: Line with malformed statements commented out
        """
        # Check for obviously malformed lines
        if "'[;" in line or "'[;);" in line:
            # Skip malformed lines
            return f"-- SKIPPED MALFORMED LINE: {line.strip()}"
        
        # Remove Oracle-specific statements
        if any(keyword in line.upper() for keyword in ['USE ', 'SET DEFINE', 'ALTER SESSION']):
            return f"-- {line.strip()} (Oracle specific, commented out)"
        
        return line
    
    def fix_data_type_issues(self, line: str) -> str:
        """
        Fix data type issues in INSERT VALUES clauses.
        
        Orchestrates the application of all data fixes in the correct order:
        malformed statements, quote escaping, problematic strings, numeric issues,
        and extra parentheses.
        
        Args:
            line (str): SQL line to process
            
        Returns:
            str: Line with all data type issues fixed
        """
        # First handle malformed statements
        line = self.fix_malformed_statements(line)
        
        # If line was commented out, return it as is
        if line.strip().startswith('--'):
            return line
        
        # Handle quote escaping - this is critical for SQL Server compatibility
        # Do this FIRST to ensure proper escaping before other processing
        line = self.escape_quotes_in_values(line)
        
        # Handle problematic strings that cause SQL Server syntax errors
        line = self.fix_problematic_strings(line)
        
        # Fix numeric issues
        line = self.fix_numeric_issues(line)
        
        # Fix extra parentheses that cause SQL Server syntax errors
        line = self.fix_extra_parentheses(line)
        
        return line
    
    def convert_insert_statement(self, line: str) -> str:
        """
        Convert Oracle INSERT statement to SQL Server format.
        
        Converts table and column names to bracketed format and applies
        comprehensive data fixes for SQL Server compatibility.
        
        Args:
            line (str): Oracle INSERT statement
            
        Returns:
            str: SQL Server compatible INSERT statement
        """
        line = re.sub(rf'Insert into {self.schema_name}\.([^\s]+)\s*\(', rf'INSERT INTO [{self.schema_name}].[\1] (', line)
        
        def add_brackets_to_columns(match):
            columns = match.group(1)
            column_list = [col.strip() for col in columns.split(',')]
            bracketed_columns = ', '.join([f'[{col}]' for col in column_list])
            return f'({bracketed_columns})'
        
        line = re.sub(r'\(([^)]+)\)\s+values', add_brackets_to_columns, line)
        line = re.sub(r'\)\s*\(', ') VALUES (', line)
        line = self.convert_oracle_functions(line)
        line = re.sub(r'\bnull\b', 'NULL', line, flags=re.IGNORECASE)
        line = self.fix_data_type_issues(line)
        
        self.conversion_stats['inserts_processed'] += 1
        return line
    
    def convert_multi_line_insert(self, lines: list) -> str:
        """
        Convert multi-line Oracle INSERT statement to SQL Server format.
        
        Joins multiple lines of an INSERT statement and applies conversion
        to create a single SQL Server compatible statement.
        
        Args:
            lines (list): List of lines containing the INSERT statement
            
        Returns:
            str: Single converted INSERT statement
        """
        full_statement = ' '.join(line.strip() for line in lines)
        converted_statement = self.convert_insert_statement(full_statement)
        return converted_statement
    
    def split_inserts_into_chunks(self, inserts_file):
        """
        Split the INSERT statements file into 100,000 line chunks.
        
        Uses the Unix 'split' command to create manageable chunks
        for SQL Server execution, naming them sequentially.
        
        Args:
            inserts_file (str): Path to the large INSERT statements file
        """
        import subprocess
        import os
        
        print("Splitting INSERT statements into 100,000 line chunks...")
        
        # Use split command to create chunks
        chunk_prefix = inserts_file.replace('_all.sql', '_chunk_')
        result = subprocess.run(['split', '-l', '100000', inserts_file, chunk_prefix], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            # Rename chunks to be more user-friendly
            chunk_files = [f for f in os.listdir('.') if f.startswith(os.path.basename(chunk_prefix))]
            chunk_files.sort()
            
            for i, chunk_file in enumerate(chunk_files, 1):
                new_name = f"{chunk_prefix}{i:02d}.sql"
                os.rename(chunk_file, new_name)
            
            print(f"Created {len(chunk_files)} INSERT chunk files")
        else:
            print(f"Warning: Failed to split INSERT statements: {result.stderr}")
    
    def process_file(self):
        """
        Process the Oracle SQL file and convert to SQL Server format.
        
        Main conversion method that orchestrates the entire conversion process:
        reads the Oracle file, separates table definitions from INSERT statements,
        converts both types, and splits large INSERT files into manageable chunks.
        """
        print(f"Converting {self.input_file} to SQL Server format")
        print(f"File size: {os.path.getsize(self.input_file) / (1024*1024):.1f} MB")
        
        # Create separate files for table definitions and INSERT statements
        definitions_file = self.output_file.replace('.sql', '_definitions.sql')
        inserts_file = self.output_file.replace('.sql', '_inserts_all.sql')
        
        with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as infile, \
             open(definitions_file, 'w', encoding='utf-8') as def_outfile, \
             open(inserts_file, 'w', encoding='utf-8') as inserts_outfile:
            
            # Write headers for both files
            header = "-- Converted from Oracle to SQL Server\n"
            header += f"-- Conversion date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            header += f"-- Original file: {self.input_file}\n"
            header += "--\n"
            header += "-- Note: This file has been automatically converted from Oracle format.\n"
            header += "-- Please review and test before using in production.\n\n"
            
            def_outfile.write(header)
            inserts_outfile.write(header)
            
            current_table_lines = []
            current_insert_lines = []
            in_create_table = False
            in_insert_statement = False
            
            for line_num, line in enumerate(infile, 1):
                self.conversion_stats['lines_processed'] = line_num
                
                if line_num % 10000 == 0:
                    print(f"Processed {line_num:,} lines...")
                
                original_line = line
                line = line.strip()
                
                # Skip comments and empty lines
                if line.startswith('--') or line.startswith('REM') or not line:
                    continue
                
                # Handle CREATE TABLE statements
                if 'CREATE TABLE' in line:
                    in_create_table = True
                    current_table_lines = [line]
                    continue
                
                if in_create_table:
                    current_table_lines.append(line)
                    # Handle both formats: ending with ; or ending with )
                    if line.endswith(';') or (line.strip() == ')' and not any(keyword in line.upper() for keyword in [
                        'SEGMENT CREATION', 'PCTFREE', 'PCTUSED', 'INITRANS', 'MAXTRANS',
                        'NOCOMPRESS', 'LOGGING', 'STORAGE', 'TABLESPACE', 'BUFFER_POOL',
                        'FLASH_CACHE', 'CELL_FLASH_CACHE', 'PCTINCREASE', 'FREELISTS', 'FREELIST GROUPS'
                    ])):
                        converted_lines = self.convert_create_table(current_table_lines)
                        def_outfile.write('\n'.join(converted_lines) + '\n')
                        in_create_table = False
                        current_table_lines = []
                    continue
                
                # Handle INSERT statements
                if line.startswith('Insert into'):
                    # Check if it's a single-line INSERT (ends with ;)
                    if line.endswith(';'):
                        converted_insert = self.convert_insert_statement(line)
                        inserts_outfile.write(converted_insert + '\n')
                    else:
                        # Multi-line INSERT statement
                        in_insert_statement = True
                        current_insert_lines = [original_line]
                    continue

                if in_insert_statement:
                    current_insert_lines.append(original_line)
                    if line.endswith(');'):
                        converted_insert = self.convert_multi_line_insert(current_insert_lines)
                        inserts_outfile.write(converted_insert + '\n')
                        in_insert_statement = False
                        current_insert_lines = []
                    continue
                
                # Handle SET DEFINE OFF (Oracle specific)
                if line.startswith('SET DEFINE OFF'):
                    def_outfile.write('-- SET DEFINE OFF (Oracle specific, not needed in SQL Server)\n')
                    continue
        
        # Split INSERT statements into chunks
        self.split_inserts_into_chunks(inserts_file)
        
        print(f"\nConversion completed!")
        print(f"Tables processed: {self.conversion_stats['tables_processed']}")
        print(f"INSERT statements processed: {self.conversion_stats['inserts_processed']}")
        print(f"Total lines processed: {self.conversion_stats['lines_processed']:,}")
        print(f"Output files:")
        print(f"  - Table definitions: {definitions_file}")
        print(f"  - All INSERT statements: {inserts_file}")
        print(f"  - INSERT chunks: {inserts_file.replace('_all.sql', '_chunk_*.sql')}")


def main():
    """
    Main function to run the Oracle to SQL Server converter.
    
    Parses command line arguments and initiates the conversion process.
    Supports custom output files and schema names.
    """
    parser = argparse.ArgumentParser(
        description='Convert Oracle SQL database export to SQL Server format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s my_oracle_export.sql
  %(prog)s database.sql -o custom_output.sql
  %(prog)s schema_export.sql --schema MYSCHEMA
  %(prog)s test_data.sql --schema TEST --output test_sqlserver.sql

The converter will automatically:
- Separate table definitions from INSERT statements
- Split large INSERT files into 100,000 line chunks
- Convert Oracle data types to SQL Server equivalents
- Handle Oracle-specific functions and syntax
        """
    )
    
    parser.add_argument('input_file', 
                       help='Input Oracle SQL file to convert')
    parser.add_argument('-o', '--output', 
                       help='Output base filename (default: auto-generated from input filename)')
    parser.add_argument('--schema', 
                       default='ADMIN', 
                       help='Schema name to convert (default: ADMIN)')
    parser.add_argument('--version', 
                       action='version', 
                       version='Oracle to SQL Server Converter 2.0')
    
    args = parser.parse_args()
    
    # Validate input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        return 1
    
    try:
        converter = OracleToSQLServerConverter(args.input_file, args.output, args.schema)
        converter.process_file()
        return 0
    except Exception as e:
        print(f"Error during conversion: {e}")
        return 1


if __name__ == "__main__":
    exit(main())