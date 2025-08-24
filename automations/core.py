import os
import time
import tempfile
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Tuple, Union
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    WebDriverException
)

class WebAutomationError(Exception):
    """Base exception for automation errors"""
    pass

class WebAutomator:
    """
    Chromium-only Selenium Automation Framework optimized for DigitalOcean App Platform
    """

    def __init__(
        self,
        headless: bool = True,
        implicit_wait: int = 10,
        download_dir: Optional[str] = None,
        driver_path: Optional[str] = None,
        chromium_path: Optional[str] = None
    ):
        self.headless = headless
        self.implicit_wait = implicit_wait
        self.download_dir = download_dir
        self.driver_path = driver_path
        self.chromium_path = chromium_path
        self.driver = None
        self.page_objects = {}
        self.original_window = None
        
        self._init_driver()
    
    def _debug_print(self, message: str, level: str = "INFO"):
        """Print debug messages with timestamps"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}", file=sys.stderr)
    
    def _run_command(self, cmd: List[str], description: str) -> Tuple[bool, str]:
        """Run a command and return success status and output"""
        try:
            self._debug_print(f"Running: {description}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        except subprocess.TimeoutExpired:
            return False, "Command timed out after 30 seconds"
        except Exception as e:
            return False, f"Exception: {str(e)}"
    
    def _find_chromium_binary(self) -> Optional[str]:
        """Find Chromium binary in various common locations"""
        possible_paths = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/snap/bin/chromium",
            os.getenv('CHROMIUM_BIN'),
            os.getenv('CHROME_BIN')
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path) and os.access(path, os.X_OK):
                self._debug_print(f"Found Chromium at: {path}")
                return path
        
        # Additional search using which command
        try:
            which_path = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
            if which_path:
                self._debug_print(f"Found via which: {which_path}")
                return which_path
        except:
            pass
            
        self._debug_print("Chromium not found in common locations", "WARNING")
        return None
    
    def _find_chromedriver(self) -> Optional[str]:
        """Find ChromeDriver executable"""
        possible_paths = [
            "/usr/local/bin/chromedriver",
            "/usr/bin/chromedriver",
            "/opt/chromedriver",
            "/snap/bin/chromedriver",
            os.getenv('CHROMEDRIVER_PATH'),
            os.getenv('CHROME_DRIVER_PATH'),
            shutil.which("chromedriver")
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path):
                if os.access(path, os.X_OK):
                    self._debug_print(f"Found ChromeDriver at: {path}")
                    return path
                else:
                    self._debug_print(f"ChromeDriver found but not executable: {path}", "WARNING")
        
        self._debug_print("ChromeDriver not found in common locations", "WARNING")
        return None
    
    def _check_system_dependencies(self):
        """Simple dependency check - just verify Chrome works"""
        self._debug_print("Performing Chrome dependency check...")
        
        # Set default path first
        chrome_path = self.chromium_path or "/usr/bin/google-chrome"
        
        try:
            # Test if Chrome can start with a simple command
            result = subprocess.run(
                [chrome_path, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom", "about:blank"],
                capture_output=True, 
                text=True, 
                timeout=30
            )
            
            if result.returncode == 0:
                self._debug_print("Chrome dependency check passed", "INFO")
                return True
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                self._debug_print(f"Chrome test failed: {error_msg}", "ERROR")
                return False
                
        except Exception as e:
            self._debug_print(f"Dependency check failed: {str(e)}", "ERROR")
            return False
    
    def _init_driver(self):
        """Initialize Chrome WebDriver with forced version matching"""
        try:
            self._debug_print("Initializing Chrome driver with forced version matching...")
            
            # Set default path
            self.chromium_path = self.chromium_path or "/usr/bin/google-chrome"
            
            # Verify Chrome exists
            if not os.path.exists(self.chromium_path):
                raise WebAutomationError(f"Chrome not found at: {self.chromium_path}")
            if not os.access(self.chromium_path, os.X_OK):
                raise WebAutomationError(f"Chrome not executable at: {self.chromium_path}")
            
            # Get Chrome version - CRITICAL for version matching
            success, version_output = self._run_command([self.chromium_path, "--version"], "Get Chrome version")
            if success:
                self._debug_print(f"Chrome version: {version_output}")
                # Extract exact version number (e.g., "139.0.7258.138")
                chrome_version = version_output.replace('Google Chrome ', '').strip()
                # Extract major version (139)
                chrome_major_version = chrome_version.split('.')[0]
            else:
                raise WebAutomationError("Failed to get Chrome version")
            
            # FORCE webdriver-manager to get the correct ChromeDriver version
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from webdriver_manager.core.utils import ChromeType
                
                self._debug_print(f"FORCING ChromeDriver download for Chrome {chrome_version}")
                
                # Method 1: Try exact version first
                try:
                    self.driver_path = ChromeDriverManager(
                        chrome_type=ChromeType.GOOGLE,
                        version=chrome_version  # EXACT version match
                    ).install()
                    self._debug_print(f"Successfully installed ChromeDriver {chrome_version}")
                except:
                    # Method 2: Try major version if exact fails
                    self._debug_print(f"Exact version failed, trying major version {chrome_major_version}")
                    self.driver_path = ChromeDriverManager(
                        chrome_type=ChromeType.GOOGLE,
                        version=chrome_major_version  # Major version match
                    ).install()
                    self._debug_print(f"Successfully installed ChromeDriver for major version {chrome_major_version}")
                
                # Verify ChromeDriver version
                success, driver_version = self._run_command([self.driver_path, "--version"], "Verify ChromeDriver version")
                if success:
                    self._debug_print(f"Final ChromeDriver version: {driver_version}")
                
            except ImportError:
                raise WebAutomationError("webdriver-manager is not installed. Add 'webdriver-manager' to requirements.txt")
            
            # MANUAL FALLBACK: If webdriver-manager still fails, download directly
            if not self.driver_path or not os.path.exists(self.driver_path):
                self._debug_print("webdriver-manager failed, downloading ChromeDriver manually...")
                self._download_chromedriver_manually(chrome_version)
            
            # Initialize Chrome options
            options = ChromeOptions()
            options.binary_location = self.chromium_path
            
            # Essential options
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1280,720")
            options.add_argument("--disable-extensions")
            
            # Configure service
            service = ChromeService(
                executable_path=self.driver_path,
                service_args=["--verbose"],
                log_path="/tmp/chromedriver.log"
            )
            
            self._debug_print("Starting Chrome driver...")
            self.driver = webdriver.Chrome(service=service, options=options)
            
            self.driver.implicitly_wait(self.implicit_wait)
            self.original_window = self.driver.current_window_handle
            
            self._debug_print("Chrome driver initialized successfully!")
            
        except Exception as e:
            error_details = f"Initialization error: {str(e)}"
            
            # Enhanced diagnostics
            error_details += f"\n\nVersion diagnostics:"
            error_details += f"\n- Chrome path: {self.chromium_path}"
            error_details += f"\n- ChromeDriver path: {self.driver_path}"
            
            # Check what versions are actually present
            try:
                chrome_ver = subprocess.run([self.chromium_path, "--version"], capture_output=True, text=True)
                error_details += f"\n- Chrome version: {chrome_ver.stdout.strip() if chrome_ver.returncode == 0 else 'Unknown'}"
            except:
                pass
                
            try:
                driver_ver = subprocess.run([self.driver_path, "--version"], capture_output=True, text=True) if self.driver_path else None
                error_details += f"\n- ChromeDriver version: {driver_ver.stdout.strip() if driver_ver and driver_ver.returncode == 0 else 'Unknown'}"
            except:
                pass
            
            self._debug_print(error_details, "ERROR")
            raise WebAutomationError(error_details)
    
    def _download_chromedriver_manually(self, chrome_version):
        """Manual fallback to download ChromeDriver"""
        try:
            # Download specific ChromeDriver version
            download_url = f"https://chromedriver.storage.googleapis.com/{chrome_version}/chromedriver_linux64.zip"
            self._debug_print(f"Downloading ChromeDriver from: {download_url}")
            
            # Download and extract
            subprocess.run(["wget", "-O", "/tmp/chromedriver.zip", download_url], check=True)
            subprocess.run(["unzip", "-o", "/tmp/chromedriver.zip", "-d", "/usr/local/bin/"], check=True)
            subprocess.run(["chmod", "+x", "/usr/local/bin/chromedriver"], check=True)
            subprocess.run(["rm", "/tmp/chromedriver.zip"], check=True)
            
            self.driver_path = "/usr/local/bin/chromedriver"
            self._debug_print("Manually installed ChromeDriver")
            
        except Exception as e:
            raise WebAutomationError(f"Manual ChromeDriver download failed: {str(e)}")
    
    def _emergency_chromedriver_fix(self):
        """Emergency fix for version mismatches"""
        try:
            self._debug_print("Attempting emergency ChromeDriver fix...")
            
            # Get current Chrome version
            result = subprocess.run(["/usr/bin/google-chrome", "--version"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                chrome_version = result.stdout.strip().replace('Google Chrome ', '')
                self._debug_print(f"Detected Chrome version: {chrome_version}")
                
                # Download matching ChromeDriver
                import requests, zipfile, io
                url = f"https://chromedriver.storage.googleapis.com/{chrome_version}/chromedriver_linux64.zip"
                
                self._debug_print(f"Downloading matching ChromeDriver from: {url}")
                response = requests.get(url)
                response.raise_for_status()
                
                # Extract and install
                with zipfile.ZipFile(io.BytesIO(response.content)) as zipf:
                    zipf.extractall("/usr/local/bin/")
                
                # Make executable
                subprocess.run(["chmod", "+x", "/usr/local/bin/chromedriver"], check=True)
                
                self.driver_path = "/usr/local/bin/chromedriver"
                self._debug_print("Emergency fix completed successfully")
                return True
                
        except Exception as e:
            self._debug_print(f"Emergency fix failed: {str(e)}", "ERROR")
            return False
            
    def test_browser_setup(self) -> Dict[str, any]:
        """Test browser setup and return detailed diagnostics"""
        diagnostics = {
            'browser': 'chromium',
            'chromium_path': self.chromium_path,
            'driver_path': self.driver_path,
            'chromium_exists': os.path.exists(self.chromium_path) if self.chromium_path else False,
            'driver_exists': os.path.exists(self.driver_path) if self.driver_path else False,
            'chromium_executable': os.access(self.chromium_path, os.X_OK) if self.chromium_path else False,
            'driver_executable': os.access(self.driver_path, os.X_OK) if self.driver_path else False,
            'driver_initialized': self.driver is not None,
            'test_navigation': False,
            'page_title': None,
            'user_agent': None,
            'error': None
        }
        
        if self.driver:
            try:
                # Use a lightweight test page
                self.driver.get('about:version')
                diagnostics['test_navigation'] = True
                diagnostics['page_title'] = self.driver.title
                diagnostics['user_agent'] = self.driver.execute_script("return navigator.userAgent;")
                
                # Additional diagnostics
                diagnostics['window_handles'] = len(self.driver.window_handles)
                diagnostics['current_url'] = self.driver.current_url
                
            except Exception as e:
                diagnostics['error'] = str(e)
                diagnostics['navigation_error'] = str(e)
        
        return diagnostics

    # ========== ALL ORIGINAL METHODS PRESERVED ==========
    
    def define_page(self, page_name: str, elements: Dict[str, Dict[str, str]], base_url: Optional[str] = None):
        self.page_objects[page_name] = {
            'elements': elements,
            'base_url': base_url
        }
        
    def navigate_to(self, url: str):
        self.driver.get(url)
        
    def navigate_to_page(self, page_name: str, path: str = ""):
        if page_name not in self.page_objects:
            raise ValueError(f"Page '{page_name}' not defined")
        base_url = self.page_objects[page_name]['base_url']
        if not base_url:
            raise ValueError(f"No base URL defined for page '{page_name}'")
        self.driver.get(base_url + path)
        
    def find_element(self, locator: Union[Tuple[str, str], str], page_name: Optional[str] = None, 
                    timeout: Optional[int] = None, retries: int = 3):
        by, value = self._resolve_locator(locator, page_name)
        for attempt in range(retries):
            try:
                if timeout is not None:
                    wait = WebDriverWait(self.driver, timeout)
                    return wait.until(EC.presence_of_element_located((by, value)))
                return self.driver.find_element(by, value)
            except (NoSuchElementException, TimeoutException, StaleElementReferenceException) as e:
                if attempt == retries - 1:
                    raise
                time.sleep(1)
                
    def find_elements(self, locator: Union[Tuple[str, str], str], page_name: Optional[str] = None, 
                     timeout: Optional[int] = None):
        by, value = self._resolve_locator(locator, page_name)
        if timeout is not None:
            wait = WebDriverWait(self.driver, timeout)
            return wait.until(EC.presence_of_all_elements_located((by, value)))
        return self.driver.find_elements(by, value)
        
    def _resolve_locator(self, locator: Union[Tuple[str, str], str], page_name: Optional[str] = None) -> Tuple[str, str]:
        if isinstance(locator, tuple):
            return locator
        if not page_name:
            raise ValueError("page_name required when locator is string")
        if page_name not in self.page_objects:
            raise ValueError(f"Page '{page_name}' not defined")
        elements = self.page_objects[page_name]['elements']
        if locator not in elements:
            raise ValueError(f"Element '{locator}' not defined in page '{page_name}'")
        element_def = elements[locator]
        return element_def['by'], element_def['value']
        
    def click(self, locator: Union[Tuple[str, str], str], page_name: Optional[str] = None, 
              timeout: Optional[int] = None, retries: int = 3):
        for attempt in range(retries):
            try:
                element = self.find_element(locator, page_name, timeout)
                element.click()
                return
            except (ElementNotInteractableException, StaleElementReferenceException) as e:
                if attempt == retries - 1:
                    raise
                time.sleep(1)
                
    def input_text(self, locator: Union[Tuple[str, str], str], text: str, page_name: Optional[str] = None,
                  timeout: Optional[int] = None, clear_first: bool = True, press_enter: bool = False):
        element = self.find_element(locator, page_name, timeout)
        if clear_first:
            element.clear()
        element.send_keys(text)
        if press_enter:
            element.send_keys(Keys.RETURN)
            
    def hover(self, locator: Union[Tuple[str, str], str], page_name: Optional[str] = None, timeout: Optional[int] = None):
        element = self.find_element(locator, page_name, timeout)
        ActionChains(self.driver).move_to_element(element).perform()
        
    def right_click(self, locator: Union[Tuple[str, str], str], page_name: Optional[str] = None, timeout: Optional[int] = None):
        element = self.find_element(locator, page_name, timeout)
        ActionChains(self.driver).context_click(element).perform()
        
    def select_dropdown_option(self, locator: Union[Tuple[str, str], str], option: Union[str, int],
                              page_name: Optional[str] = None, timeout: Optional[int] = None, by_value: bool = False):
        from selenium.webdriver.support.ui import Select
        element = self.find_element(locator, page_name, timeout)
        select = Select(element)
        if isinstance(option, int):
            select.select_by_index(option)
        elif by_value:
            select.select_by_value(option)
        else:
            select.select_by_visible_text(option)
            
    def wait_for_element(self, locator: Union[Tuple[str, str], str], page_name: Optional[str] = None,
                        timeout: int = 10, visible: bool = True, clickable: bool = False):
        by, value = self._resolve_locator(locator, page_name)
        wait = WebDriverWait(self.driver, timeout)
        if clickable:
            return wait.until(EC.element_to_be_clickable((by, value)))
        elif visible:
            return wait.until(EC.visibility_of_element_located((by, value)))
        else:
            return wait.until(EC.presence_of_element_located((by, value)))
            
    def reload_page(self):
        self.driver.refresh()
        
    def switch_to_frame(self, locator: Union[Tuple[str, str], str], page_name: Optional[str] = None, timeout: Optional[int] = None):
        frame = self.find_element(locator, page_name, timeout)
        self.driver.switch_to.frame(frame)
        
    def switch_to_default_content(self):
        self.driver.switch_to.default_content()
        
    def switch_to_window(self, window_handle: Optional[str] = None, index: Optional[int] = None):
        if window_handle:
            self.driver.switch_to.window(window_handle)
        elif index is not None:
            handles = self.driver.window_handles
            if index < len(handles):
                self.driver.switch_to.window(handles[index])
            else:
                raise ValueError(f"Window index {index} out of range")
        else:
            raise ValueError("Must provide either window_handle or index")
            
    def close_current_window(self):
        self.driver.close()
        
    def take_screenshot(self, filename: str):
        self.driver.save_screenshot(filename)
        
    def get_cookies(self) -> Dict[str, str]:
        return {cookie['name']: cookie['value'] for cookie in self.driver.get_cookies()}
        
    def add_cookie(self, name: str, value: str):
        self.driver.add_cookie({'name': name, 'value': value})
        
    def delete_cookie(self, name: str):
        self.driver.delete_cookie(name)
        
    def clear_cookies(self):
        self.driver.delete_all_cookies()
        
    def execute_js(self, script: str, *args):
        return self.driver.execute_script(script, *args)
        
    def scroll_to_element(self, locator: Union[Tuple[str, str], str], page_name: Optional[str] = None, timeout: Optional[int] = None):
        element = self.find_element(locator, page_name, timeout)
        self.execute_js("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        
    def wait_for_download(self, filename: str, timeout: int = 30, check_interval: int = 1):
        if not self.download_dir:
            raise ValueError("Download directory not configured")
        filepath = os.path.join(self.download_dir, filename)
        end_time = time.time() + timeout
        while time.time() < end_time:
            if os.path.exists(filepath):
                return filepath
            time.sleep(check_interval)
        raise TimeoutException(f"File '{filename}' not found after {timeout} seconds")
        
    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                self._debug_print(f"Warning: Error during driver quit: {str(e)}", "WARNING")
            finally:
                self.driver = None
                
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()






