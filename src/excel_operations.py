#!/usr/bin/env python3
import json
import sys
import xlwings as xw
import os

def get_workbook(file_path):
    """Get or open a workbook in the active Excel instance."""
    try:
        # Try to get the workbook if it's already open
        return xw.books[os.path.basename(file_path)]
    except:
        # If not found, look for any existing Excel instances
        try:
            app = xw.apps.active
        except:
            app = xw.App(visible=True)
        
        # Open or create the workbook
        if os.path.exists(file_path):
            return app.books.open(file_path)
        else:
            wb = app.books.add()
            wb.save(file_path)
            return wb

def create_workbook(args):
    """Create a new Excel workbook with specified sheets."""
    try:
        wb = get_workbook(args['file_path'])
        
        # If sheets are specified, create them
        if 'sheets' in args and args['sheets']:
            # First sheet already exists, rename it
            wb.sheets[0].name = args['sheets'][0]
            
            # Add additional sheets
            for sheet_name in args['sheets'][1:]:
                wb.sheets.add(name=sheet_name)
        
        wb.save()
        return {
            'success': True,
            'message': f"Workbook created at {args['file_path']}",
            'sheets': args.get('sheets', ['Sheet1'])
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def read_worksheet(args):
    """Read data from an Excel worksheet."""
    try:
        wb = get_workbook(args['file_path'])
        sheet = wb.sheets[args['sheet_name']]
        
        # If range is specified, read that range, otherwise read used range
        if 'range' in args:
            data = sheet.range(args['range']).value
        else:
            data = sheet.used_range.value
            
        # Convert data to list format
        if isinstance(data, (list, tuple)):
            data = [
                [str(cell) if cell is not None else None for cell in row]
                for row in data
            ]
        else:
            data = [[str(data) if data is not None else None]]
            
        return {
            'success': True,
            'data': data
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def write_worksheet(args):
    """Write data to an Excel worksheet."""
    try:
        wb = get_workbook(args['file_path'])
        
        # Ensure the sheet exists
        try:
            sheet = wb.sheets[args['sheet_name']]
        except:
            sheet = wb.sheets.add(name=args['sheet_name'])
        
        # Write the data starting at the specified range
        sheet.range(args['range']).value = args['data']
        
        # Save but keep the workbook open
        wb.save()
        
        return {
            'success': True,
            'message': f"Data written to {args['file_path']}, sheet: {args['sheet_name']}"
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def main():
    if len(sys.argv) != 3:
        print(json.dumps({
            'success': False,
            'error': 'Invalid number of arguments'
        }))
        sys.exit(1)
        
    command = sys.argv[1]
    try:
        args = json.loads(sys.argv[2])
    except json.JSONDecodeError:
        print(json.dumps({
            'success': False,
            'error': 'Invalid JSON arguments'
        }))
        sys.exit(1)
        
    # Command router
    command_map = {
        'create_workbook': create_workbook,
        'read_worksheet': read_worksheet,
        'write_worksheet': write_worksheet
    }
    
    if command not in command_map:
        print(json.dumps({
            'success': False,
            'error': f'Unknown command: {command}'
        }))
        sys.exit(1)
        
    result = command_map[command](args)
    print(json.dumps(result))

if __name__ == '__main__':
    main()