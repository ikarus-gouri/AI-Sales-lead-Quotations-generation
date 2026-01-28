"""Google Sheets integration for catalog data."""

import os
import json
from typing import Dict, List, Optional
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
            
            # Clear existing data
            try:
                self.service.spreadsheets().values().clear(
                    spreadsheetId=spreadsheet_id,
                    range='Sheet1!A1:Z'
                ).execute()
            except HttpError:
                # Sheet might not exist or might be empty
                pass
            
            # Upload new data
            body = {
                'values': all_data
            }
            
            result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range='Sheet1!A1',
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
    
    def save_catalog(
        self,
        catalog: Dict,
        spreadsheet_id: Optional[str] = None,
        title: str = "Product Catalog",
        include_prices: bool = True
    ) -> Optional[str]:
        """
        Save catalog to Google Sheets.
        
        Args:
            catalog: The product catalog
            spreadsheet_id: Existing spreadsheet ID (creates new if None, or uses default from env)
            title: Title for new spreadsheet
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
        
        # Prepare data
        rows = []
        
        for product_id, product_data in catalog.items():
            product_name = product_data.get('product_name', 'Unknown Product')
            base_price = product_data.get('base_price') or 'N/A'
            product_url = product_data.get('url', '')

            # Product header
            if include_prices:
                rows.append([
                    f"Base Model({product_name})",
                    product_name,
                    base_price,
                    product_url,
                    ''
                ])
            else:
                rows.append([
                    f"Base Model({product_name})",
                    product_name,
                    product_url
                ])

            # Customization categories
            customizations = product_data.get('customizations', {})
            for category, options in customizations.items():
                if not options:
                    continue
                    
                for i, option in enumerate(options):
                    # Handle both dict and string option types
                    if isinstance(option, dict):
                        label = option.get('label', str(option))
                        price = option.get('price', '')
                        image = option.get('image', '')
                    else:
                        label = str(option)
                        price = ''
                        image = ''
                    
                    if include_prices:
                        rows.append([
                            category if i == 0 else '',
                            label,
                            price,
                            image,
                            f"Category: {category}"
                        ])
                    else:
                        rows.append([
                            category if i == 0 else '',
                            label,
                            image
                        ])
        
        # Header row
        header = ['Categories', 'Component', 'Price', 'References', 'Notes'] if include_prices else ['Categories', 'Component', 'References']
        
        # Upload data
        success = self.upload_data(spreadsheet_id, rows, header_row=header)
        
        if success:
            # Apply formatting
            self.format_sheet(spreadsheet_id)
            print(f"\n✓ Catalog uploaded to Google Sheets")
            print(f"  URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}\n")
            return spreadsheet_id
        
        return None