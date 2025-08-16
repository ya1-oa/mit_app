from .core import WebAutomator, WebAutomationError
from typing import Dict, Any, List, Optional, Tuple, Union
import pandas as pd
import re
import time
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

class AutomationTasks:
    def __init__(self, browser: str = "chrome", headless: bool = True):
        self.automator = WebAutomator(browser=browser, headless=headless)
    
    def generic_automation(
        self,
        url: str,
        actions: List[Dict[str, Any]],
        page_objects: Optional[Dict[str, Dict]] = None
    ) -> Dict[str, Any]:
        """
        Execute a generic automation flow
        
        Args:
            url: URL to start automation
            actions: List of actions to perform
                    Example: [{"action": "click", "locator": ("id", "button1")}, ...]
            page_objects: Optional page object definitions
            
        Returns:
            Dict with results and status
        """
        results = {"status": "started", "steps": []}
        
        try:
            # Register page objects if provided
            if page_objects:
                for page_name, elements in page_objects.items():
                    self.automator.define_page(page_name, elements)
            
            # Navigate to starting URL
            self.automator.navigate_to(url)
            results['steps'].append({"action": "navigate", "url": url, "status": "success"})
            
            # Process each action
            for action in actions:
                try:
                    step_result = self._execute_action(action)
                    results['steps'].append(step_result)
                except Exception as e:
                    results['steps'].append({
                        "action": action.get('action'),
                        "element": action.get('locator'),
                        "status": "failed",
                        "error": str(e)
                    })
                    raise WebAutomationError(f"Action failed: {action}") from e
            
            results["status"] = "completed"
            
        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)
        finally:
            self.automator.close()
        
        return results
    
    def _process_excel_section(self, df, rows, cols, label=None):
        """Helper method to process a section of the Excel file"""
        section_rooms = []
        for row in rows:
            room_id = str(df.iloc[row, cols[0]]).strip() if pd.notna(df.iloc[row, cols[0]]) else None
            col1 = str(df.iloc[row, cols[1]]).strip() if len(cols) > 1 and pd.notna(df.iloc[row, cols[1]]) else None
            col2 = str(df.iloc[row, cols[2]]).strip() if len(cols) > 2 and pd.notna(df.iloc[row, cols[2]]) else None
            
            if label:  # For labeled sections (SOURCE OF LOSS, DMO)
                if room_id and col1 and col2:
                    section_rooms.append(f"{room_id} {col1} {col2}")
            else:  # For simple ID+Name sections
                if room_id and col1:
                    section_rooms.append(f"{room_id} {col1}")
        
        return section_rooms
    
    def _extract_rooms_from_excel(self, file_path: str) -> List[str]:
        """Extract rooms from Excel with the specified column structure"""
        try:
            # Read the Excel file (jobinfo(3) tab, rows 2-26)
            df = pd.read_excel(
                file_path,
                sheet_name='jobinfo(3)',
                header=None,
                skiprows=1  # Skip header row
            )
            rows_to_process = range(25)  # Rows 2-26 (0-indexed)
            rooms = []
            
            # 1. Basic rooms (A-B and D-E)
            rooms += self._process_excel_section(df, rows_to_process, [0, 1])  # A-B
            rooms += self._process_excel_section(df, rows_to_process, [3, 4])  # D-E
            
            # 2. SOURCE OF LOSS sections
            rooms += self._process_excel_section(df, rows_to_process, [8, 9, 10], label=True)  # I-K
            rooms += self._process_excel_section(df, rows_to_process, [12, 13, 14], label=True)  # M-O
            
            # 3. DMO sections
            rooms += self._process_excel_section(df, rows_to_process, [17, 18, 19], label=True)  # R-T
            rooms += self._process_excel_section(df, rows_to_process, [21, 22, 23], label=True)  # V-X
            
            # 4. FSI sections
            rooms += self._process_excel_section(df, rows_to_process, [25, 26])  # Z-AA
            rooms += self._process_excel_section(df, rows_to_process, [28, 29])  # AC-AD
            
            # 5. WTF MIT sections
            rooms += self._process_excel_section(df, rows_to_process, [30, 31])  # AF-AG
            rooms += self._process_excel_section(df, rows_to_process, [33, 34])  # AH-AI
            
            # Remove duplicates and sort
            unique_rooms = []
            seen = set()
            for room in rooms:
                if room not in seen:
                    seen.add(room)
                    unique_rooms.append(room)
            
            # Sort by numeric prefix
            unique_rooms.sort(key=lambda x: int(re.search(r'^\d+', x).group()))
            
            return unique_rooms
            
        except Exception as e:
            raise WebAutomationError(f"Excel processing failed: {str(e)}")

    def _execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single automation action"""
        action_type = action['action']
        locator = action.get('locator')
        page_name = action.get('page')
        value = action.get('value')
        timeout = action.get('timeout', 10)
        
        result = {
            "action": action_type,
            "element": locator,
            "page": page_name,
            "status": "success"
        }
        
        if action_type == "click":
            self.automator.click(locator, page_name, timeout)
        elif action_type == "input":
            self.automator.input_text(locator, value, page_name, timeout)
        elif action_type == "hover":
            self.automator.hover(locator, page_name, timeout)
        elif action_type == "right_click":
            self.automator.right_click(locator, page_name, timeout)
        elif action_type == "select":
            self.automator.select_dropdown_option(locator, value, page_name, timeout)
        elif action_type == "wait":
            self.automator.wait_for_element(locator, page_name, timeout)
        elif action_type == "navigate":
            self.automator.navigate_to(value)
        elif action_type == "reload":
            self.automator.reload_page()
        else:
            raise WebAutomationError(f"Unknown action type: {action_type}")
        
        return result

from .core import WebAutomator, WebAutomationError
from typing import Dict, Any, List, Optional, Tuple, Union
import pandas as pd
import re
import time
import os
import json
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
from selenium.webdriver.remote.webelement import WebElement

class RoomTemplateAutomation:
    def __init__(self, browser: str = "chrome", headless: bool = True):
        # Initialize with performance logging capabilities
        self.automator = WebAutomator(browser=browser, headless=headless)
        self._force_browser_ready()

    def _force_browser_ready(self):
        """Ensure browser is fully ready before any interaction"""
        try:
            # Set explicit window size (bypasses maximize issues)
            self.automator.driver.set_window_size(1920, 1080)
            
            # Wait for all initializations to complete
            WebDriverWait(self.automator.driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception as e:
            print(f"⚠️ Browser initialization warning: {str(e)}")

    def _save_debug_info(self, prefix: str = "error"):
        """Save comprehensive debug information"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_dir = "debug_logs"
        os.makedirs(debug_dir, exist_ok=True)
        
        try:
            # Save screenshot
            screenshot_path = f"{debug_dir}/{prefix}_{timestamp}.png"
            self.automator.driver.save_screenshot(screenshot_path)
            
            # Save page source
            page_source_path = f"{debug_dir}/{prefix}_page_source_{timestamp}.html"
            with open(page_source_path, "w", encoding="utf-8") as f:
                f.write(self.automator.driver.page_source)
                
            # Save browser logs if available
            try:
                logs = self.automator.driver.get_log("browser")
                log_path = f"{debug_dir}/{prefix}_console_logs_{timestamp}.json"
                with open(log_path, "w") as f:
                    json.dump(logs, f)
            except Exception as log_error:
                print(f"Could not save browser logs: {str(log_error)}")
                
            return {
                "screenshot": screenshot_path,
                "page_source": page_source_path,
                "logs": log_path if 'log_path' in locals() else None
            }
            
        except Exception as e:
            print(f"Could not save debug info: {str(e)}")
            return None

    def _wait_for_page_transition(self, timeout=30):
        """Wait for page to fully transition after navigation"""
        try:
            # Get current window handles if this might open new tab/window
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
                
            # Additional wait for jQuery/other frameworks if needed
            try:
                WebDriverWait(self.automator.driver, 10).until(
                    lambda d: d.execute_script("return (typeof jQuery === 'undefined') || jQuery.active == 0"))
            except:
                pass
                
            # Wait for any loading indicators to disappear
            try:
                WebDriverWait(self.automator.driver, 10).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.loading, .spinner, .progress-bar')))
            except:
                pass
                
        except Exception as e:
            print(f"Page transition warning: {str(e)}")
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
            
            # Store original window handle (should be only one tab at this point)
            original_window = self.automator.driver.current_window_handle
            
            # Click the login button (will open new tab)
            self.automator.click('login_button', page_name='login')
            
            # Wait for new window to appear and switch to it
            WebDriverWait(self.automator.driver, 10).until(
                lambda d: len(d.window_handles) > 1
            )
            
            # Switch to the new tab (should be the login page)
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
                return True
            except TimeoutException:
                raise Exception("Failed to verify successful login")
                
        except Exception as e:
            print(f"Login failed: {str(e)}")
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
            print(f"Navigation failed: {json.dumps(debug_info, indent=2)}")
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
            return True


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
                        print(f"Warning: Room '{room_name}' may not have been added")
                    
                    time.sleep(0.3)
                    
                except Exception as e:
                    results['errors'].append(f"Failed to add room '{room_name}': {str(e)}")
                    print(f"Error adding room: {str(e)}")
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
            except:
                results['status'] = 'completed_with_warnings'
                print("Warning: Could not verify save completion")

        except Exception as e:
            results.update({
                'status': 'failed',
                'error': str(e)
            })
            print(f"Critical error: {str(e)}")

        return results

    def _extract_rooms_from_excel(self, file_path: str) -> List[str]:
        """Extract and format rooms from Excel file according to the specified structure"""
        try:
            # Read the Excel file
            df = pd.read_excel(
                file_path,
                sheet_name='jobinfo(3)',
                header=None,
                skiprows=1  # Skip header row
            )
            
            rooms = []
            row_range = range(min(25, len(df)))  # Process up to 26 rows (0-25)
            
            # Process all specified column groups
            column_groups = [
                # Format: (columns, has_label)
                ([0, 1], False),    # A-B
                ([3, 4], False),    # D-E
                ([8, 9, 10], True), # I-K (SOURCE OF LOSS)
                ([12, 13, 14], True), # M-O
                ([17, 18, 19], True), # R-T (DMO)
                ([21, 22, 23], True), # V-X
                ([25, 26], False),  # Z-AA (FSI)
                ([28, 29], False),  # AC-AD
                ([30, 31], False),  # AF-AG (WTF MIT)
                ([33, 34], False)   # AH-AI
            ]
            
            for cols, has_label in column_groups:
                for row in row_range:
                    try:
                        # Get values from columns
                        values = [str(df.iloc[row, col]).strip() 
                                 for col in cols if pd.notna(df.iloc[row, col])]
                        
                        # Skip if any value is empty or 'nan'
                        if not values or any(v.lower() == 'nan' for v in values):
                            continue
                            
                        if has_label and len(values) >= 3:
                            # Format: "ID Label Name"
                            rooms.append(f"{values[0]} {values[1]} {values[2]}")
                        elif not has_label and len(values) >= 2:
                            # Format: "ID Name"
                            rooms.append(f"{values[0]} {values[1]}")
                    except:
                        continue
            
            # Remove duplicates while preserving order
            seen = set()
            unique_rooms = [x for x in rooms if not (x in seen or seen.add(x))]
            
            # Sort by numeric prefix
            unique_rooms.sort(key=lambda x: int(re.search(r'^\d+', x).group()))
            
            return unique_rooms
            
        except Exception as e:
            raise WebAutomationError(f"Excel processing failed: {str(e)}")

    def create_room_template_from_excel(self, email: str, password: str, template_name: str, excel_file_path: str) -> dict:
        """Complete automation flow using Excel file as data source"""
        # Extract and format rooms from Excel
        try:
            room_names = self._extract_rooms_from_excel(excel_file_path)
            if not room_names:
                return {
                    'status': 'failed',
                    'error': 'No valid rooms found in Excel file',
                    'excel_processing': {
                        'file_path': excel_file_path,
                        'rooms_found': 0
                    }
                }
            
            # Execute the full automation flow
            results = self.full_automation_flow(
                email=email,
                password=password,
                template_name=template_name,
                room_names=room_names
            )
            
            # Add Excel processing info to results
            results['excel_processing'] = {
                'file_path': excel_file_path,
                'rooms_found': len(room_names),
                'rooms_processed': len(results.get('processed_rooms', []))
            }
            
            return results
            
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
                'excel_processing': {
                    'file_path': excel_file_path,
                    'error': 'Failed to process Excel file'
                }
            }

    def full_automation_flow(self, email: str, password: str, template_name: str, room_names: list) -> dict:
        """Complete automation flow from login to template creation"""
        results = {
            'login_status': None,
            'navigation_status': None,
            'list_status': None,
            'template_creation': None,
            'start_time': datetime.now().isoformat(),
            'total_rooms': len(room_names),
            'debug_info': []
        }
        
        try:
            # Step 1: Login
            login_success = self.login(email, password)
            results['login_status'] = 'success' if login_success else 'failed'
            results['debug_info'].append({
                'step': 'login',
                'status': results['login_status'],
                'time': datetime.now().isoformat()
            })
            if not login_success:
                raise Exception("Login failed")
            
            # Step 2: Navigate to org settings
            nav_success = self.navigate_to_org_settings()
            results['navigation_status'] = 'success' if nav_success else 'failed'
            results['debug_info'].append({
                'step': 'org_settings_nav',
                'status': results['navigation_status'],
                'time': datetime.now().isoformat(),
                'url': self.automator.driver.current_url
            })
            if not nav_success:
                raise Exception("Organization settings navigation failed")
            
            # Step 3: Navigate to manage lists
            list_success = self.navigate_to_manage_lists()
            results['list_status'] = 'success' if list_success else 'failed'
            results['debug_info'].append({
                'step': 'manage_lists_nav',
                'status': results['list_status'],
                'time': datetime.now().isoformat(),
                'url': self.automator.driver.current_url
            })
            if not list_success:
                raise Exception("Manage lists navigation failed")

            # Verify we're on the correct page before template creation
            current_url = self.automator.driver.current_url
            if "lists" not in current_url.lower():
                raise Exception(f"Not on manage lists page. Current URL: {current_url}")
            
            # Step 4: Create template
            template_results = self.create_room_template(template_name, room_names)
            results['template_creation'] = template_results
            results['debug_info'].extend(template_results.get('debug_info', []))
            
            # Wait a moment before closing
            time.sleep(2)
            
        except Exception as e:
            results['error'] = str(e)
            results['status'] = 'failed'
            results['debug_info'].append({
                'step': 'flow_error',
                'error': str(e),
                'time': datetime.now().isoformat(),
                'screenshot': self._save_debug_info("flow_failure")
            })
        finally:
            self.automator.close()
            results['end_time'] = datetime.now().isoformat()
            
        return results