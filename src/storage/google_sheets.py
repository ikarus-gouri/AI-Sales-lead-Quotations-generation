"""Google Sheets integration for catalog data."""

import os
import json
from typing import Dict, List, Optional
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleSheetsStorage:
    """Upload catalog data to Google Sheets."""
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    def __init__(self, credentials_file: str = 'credentials.json'):
        """
        Initialize Google Sheets client.
        
        Args:
            credentials_file: Path to service account credentials JSON
        """
        self.credentials_file = credentials_file
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Sheets API using file or environment variable."""
        try:
            # First, try to load from environment variable (for HuggingFace Spaces)
            creds_json_str = os.getenv('GOOGLE_SHEETS_CREDS_JSON')
            
            if creds_json_str:
                # Parse JSON string from environment
                try:
                    creds_dict = json.loads(creds_json_str)
                    creds = Credentials.from_service_account_info(
                        creds_dict,
                        scopes=self.SCOPES
                    )
                    self.service = build('sheets', 'v4', credentials=creds)
                    print("✓ Google Sheets authenticated from environment variable")
                    return
                except json.JSONDecodeError as e:
                    print(f"⚠ Failed to parse GOOGLE_SHEETS_CREDS_JSON: {e}")
            
            # Fallback to credentials file
            if os.path.exists(self.credentials_file):
                creds = Credentials.from_service_account_file(
                    self.credentials_file,
                    scopes=self.SCOPES
                )
                self.service = build('sheets', 'v4', credentials=creds)
                print(f"✓ Google Sheets authenticated from {self.credentials_file}")
                return
            
            # No credentials found
            print(f"⚠ Google Sheets credentials not found")
            print("  Set GOOGLE_SHEETS_CREDS_JSON environment variable or")
            print(f"  Provide {self.credentials_file} file")
            self.service = None
            
        except Exception as e:
            print(f"⚠ Failed to authenticate with Google Sheets: {e}")
            self.service = None
    
    def _create_new_sheet(self, spreadsheet_id: str, sheet_name: str) -> Optional[int]:
        """
        Create a new sheet tab in the spreadsheet.
        
        Args:
            spreadsheet_id: The spreadsheet ID
            sheet_name: Name for the new sheet tab
            
        Returns:
            Sheet ID or None if failed
        """
        if not self.service:
            return None
        
        try:
            # Check if sheet already exists
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            for sheet in spreadsheet.get('sheets', []):
                if sheet['properties']['title'] == sheet_name:
                    print(f"ℹ Sheet '{sheet_name}' already exists, will overwrite data")
                    return sheet['properties']['sheetId']
            
            # Create new sheet
            request_body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': sheet_name
                        }
                    }
                }]
            }
            
            response = self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=request_body
            ).execute()
            
            sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']
            print(f"✓ Created new sheet tab: '{sheet_name}'")
            return sheet_id
            
        except HttpError as e:
            print(f"⚠ Failed to create new sheet: {e}")
            return None
    
    def create_spreadsheet(self, title: str) -> Optional[str]:
        """
        Create a new Google Spreadsheet.
        
        Args:
            title: Title for the spreadsheet
            
        Returns:
            Spreadsheet ID or None if failed
        """
        if not self.service:
            print("⚠ Google Sheets service not available")
            return None
        
        try:
            spreadsheet = {
                'properties': {
                    'title': title
                }
            }
            
            spreadsheet = self.service.spreadsheets().create(
                body=spreadsheet,
                fields='spreadsheetId'
            ).execute()
            
            spreadsheet_id = spreadsheet.get('spreadsheetId')
            print(f"✓ Created spreadsheet: {spreadsheet_id}")
            print(f"  URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
            
            return spreadsheet_id
        except HttpError as e:
            print(f"✗ Failed to create spreadsheet: {e}")
            return None
    
    def upload_data(
        self,
        spreadsheet_id: str,
        data: List[List],
        sheet_name: str = 'Product Catalog',
        header_row: Optional[List[str]] = None
    ) -> bool:
        """
        Upload data to a Google Sheet.
        
        Args:
            spreadsheet_id: The spreadsheet ID
            data: List of rows to upload
            sheet_name: Name of the sheet tab
            header_row: Optional header row
            
        Returns:
            True if successful, False otherwise
        """
        if not self.service:
            print("⚠ Google Sheets service not available")
            return False
        
        try:
            # Prepare data with header
            all_data = []
            if header_row:
                all_data.append(header_row)
            all_data.extend(data)
            
            # Create a new sheet tab with the specified name
            self._create_new_sheet(spreadsheet_id, sheet_name)
            
            # Upload new data to the new sheet
            body = {
                'values': all_data
            }
            
            result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f'{sheet_name}!A1',
                valueInputOption='RAW',
                body=body
            ).execute()
            
            print(f"✓ Uploaded {result.get('updatedCells')} cells to Google Sheets")
            return True
            
        except HttpError as e:
            print(f"✗ Failed to upload data: {e}")
            return False
    
    def format_sheet(self, spreadsheet_id: str, sheet_name: str = 'Sheet1'):
        """
        Apply formatting to the sheet (bold headers, freeze rows, etc.).
        
        Args:
            spreadsheet_id: The spreadsheet ID
            sheet_name: Name of the sheet tab
        """
        if not self.service:
            return
        
        try:
            # Get sheet ID
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            sheet_id = None
            for sheet in spreadsheet['sheets']:
                if sheet['properties']['title'] == sheet_name:
                    sheet_id = sheet['properties']['sheetId']
                    break
            
            if sheet_id is None:
                # Default to first sheet
                sheet_id = spreadsheet['sheets'][0]['properties']['sheetId']
            
            # Format requests
            requests = [
                # Freeze header row
                {
                    'updateSheetProperties': {
                        'properties': {
                            'sheetId': sheet_id,
                            'gridProperties': {
                                'frozenRowCount': 1
                            }
                        },
                        'fields': 'gridProperties.frozenRowCount'
                    }
                },
                # Bold header row
                {
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'textFormat': {
                                    'bold': True
                                },
                                'backgroundColor': {
                                    'red': 0.9,
                                    'green': 0.9,
                                    'blue': 0.9
                                }
                            }
                        },
                        'fields': 'userEnteredFormat(textFormat,backgroundColor)'
                    }
                },
                # Auto-resize columns
                {
                    'autoResizeDimensions': {
                        'dimensions': {
                            'sheetId': sheet_id,
                            'dimension': 'COLUMNS',
                            'startIndex': 0,
                            'endIndex': 10
                        }
                    }
                }
            ]
            
            body = {
                'requests': requests
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=body
            ).execute()
            
            print("✓ Applied formatting to sheet")
            
        except HttpError as e:
            print(f"⚠ Failed to format sheet: {e}")
    
    def apply_color_formatting(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        color_cell_map: List[tuple]
    ):
        """
        Apply background colors to specific cells based on hex codes.
        
        Args:
            spreadsheet_id: The spreadsheet ID
            sheet_name: Name of the sheet tab
            color_cell_map: List of tuples (row_index, col_index, hex_color)
        """
        if not self.service or not color_cell_map:
            return
        
        try:
            # Get sheet ID
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            sheet_id = None
            for sheet in spreadsheet['sheets']:
                if sheet['properties']['title'] == sheet_name:
                    sheet_id = sheet['properties']['sheetId']
                    break
            
            if sheet_id is None:
                return
            
            # Build format requests for each color cell
            requests = []
            
            for row_idx, col_idx, hex_color in color_cell_map:
                # Parse hex color (e.g., "#FF5733")
                hex_color = hex_color.lstrip('#')
                if len(hex_color) != 6:
                    continue
                
                try:
                    r = int(hex_color[0:2], 16) / 255.0
                    g = int(hex_color[2:4], 16) / 255.0
                    b = int(hex_color[4:6], 16) / 255.0
                except:
                    continue
                
                # Determine text color based on background brightness
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                text_color = {
                    'red': 0.0 if brightness > 0.5 else 1.0,
                    'green': 0.0 if brightness > 0.5 else 1.0,
                    'blue': 0.0 if brightness > 0.5 else 1.0
                }
                
                requests.append({
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': row_idx,
                            'endRowIndex': row_idx + 1,
                            'startColumnIndex': col_idx,
                            'endColumnIndex': col_idx + 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'backgroundColor': {
                                    'red': r,
                                    'green': g,
                                    'blue': b
                                },
                                'textFormat': text_color
                            }
                        },
                        'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                    }
                })
            
            if requests:
                body = {'requests': requests}
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body=body
                ).execute()
                
                print(f"✓ Applied color formatting to {len(requests)} cells")
                
        except HttpError as e:
            print(f"⚠ Failed to apply color formatting: {e}")
    
    def save_catalog(
        self,
        catalog: Dict,
        spreadsheet_id: Optional[str] = None,
        title: str = "Product Catalog",
        sheet_name: Optional[str] = None,
        include_prices: bool = True
    ) -> Optional[str]:
        """
        Save catalog to Google Sheets.
        
        Args:
            catalog: The product catalog
            spreadsheet_id: Existing spreadsheet ID (creates new if None, or uses default from env)
            title: Title for new spreadsheet
            sheet_name: Name for the sheet tab (auto-generated with timestamp if None)
            include_prices: Whether to include prices column
            
        Returns:
            Spreadsheet ID or None if failed
        """
        if not self.service:
            print("⚠ Cannot save to Google Sheets - service not available")
            return None
        
        # Use default spreadsheet ID from environment if not provided
        if not spreadsheet_id:
            spreadsheet_id = os.getenv('GOOGLE_SPREADSHEET_ID')
            if spreadsheet_id:
                print(f"ℹ Using default spreadsheet ID from environment: {spreadsheet_id}")
        
        # Create spreadsheet if still no ID
        if not spreadsheet_id:
            spreadsheet_id = self.create_spreadsheet(title)
            if not spreadsheet_id:
                return None
        
        # Generate sheet name with timestamp if not provided
        if not sheet_name:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sheet_name = f"Catalog {timestamp}"
        
        # Prepare data
        rows = []
        
        for product_id, product_data in catalog.items():
            product_name = product_data.get('product_name', 'Unknown Product')
            base_price = product_data.get('base_price') or 'N/A'
            product_url = product_data.get('url', '')
            specifications = product_data.get('specifications', {})

            # Product header
            if include_prices:
                rows.append([
                    f"Base Model({product_name})",
                    product_name,
                    base_price,
                    '',
                    '',
                    product_url
                ])
            else:
                rows.append([
                    f"Base Model({product_name})",
                    product_name,
                    '',
                    product_url
                ])
            
            # Specifications section
            if specifications:
                rows.append(['', '', '', '', '', ''])  # Empty row for spacing
                rows.append(['Specifications', '', '', '', '', ''])
                
                for spec_key, spec_value in specifications.items():
                    if include_prices:
                        rows.append([
                            '',
                            f"{spec_key}: {spec_value}",
                            '',
                            '',
                            'Specification',
                            ''
                        ])
                    else:
                        rows.append([
                            '',
                            f"{spec_key}: {spec_value}",
                            '',
                            'Specification'
                        ])
                
                rows.append(['', '', '', '', '', ''])  # Empty row after specs

            # Customization categories
            customizations = product_data.get('customizations', {})
            color_cell_map = []  # Track which cells need color formatting: [(row, col, hex_color)]
            
            # Group options by model (if model field exists)
            model_grouped = {}
            for category, options in customizations.items():
                if not options:
                    continue
                
                for option in options:
                    if isinstance(option, dict):
                        model_key = option.get('model', 'General')  # Group by model or 'General' if no model
                    else:
                        model_key = 'General'
                    
                    if model_key not in model_grouped:
                        model_grouped[model_key] = {}
                    if category not in model_grouped[model_key]:
                        model_grouped[model_key][category] = []
                    model_grouped[model_key][category].append(option)
            
            # Output grouped by model
            for model_key in sorted(model_grouped.keys()):
                # Add model header if there are multiple models
                if len(model_grouped) > 1:
                    rows.append(['', '', '', '', '', ''])  # Spacing
                    if include_prices:
                        rows.append([
                            f"═══ {model_key} ═══",
                            '',
                            '',
                            '',
                            f'Model Configuration',
                            ''
                        ])
                    else:
                        rows.append([
                            f"═══ {model_key} ═══",
                            '',
                            '',
                            f'Model Configuration'
                        ])
                
                # Output categories for this model
                for category, options in model_grouped[model_key].items():
                    if not options:
                        continue
                        
                    for i, option in enumerate(options):
                        # Handle both dict and string option types
                        if isinstance(option, dict):
                            label = option.get('label', str(option))
                            price = option.get('price', '')
                            image = option.get('image', '')
                            hex_color = option.get('hex_color', '')
                        else:
                            label = str(option)
                            price = ''
                            image = ''
                            hex_color = ''
                        
                        current_row = len(rows) + 1  # +1 for header row
                        
                        if include_prices:
                            rows.append([
                                category if i == 0 else '',
                                label,
                                price,
                                image,
                                f"Category: {category}",
                                ''
                            ])
                            # Track color cell (column B = index 1, 0-indexed)
                            if hex_color:
                                color_cell_map.append((current_row, 1, hex_color))
                        else:
                            rows.append([
                                category if i == 0 else '',
                                label,
                                image,
                                ''
                            ])
                            if hex_color:
                                color_cell_map.append((current_row, 1, hex_color))
        
        # Header row
        header = ['Categories', 'Component', 'Price', 'Image', 'Notes', 'References'] if include_prices else ['Categories', 'Component', 'Image', 'References']
        
        # Upload data
        success = self.upload_data(spreadsheet_id, rows, sheet_name=sheet_name, header_row=header)
        
        if success:
            # Apply formatting
            self.format_sheet(spreadsheet_id, sheet_name=sheet_name)
            
            # Apply color formatting to color cells
            if color_cell_map:
                self.apply_color_formatting(spreadsheet_id, sheet_name, color_cell_map)
            
            print(f"\n✓ Catalog uploaded to Google Sheets")
            print(f"  Sheet: '{sheet_name}'")
            print(f"  URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}\n")
            return spreadsheet_id
        
        return None