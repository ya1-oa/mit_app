import pandas as pd
import numpy as np
import re
from .core import WebAutomator, WebAutomationError
from typing import Dict, Any, List, Optional, Tuple, Union
import time
import os
import json
import subprocess
import sys
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
    StaleElementReferenceException
)
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

class RoomTemplateAutomation:
    def __init__(self, headless: bool = True):
        # Initialize with Chromium-only automator
        try:
            self.automator = WebAutomator(headless=headless)
            self._log("RoomTemplateAutomation initialized successfully")
            self._force_browser_ready()
        except Exception as e:
            self._log(f"Failed to initialize RoomTemplateAutomation: {str(e)}", "ERROR")
            raise
    
    def _log(self, message: str, level: str = "INFO"):
        """Log messages with timestamps"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}", file=sys.stderr)

    def _force_browser_ready(self):
        """Ensure browser is fully ready before any interaction"""
        try:
            # Set explicit window size
            self.automator.driver.set_window_size(1920, 1080)
            
            # Wait for all initializations to complete
            WebDriverWait(self.automator.driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            self._log("Browser ready check completed")
        except Exception as e:
            self._log(f"Browser initialization warning: {str(e)}", "WARNING")

    def _save_debug_info(self, prefix: str = "error"):
        """Save comprehensive debug information"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_dir = "debug_logs"
        os.makedirs(debug_dir, exist_ok=True)
        
        try:
            debug_info = {}
            
            # Save screenshot
            screenshot_path = f"{debug_dir}/{prefix}_{timestamp}.png"
            self.automator.driver.save_screenshot(screenshot_path)
            debug_info["screenshot"] = screenshot_path
            
            # Save page source
            page_source_path = f"{debug_dir}/{prefix}_page_source_{timestamp}.html"
            with open(page_source_path, "w", encoding="utf-8") as f:
                f.write(self.automator.driver.page_source)
            debug_info["page_source"] = page_source_path
            
            # Save browser logs if available
            try:
                logs = self.automator.driver.get_log("browser")
                log_path = f"{debug_dir}/{prefix}_console_logs_{timestamp}.json"
                with open(log_path, "w") as f:
                    json.dump(logs, f)
                debug_info["logs"] = log_path
            except Exception as log_error:
                self._log(f"Could not save browser logs: {str(log_error)}", "WARNING")
            
            self._log(f"Debug info saved: {debug_info}")
            return debug_info
            
        except Exception as e:
            self._log(f"Could not save debug info: {str(e)}", "ERROR")
            return {"error": str(e)}

    def _wait_for_page_transition(self, timeout=30):
        """Wait for page to fully transition after navigation"""
        try:
            original_handles = self.automator.driver.window_handles
            
            # Wait for document ready state
            WebDriverWait(self.automator.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # If new window opened, switch to it
            if len(self.automator.driver.window_handles) > len(original_handles):
                new_window = [h for h in self.automator.driver.window_handles 
                             if h not in original_handles][0]
                self.automator.driver.switch_to.window(new_window)
                
            # Additional wait for frameworks
            try:
                WebDriverWait(self.automator.driver, 10).until(
                    lambda d: d.execute_script("return (typeof jQuery === 'undefined') || jQuery.active == 0"))
            except:
                pass
                
            self._log("Page transition completed")
                
        except Exception as e:
            self._log(f"Page transition warning: {str(e)}", "WARNING")
            self._save_debug_info("transition_warning")

    def _find_element_with_fallbacks(self, selector_options: List[Dict[str, Any]], timeout: int = 10) -> WebElement:
        """Helper to try multiple selector options"""
        for selector in selector_options:
            try:
                return WebDriverWait(self.automator.driver, timeout).until(
                    EC.presence_of_element_located((selector['by'], selector['value']))
                )
            except:
                continue
        raise NoSuchElementException(f"Could not find element with any selector: {selector_options}")

    def _is_element_present(self, by, value, timeout=5) -> bool:
        """Helper to check if element exists without throwing exception"""
        try:
            WebDriverWait(self.automator.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return True
        except:
            return False

    def login(self, email: str, password: str) -> bool:
        """Handle the login process with proper tab management"""
        try:
            self._log("Starting login process")
            
            # Define login page elements
            login_page = {
                'login_button': {'by': By.CSS_SELECTOR, 'value': 'a.button_2[href*="login"]'},
                'email_input': {'by': By.ID, 'value': 'username'},
                'email_continue': {'by': By.CSS_SELECTOR, 'value': 'button._button-login-id'},
                'password_input': {'by': By.ID, 'value': 'password'},
                'password_continue': {'by': By.CSS_SELECTOR, 'value': 'button._button-login-password'}
            }
            self.automator.define_page('login', login_page)
            
            # Execute login flow
            self.automator.navigate_to('https://encircleapp.com/')
            
            # Store original window handle
            original_window = self.automator.driver.current_window_handle
            
            # Click the login button (will open new tab)
            self.automator.click('login_button', page_name='login')
            
            # Wait for new window to appear and switch to it
            WebDriverWait(self.automator.driver, 10).until(
                lambda d: len(d.window_handles) > 1
            )
            
            # Switch to the new tab
            new_window = [window for window in self.automator.driver.window_handles 
                         if window != original_window][0]
            self.automator.driver.switch_to.window(new_window)
            
            # Verify we're on the login page
            try:
                WebDriverWait(self.automator.driver, 10).until(
                    lambda d: "login" in d.current_url.lower() or 
                             "auth" in d.current_url.lower() or
                             "signin" in d.current_url.lower()
                )
            except TimeoutException:
                raise Exception("Failed to verify login page URL")
            
            # First login page (email)
            self.automator.wait_for_element('email_input', page_name='login', timeout=10)
            self.automator.input_text('email_input', email, page_name='login')
            self.automator.click('email_continue', page_name='login')
            
            # Second login page (password)
            self.automator.wait_for_element('password_input', page_name='login', timeout=10)
            self.automator.input_text('password_input', password, page_name='login')
            self.automator.click('password_continue', page_name='login')
            
            # Verify login success
            try:
                WebDriverWait(self.automator.driver, 15).until(
                    lambda d: "dashboard" in d.current_url.lower() or
                             any(x in d.current_url.lower() for x in ["home", "app", "workspace"])
                )
                self._log("Login successful")
                return True
            except TimeoutException:
                raise Exception("Failed to verify successful login")
                
        except Exception as e:
            self._log(f"Login failed: {str(e)}", "ERROR")
            self._save_debug_info("login_failure")
            return False

    def navigate_to_org_settings(self) -> bool:
        """Navigate through User Settings → Organization Settings → Manage Lists"""
        debug_info = {
            'start_url': self.automator.driver.current_url,
            'steps': []
        }
        
        try:
            # 1. Click User Settings button
            try:
                user_settings = WebDriverWait(self.automator.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.NewNavigation-button'))
                )
                self.automator.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", user_settings)
                time.sleep(0.3)
                user_settings.click()
                debug_info['steps'].append({'action': 'click_user_settings', 'status': 'success'})
                time.sleep(1)  # Allow menu to open
            except Exception as e:
                debug_info['steps'].append({'action': 'click_user_settings', 'status': 'failed', 'error': str(e)})
                raise Exception("Could not find User Settings button")

            # 2. Click Organization Settings
            try:
                org_settings = WebDriverWait(self.automator.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//div[contains(@class, "SettingsDropdownMenuLinkItem-content") and contains(text(), "Organization Settings")]'))
                )
                self.automator.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", org_settings)
                time.sleep(0.3)
                org_settings.click()
                debug_info['steps'].append({'action': 'click_org_settings', 'status': 'success'})
                
                # Wait for navigation to complete
                WebDriverWait(self.automator.driver, 15).until(
                    lambda d: "settings/org" in d.current_url.lower()
                )
                time.sleep(1)  # Allow page to settle
            except Exception as e:
                debug_info['steps'].append({'action': 'click_org_settings', 'status': 'failed', 'error': str(e)})
                raise Exception("Could not find Organization Settings option")

            return True

        except Exception as e:
            debug_info['error'] = str(e)
            debug_info['final_url'] = self.automator.driver.current_url
            debug_info['screenshot'] = self._save_debug_info("org_settings_nav_failure")
            self._log(f"Navigation failed: {json.dumps(debug_info, indent=2)}", "ERROR")
            return False

    def navigate_to_manage_lists(self) -> bool:
        """Click the Manage Lists link on the Organization Settings page"""
        try:
            # Find and click Manage Lists link with minimal waiting
            manage_lists = WebDriverWait(self.automator.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[href*="/lists"]'))
            )
            
            # Quick scroll into view and click
            self.automator.driver.execute_script("arguments[0].scrollIntoView();", manage_lists)
            self.automator.driver.execute_script("arguments[0].click();", manage_lists)
            
            # Brief pause to allow navigation
            time.sleep(2)
            
            return True

        except Exception:
            # If we fail, just continue assuming we're on the right page
            self._log("Failed to navigate to manage lists, continuing anyway", "WARNING")
            return True

def delete_all_templates(self) -> dict:
    """Delete ALL templates under Room Templates regardless of name"""
    results = {
        'templates_deleted': 0,
        'errors': [],
        'details': []
    }
    
    try:
        self._log("Attempting to delete ALL existing templates")
        
        # Refresh page to ensure we have current template list
        self.automator.driver.refresh()
        time.sleep(3)  # Give more time for page to load
        
        # Wait for the SimpleList to load
        WebDriverWait(self.automator.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.SimpleList-row'))
        )
        
        # Get all template rows
        template_rows = self.automator.driver.find_elements(By.CSS_SELECTOR, '.SimpleList-row')
        self._log(f"Found {len(template_rows)} template rows to delete")
        
        # Keep deleting until no templates remain
        while template_rows:
            for row in template_rows:
                try:
                    # Get the template name for logging
                    try:
                        title_element = row.find_element(
                            By.CSS_SELECTOR, 
                            '.SimpleList-row-header-info-title'
                        )
                        template_name = title_element.text.strip()
                    except:
                        template_name = "Unknown Template"
                    
                    self._log(f"Deleting template: {template_name}")
                    
                    # Find the delete button in this row
                    delete_button = row.find_element(
                        By.CSS_SELECTOR, 
                        '.ActionIcon--delete'
                    )
                    
                    # Scroll into view and click delete
                    self.automator.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", delete_button)
                    time.sleep(0.5)
                    
                    # Click using JavaScript to avoid interception
                    self.automator.driver.execute_script("arguments[0].click();", delete_button)
                    time.sleep(1)  # Wait for modal to appear
                    
                    # Confirm deletion - wait for the modal and click confirm button
                    try:
                        WebDriverWait(self.automator.driver, 5).until(
                            EC.visibility_of_element_located((
                            By.CSS_SELECTOR, 
                            'div.BaseModal-backdrop--floating'
                            ))
                        )

                        # Then wait for the delete button to be clickable
                        confirm_button = WebDriverWait(self.automator.driver, 5).until(
                            EC.element_to_be_clickable((
                            By.CSS_SELECTOR, 
                            'button.analytics-DELETE_BUTTON'
                            ))
                        )
                        
                        # Click confirm using JavaScript
                        self.automator.driver.execute_script("arguments[0].click();", confirm_button)
                        time.sleep(2)  # Wait for deletion to complete
                        
                        results['templates_deleted'] += 1
                        results['details'].append({
                            'template': template_name,
                            'status': 'deleted'
                        })
                        self._log(f"Successfully deleted template: {template_name}")
                        
                        # Break out of the inner loop and refresh the template list
                        break
                        
                    except Exception as confirm_error:
                        error_msg = f"Failed to confirm deletion for '{template_name}': {str(confirm_error)}"
                        results['errors'].append(error_msg)
                        results['details'].append({
                            'template': template_name,
                            'status': 'failed',
                            'error': str(confirm_error)
                        })
                        self._log(error_msg, "WARNING")
                        
                        # Try to close the modal if confirmation failed
                        try:
                            cancel_button = self.automator.driver.find_element(
                                By.CSS_SELECTOR,
                                'div.BaseModal-backdrop--floating button:not(.Button--danger)'
                            )
                            cancel_button.click()
                            time.sleep(1)
                        except:
                            pass
                        continue
                    
                except Exception as row_error:
                    error_msg = f"Error processing template row: {str(row_error)}"
                    results['errors'].append(error_msg)
                    self._log(error_msg, "WARNING")
                    continue
            
            # Refresh the template rows list after deletion attempt
            time.sleep(2)
            template_rows = self.automator.driver.find_elements(By.CSS_SELECTOR, '.SimpleList-row')
            self._log(f"Remaining templates: {len(template_rows)}")
            
            # Safety check to prevent infinite loop
            if len(template_rows) >= results['templates_deleted'] + len(results['errors']):
                self._log("No progress made in deletion loop, breaking out", "WARNING")
                break
        
        self._log(f"Deleted {results['templates_deleted']} templates successfully")
        return results
        
    except Exception as e:
        error_msg = f"Error in template deletion process: {str(e)}"
        results['errors'].append(error_msg)
        self._log(error_msg, "ERROR")
        return results

# Also update the delete_existing_templates method to use the new delete_all_templates method
def delete_existing_templates(self, template_names: List[str] = None) -> dict:
    """Delete existing templates - now supports deleting ALL templates"""
    if template_names is None:
        # If no specific names provided, delete ALL templates
        return self.delete_all_templates()
    else:
        # Original logic for deleting specific templates
        results = {
            'templates_deleted': 0,
            'errors': [],
            'details': []
        }
        
        try:
            self._log(f"Attempting to delete {len(template_names)} specific templates")
            
            # Refresh page to ensure we have current template list
            self.automator.driver.refresh()
            time.sleep(3)
            
            # Wait for the SimpleList to load
            WebDriverWait(self.automator.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.SimpleList-row'))
            )
            
            # Get all template rows
            template_rows = self.automator.driver.find_elements(By.CSS_SELECTOR, '.SimpleList-row')
            self._log(f"Found {len(template_rows)} template rows")
            
            for template_name in template_names:
                # ... keep the original specific deletion logic here ...
                # (your existing delete_existing_templates method code for specific names)
                pass
                
        except Exception as e:
            error_msg = f"Error in template deletion process: {str(e)}"
            results['errors'].append(error_msg)
            self._log(error_msg, "ERROR")
        
        return results

    def create_room_template(self, template_name: str, room_names: list) -> dict:
        """Create room template using Enter key instead of button clicks"""
        results = {
            'status': 'started',
            'template_name': template_name,
            'rooms_added': 0,
            'errors': []
        }

        try:
            # Define elements (no longer need add_room_btn)
            elements = {
                'add_template_btn': (By.XPATH, '//button[.//span[contains(., "Add Room Template")]]'),
                'template_name_input': (By.CSS_SELECTOR, 'input.InnerTextInput-input--primary'),
                'room_name_input': (By.CSS_SELECTOR, 'div.RoomListInput-addName-input input'),
                'save_btn': (By.XPATH, '//button[.//span[contains(., "Save")]]')
            }

            # 1. Add Template
            add_btn = WebDriverWait(self.automator.driver, 10).until(
                EC.element_to_be_clickable(elements['add_template_btn'])
            )
            add_btn.click()
            time.sleep(0.5)

            # 2. Enter Template Name
            name_input = WebDriverWait(self.automator.driver, 10).until(
                EC.element_to_be_clickable(elements['template_name_input'])
            )
            name_input.clear()
            name_input.send_keys(template_name)

            # 3. Add Rooms using Enter key
            for room_name in room_names:
                try:
                    # Enter room name
                    room_input = WebDriverWait(self.automator.driver, 5).until(
                        EC.element_to_be_clickable(elements['room_name_input'])
                    )
                    room_input.clear()
                    
                    # Type room name and press Enter twice
                    room_input.send_keys(room_name)
                    time.sleep(0.2)
                    room_input.send_keys(Keys.RETURN)
                    time.sleep(0.2)
                    room_input.send_keys(Keys.RETURN)
                    
                    # Verify room was added
                    try:
                        WebDriverWait(self.automator.driver, 3).until(
                            EC.presence_of_element_located((By.XPATH, f'//*[contains(., "{room_name}")]'))
                        )
                        results['rooms_added'] += 1
                    except:
                        self._log(f"Warning: Room '{room_name}' may not have been added", "WARNING")
                    
                    time.sleep(0.3)
                    
                except Exception as e:
                    error_msg = f"Failed to add room '{room_name}': {str(e)}"
                    results['errors'].append(error_msg)
                    self._log(error_msg, "ERROR")
                    continue

            # 4. Save Template (still using click)
            save_btn = WebDriverWait(self.automator.driver, 10).until(
                EC.element_to_be_clickable(elements['save_btn'])
            )
            save_btn.click()
            
            # Verify save
            try:
                WebDriverWait(self.automator.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.Notifier__notification--success'))
                )
                results['status'] = 'completed'
                self._log(f"Template '{template_name}' saved successfully")
            except:
                results['status'] = 'completed_with_warnings'
                self._log(f"Warning: Could not verify save completion for '{template_name}'", "WARNING")

            # Wait a moment before continuing to next template
            time.sleep(1)

        except Exception as e:
            error_msg = f"Critical error in template creation for '{template_name}': {str(e)}"
            results.update({
                'status': 'failed',
                'error': error_msg
            })
            self._log(error_msg, "ERROR")

        return results


    def get_template_configurations(self) -> List[Dict]:
        """Define configurations for different templates to be generated"""
        return [
            {
                'id': 'readings default',
                'name': '70000 Readings Default', 
                'description': 'Fifth template with readings data',
                'column_ranges': [83],  # Updated columns
                'priority': 5,
                'use_qr_columns': True
            },
            {
                'id': 'basic',
                'name': '100-800 Base List',
                'description': 'First template with basic room data',
                'column_ranges': [19, 24, 29, 40, 45],  # T=20, Y=25, AD=30, AO=41
                'priority': 3,
                'use_qr_columns': True
            },
            {
                'id': 'extended',
                'name': '400 PPR List', 
                'description': 'Second template with extended room data',
                'column_ranges': [30],  # AJ=36
                'priority': 2,
                'use_qr_columns': True
            },
            {
                'id': 'readings',
                'name': '6000-7000 Readings List', 
                'description': 'Third template with readings data',
                'column_ranges': [50, 55, 60, 65, 70],  # AT=46, AZ=52, BE=57, BK=63, BQ=69
                'priority': 1,
                'use_qr_columns': True
            }
        ]
            
    def _extract_rooms_from_excel_by_config(self, file_path: str, config: Dict) -> List[str]:
        """Extract rooms from Excel combining section values with Q/R columns"""
        try:
            self._log(f"Extracting rooms for template '{config['name']}' using section ranges + Q/R columns")
            
            # Read the Excel file
            df = pd.read_excel(
                file_path,
                sheet_name='ROOMS#',
                header=None,
                na_values=['', '-', 'NaN', 'N/A', 'nan']
            )
            
            # Count actual room names in column Q (column index 16)
            user_room_count = 0
            q_column_data = df.iloc[3:, 16]  # Column Q, starting from row 3
            for cell_value in q_column_data:
                if (pd.notna(cell_value) and 
                    str(cell_value).strip() not in ['', '-', 'nan', '0']):
                    user_room_count += 1
                elif pd.isna(cell_value) or str(cell_value).strip() in ['', '-', 'nan', '0']:
                    # Stop counting when we hit empty cells (end of room names)
                    break
            print(f"user room count = {user_room_count}")
            
            self._log(f"Found {user_room_count} room names in column Q")
            
            all_rooms = []
            use_qr_columns = config.get('use_qr_columns', True)
            
            # Process each column range specified in the config
            for current_col in config['column_ranges']:
                self._log(f"Processing column range starting at {current_col}")
                
                try:
                    # Check for data in the first column of this section
                    section_data = df.iloc[2:, current_col]  # Start from row 3
                    used_rows = []
                    
                    for row_idx, cell_value in enumerate(section_data, start=2):
                        if pd.notna(cell_value) and str(cell_value).strip() not in ['', '-', 'nan', '0']:
                            used_rows.append(row_idx)
                            self._log(f"DEBUG: Found data in row {row_idx}: '{cell_value}'")
                    
                    self._log(f"DEBUG: used_rows for column {current_col}: {used_rows}")
                    
                    if not used_rows:
                        self._log(f"No data found in section starting at column {current_col}")
                        continue
                    
                    # Determine how many rows to process based on template type
                    if config['id'] == 'readings default':
                        # Readings default template: process ALL rows until we reach zero/empty
                        rows_to_process = used_rows
                    elif config['id'] == 'readings':
                        # For 6000-7000 readings: check if this is the 7000s section
                        is_7000s_section = (current_col == config['column_ranges'][-1])
                        
                        if is_7000s_section:
                            # 7000s section: process ALL rows like default
                            rows_to_process = used_rows
                        else:
                            # 6000s sections: process header + user room count (LIMITED)
                            max_rows = 1 + user_room_count  # 1 header + user rooms
                            rows_to_process = used_rows[:max_rows]
                    else:
                        # For 100-800 and 400 PPR: process header + user room count
                        max_rows = 1 + user_room_count  # 1 header + user rooms
                        rows_to_process = used_rows[:max_rows]
                    
                    # Process the determined rows
                    for row_position, row_idx in enumerate(rows_to_process):
                        try:
                            # Get room number from the section (always required)
                            room_number = df.iloc[row_idx, current_col]
                            
                            # Skip if room number is missing
                            if (pd.isna(room_number) or str(room_number).strip() in ['', '-', 'nan', '0']):
                                continue
                            
                            # Check if this is the first row (header) in the section
                            is_header = (row_position == 0)
                            
                            # Headers are always processed, skip room name validation for headers
                            if not is_header:
                                # Determine if this template/section requires room names to process rows
                                requires_room_name_to_process = True
                                
                                # Templates/sections that DON'T require room names to process rows:
                                if (config['id'] == 'readings' and 
                                      current_col == config['column_ranges'][-1]):  # 7000s section ONLY
                                        requires_room_name_to_process = False
                                # Note: 6000s sections (config['id'] == 'readings' but not last column) 
                                # DO require room names, so requires_room_name_to_process stays True
                                
                                # If room name is required to process the row, check if it exists
                                if requires_room_name_to_process:
                                    try:
                                        room_name_cell = df.iloc[row_idx, 16]  # Column Q
                                        has_room_name = (pd.notna(room_name_cell) and 
                                                       str(room_name_cell).strip() not in ['', '-', 'nan', '0', 'Room Name'])
                                        
                                        if not has_room_name:
                                            self._log(f"Skipping row {row_idx} - no room name in column Q (required for this template)")
                                            continue
                                    except IndexError:
                                        self._log(f"Skipping row {row_idx} - cannot access column Q (required for this template)")
                                        continue
                            
                            # Initialize room parts list
                            room_parts = []
                            
                            # Add room number (always first)
                            room_parts.append(str(room_number).strip())
                            
                            # Determine processing method based on template and section
                            if config['id'] == 'readings' and current_col == config['column_ranges'][-1]:
                                # 7000s section (last column): capture all section data, no Q/R columns
                                self._add_section_data_only(df, row_idx, current_col, room_parts)
                            elif config['id'] == 'readings' or use_qr_columns:
                                # 6000s sections (first 4 columns) and other templates: combine section data with Q/R columns
                                self._add_section_and_qr_data(df, row_idx, current_col, room_parts, is_header)
                            else:
                                # Readings default template: capture all section data, no Q/R columns
                                self._add_section_data_only(df, row_idx, current_col, room_parts)
                            
                            # Create the room entry
                            if room_parts:
                                room_entry = ' '.join(filter(None, room_parts))  # Remove empty strings
                                all_rooms.append(room_entry)
                                self._log(f"Added room: {room_entry}")
                                
                        except IndexError:
                            break
                            
                except Exception as section_error:
                    self._log(f"Error processing section at column {current_col}: {str(section_error)}", "WARNING")
                    continue
                    
            self._log(f"Extracted {len(all_rooms)} rooms for template '{config['name']}'")
            return all_rooms
            
        except Exception as e:
            self._log(f"Excel processing error for '{config['name']}': {str(e)}", "ERROR")
            raise WebAutomationError(f"Excel processing failed for '{config['name']}': {str(e)}")
        
    def _add_section_data_only(self, df, row_idx: int, current_col: int, room_parts: list):
        """Add only section data to room parts (for 7000s and default templates)"""
        # Capture data from the section columns (typically 5 columns per section)
        max_cols_to_check = min(5, df.shape[1] - current_col)
        
        for col_offset in range(1, max_cols_to_check):
            try:
                cell_value = df.iloc[row_idx, current_col + col_offset]
                if (pd.notna(cell_value) and 
                    str(cell_value).strip() not in ['', '-', 'nan', '0']):
                    room_parts.append(str(cell_value).strip())
            except IndexError:
                break

    def _add_section_and_qr_data(self, df, row_idx: int, current_col: int, room_parts: list, is_header: bool):
        """Add section data combined with Q/R columns (for 100-800, 400 PPR, 6000s templates)"""
        
        self._log(f"DEBUG: Processing row {row_idx}, current_col {current_col}, is_header: {is_header}")
        
        # Get the 3rd and 4th column values from the section
        third_col_value = None
        fourth_col_value = None
        
        try:
            # 3rd column (current_col + 2)
            cell_value = df.iloc[row_idx, current_col + 2]
            self._log(f"DEBUG: 3rd col ({current_col + 2}) raw value: '{cell_value}'")
            if (pd.notna(cell_value) and 
                str(cell_value).strip() not in ['', '-', 'nan', '0']):
                third_col_value = str(cell_value).strip()
                self._log(f"DEBUG: 3rd col processed value: '{third_col_value}'")
        except IndexError:
            self._log(f"DEBUG: 3rd col ({current_col + 2}) IndexError")
            pass
            
        try:
            # 4th column (current_col + 3)
            cell_value = df.iloc[row_idx, current_col + 3]
            self._log(f"DEBUG: 4th col ({current_col + 3}) raw value: '{cell_value}'")
            if (pd.notna(cell_value) and 
                str(cell_value).strip() not in ['', '-', 'nan', '0']):
                fourth_col_value = str(cell_value).strip()
                self._log(f"DEBUG: 4th col processed value: '{fourth_col_value}'")
        except IndexError:
            self._log(f"DEBUG: 4th col ({current_col + 3}) IndexError")
            pass
        
        # Get Q/R column data (only for non-header rows)
        room_name = None
        los_value = None
        
        if not is_header:  # Use the original is_header parameter (row_position == 0)
            try:
                room_name_cell = df.iloc[row_idx, 16]  # Column Q
                self._log(f"DEBUG: Q col (16) raw value: '{room_name_cell}'")
                if (pd.notna(room_name_cell) and 
                    str(room_name_cell).strip() not in ['', '-', 'nan', '0', 'Room Name']):
                    room_name = str(room_name_cell).strip()
                    self._log(f"DEBUG: Q col processed room_name: '{room_name}'")
            
                los_cell = df.iloc[row_idx, 18]  # Column R  
                self._log(f"DEBUG: R col (17) raw value: '{los_cell}'")
                if (pd.notna(los_cell) and 
                    str(los_cell).strip() not in ['', '-', 'nan', '0']):
                    los_value = str(los_cell).strip()
                    self._log(f"DEBUG: R col processed los_value: '{los_value}'")
            except IndexError as e:
                self._log(f"DEBUG: Q/R column IndexError: {e}")
                pass
        else:
            self._log(f"DEBUG: Skipping Q/R columns - this is a header row (row_position == 0)")
        
        # Assemble the room entry in correct order:
        # 1. Room number (already added before this method is called)
        # 2. Room name (from Q column) - only for non-headers
        if room_name:
            room_parts.append(room_name)
            self._log(f"DEBUG: Added room_name: '{room_name}'")
        else:
            self._log(f"DEBUG: No room_name to add")
        
        # 3. Third column value
        if third_col_value:
            room_parts.append(third_col_value)
            self._log(f"DEBUG: Added third_col_value: '{third_col_value}'")
        else:
            self._log(f"DEBUG: No third_col_value to add")
        
        # 4. Fourth column value  
        if fourth_col_value:
            room_parts.append(fourth_col_value)
            self._log(f"DEBUG: Added fourth_col_value: '{fourth_col_value}'")
        else:
            self._log(f"DEBUG: No fourth_col_value to add")
        
        # 5. LOS value (from R column) - only for non-headers
        if los_value:
            room_parts.append(los_value)
            self._log(f"DEBUG: Added los_value: '{los_value}'")
        else:
            self._log(f"DEBUG: No los_value to add")
        
        self._log(f"DEBUG: Final room_parts for this row: {room_parts}")

    def _extract_rooms_from_excel(self, file_path: str) -> List[str]:
        """Legacy method - Extract all rooms from Excel (kept for backward compatibility)"""
        # Use the extended template configuration for backward compatibility
        config = {
            'name': 'Legacy Full Template',
            'column_ranges': [18, 23, 28, 33, 37]  # All chunks
        }
        return self._extract_rooms_from_excel_by_config(file_path, config)
    
    def create_multiple_room_templates_from_excel(self, email: str, password: str, excel_file_path: str, selected_template_ids: List[str] = None, delete_existing: bool = False) -> dict:
        """Create multiple templates from Excel file based on configurations"""
        all_results = {
            'overall_status': 'started',
            'login_status': None,
            'navigation_status': None,
            'list_status': None,
            'templates_processed': [],
            'templates_successful': 0,
            'templates_failed': 0,
            'deletion_results': None,
            'start_time': datetime.now().isoformat(),
            'debug_info': [],
            'diagnostics': self.automator.test_browser_setup()
        }
        
        try:
            self._log("Starting multiple template automation flow")
            
            # Step 1: Login (only once)
            login_success = self.login(email, password)
            all_results['login_status'] = 'success' if login_success else 'failed'
            all_results['debug_info'].append({
                'step': 'login',
                'status': all_results['login_status'],
                'time': datetime.now().isoformat()
            })
            if not login_success:
                raise Exception("Login failed")
            
            # Step 2: Navigate to org settings (only once)
            nav_success = self.navigate_to_org_settings()
            all_results['navigation_status'] = 'success' if nav_success else 'failed'
            all_results['debug_info'].append({
                'step': 'org_settings_nav',
                'status': all_results['navigation_status'],
                'time': datetime.now().isoformat(),
                'url': self.automator.driver.current_url
            })
            if not nav_success:
                raise Exception("Organization settings navigation failed")
            
            # Step 3: Navigate to manage lists (only once)
            list_success = self.navigate_to_manage_lists()
            all_results['list_status'] = 'success' if list_success else 'failed'
            all_results['debug_info'].append({
                'step': 'manage_lists_nav',
                'status': all_results['list_status'],
                'time': datetime.now().isoformat(),
                'url': self.automator.driver.current_url
            })
            if not list_success:
                raise Exception("Manage lists navigation failed")

            # Verify we're on the correct page before template creation
            current_url = self.automator.driver.current_url
            if "lists" not in current_url.lower():
                raise Exception(f"Not on manage lists page. Current URL: {current_url}")
            
            # Step 4: Delete existing templates if requested
            if delete_existing:
                template_configs = self.get_template_configurations()
                template_names_to_delete = [config['name'] for config in template_configs 
                                          if selected_template_ids is None or config['id'] in selected_template_ids]
                
                if template_names_to_delete:
                    all_results['deletion_results'] = self.delete_existing_templates()
                    time.sleep(2)  # Wait after deletion
            
            # Step 5: Get template configurations and filter by selected IDs
            template_configs = self.get_template_configurations()
            
            # Filter templates if specific IDs are provided
            if selected_template_ids:
                template_configs = [config for config in template_configs 
                                   if config['id'] in selected_template_ids]
                self._log(f"Filtered to {len(template_configs)} templates based on selected IDs: {selected_template_ids}")
            
            template_configs.sort(key=lambda x: x['priority'])  # Sort by priority (1 first, 2 second, etc.)
            
            self._log(f"Will process {len(template_configs)} templates in priority order")
            
            # Step 6: Process each template
            for config_idx, config in enumerate(template_configs):
                template_result = {
                    'config': config,
                    'status': 'started',
                    'start_time': datetime.now().isoformat(),
                    'rooms_extracted': 0,
                    'rooms_added': 0,
                    'errors': []
                }
                
                try:
                    self._log(f"Processing template {config_idx + 1}/{len(template_configs)}: '{config['name']}'")
                    
                    # Extract rooms for this template configuration
                    room_names = self._extract_rooms_from_excel_by_config(excel_file_path, config)
                    template_result['rooms_extracted'] = len(room_names)
                    
                    if not room_names:
                        template_result['status'] = 'failed'
                        template_result['error'] = 'No valid rooms found for this template configuration'
                        all_results['templates_failed'] += 1
                    else:
                        # Create the template
                        creation_result = self.create_room_template(config['name'], room_names)
                        template_result.update(creation_result)
                        
                        if creation_result['status'] in ['completed', 'completed_with_warnings']:
                            all_results['templates_successful'] += 1
                            template_result['status'] = 'completed'
                        else:
                            all_results['templates_failed'] += 1
                            template_result['status'] = 'failed'
                    
                    template_result['end_time'] = datetime.now().isoformat()
                    all_results['templates_processed'].append(template_result)
                    
                    # Brief pause between templates
                    time.sleep(2)
                    
                except Exception as e:
                    error_msg = f"Failed to process template '{config['name']}': {str(e)}"
                    template_result.update({
                        'status': 'failed',
                        'error': error_msg,
                        'end_time': datetime.now().isoformat()
                    })
                    all_results['templates_processed'].append(template_result)
                    all_results['templates_failed'] += 1
                    self._log(error_msg, "ERROR")
            
            # Determine overall status
            if all_results['templates_successful'] == len(template_configs):
                all_results['overall_status'] = 'completed'
            elif all_results['templates_successful'] > 0:
                all_results['overall_status'] = 'partially_completed'
            else:
                all_results['overall_status'] = 'failed'
            
            self._log(f"Multiple template automation completed. Success: {all_results['templates_successful']}, Failed: {all_results['templates_failed']}")
            
        except Exception as e:
            error_msg = f"Multiple template automation flow failed: {str(e)}"
            self._log(error_msg, "ERROR")
            all_results['overall_error'] = error_msg
            all_results['overall_status'] = 'failed'
            all_results['debug_info'].append({
                'step': 'flow_error',
                'error': str(e),
                'time': datetime.now().isoformat(),
                'screenshot': self._save_debug_info("multi_template_failure")
            })
        finally:
            try:
                self.automator.close()
                self._log("Browser closed after multiple template automation flow")
            except Exception as close_error:
                self._log(f"Error closing browser: {str(close_error)}", "WARNING")
            all_results['end_time'] = datetime.now().isoformat()
            
        return all_results

    def run_automation(self, excel_file_path: str, selected_template_ids: List[str] = None, delete_existing: bool = True) -> dict:
        """
        PRIMARY METHOD: Run the complete automation with multiple templates from Excel
        
        This is the main method you should use for your automation.
        It will automatically generate all configured templates from the Excel file.
        
        Args:
            email: Login email
            password: Login password  
            excel_file_path: Path to the Excel file containing room data
            selected_template_ids: List of template IDs to create (None for all)
            delete_existing: Whether to delete existing templates first
            
        Returns:
            dict: Results containing status for all templates processed
        """
        self._log("=" * 60)
        self._log("STARTING MULTIPLE TEMPLATE AUTOMATION")
        self._log(f"Selected templates: {selected_template_ids}")
        self._log(f"Delete existing: {delete_existing}")
        self._log("=" * 60)
        
        return self.create_multiple_room_templates_from_excel(
            email="galaxielsaga@gmail.com",
            password="Admin@haqq123", 
            excel_file_path=excel_file_path,
            selected_template_ids=selected_template_ids,
            delete_existing=delete_existing
        )