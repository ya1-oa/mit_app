import os
import time
import tempfile
import shutil
from typing import Dict, List, Optional, Tuple, Union
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
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
    Enhanced Selenium Automation Framework optimized for DigitalOcean App Platform
    """

    def __init__(
        self,
        browser: str = "firefox",
        headless: bool = True,
        implicit_wait: int = 10,
        download_dir: Optional[str] = None,
        driver_path: Optional[str] = None
    ):
        self.browser = browser.lower()
        self.headless = headless
        self.implicit_wait = implicit_wait
        self.download_dir = download_dir
        self.driver_path = driver_path
        self.driver = None
        self.page_objects = {}
        self.original_window = None
        
        self._init_driver()
    
    def _find_driver_executable(self, driver_name: str) -> Optional[str]:
        """Find driver executable in various common locations"""
        possible_paths = []
        
        if driver_name == "geckodriver":
            possible_paths = [
                "/usr/local/bin/geckodriver",
                "/usr/bin/geckodriver",
                "/opt/geckodriver",
                shutil.which("geckodriver")
            ]
        elif driver_name == "chromedriver":
            possible_paths = [
                "/usr/local/bin/chromedriver",
                "/usr/bin/chromedriver",
                "/opt/chromedriver",
                shutil.which("chromedriver")
            ]
        
        # Add environment variable paths
        env_var = f"{driver_name.upper()}_PATH"
        if os.getenv(env_var):
            possible_paths.insert(0, os.getenv(env_var))
            
        # Return first existing path
        for path in possible_paths:
            if path and os.path.exists(path) and os.access(path, os.X_OK):
                return path
                
        return None
        
    def _init_driver(self):
        """Initialize WebDriver with App Platform optimizations"""
        browser = self.browser.lower()
        
        if browser == "firefox":
            self._init_firefox()
        elif browser == "chrome":
            self._init_chrome()
        else:
            raise ValueError(f"Unsupported browser: {browser}")
            
        if self.driver:
            self.driver.implicitly_wait(self.implicit_wait)
            self.original_window = self.driver.current_window_handle

    def _init_firefox(self):
        """Initialize Firefox with detailed debugging"""
        try:
            # Test if Firefox is actually working
            result = subprocess.run(['firefox', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            print(f"Firefox version: {result.stdout}")
            
            # Test if geckodriver works
            if self.driver_path:
                result = subprocess.run([self.driver_path, '--version'],
                                      capture_output=True, text=True, timeout=10)
                print(f"Geckodriver version: {result.stdout}")
            
            options = FirefoxOptions()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            
            service = FirefoxService(
                executable_path=self.driver_path,
                log_path='/tmp/geckodriver.log'  # Save logs to file
            )
            
            self.driver = webdriver.Firefox(options=options, service=service)
            
        except Exception as e:
            print(f"Detailed Firefox error: {str(e)}")
            # Check if log file exists and show contents
            if os.path.exists('/tmp/geckodriver.log'):
                with open('/tmp/geckodriver.log', 'r') as f:
                    print("Geckodriver logs:", f.read())
            raise

    def _init_chrome(self):
        """Initialize Chrome with container optimizations"""
        options = ChromeOptions()
        
        # Try to find Chrome binary
        chrome_binaries = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable", 
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            os.getenv('CHROME_BIN')
        ]
        
        chrome_binary = None
        for binary in chrome_binaries:
            if binary and os.path.exists(binary):
                chrome_binary = binary
                break
                
        if chrome_binary:
            options.binary_location = chrome_binary
        
        # Essential container options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--disable-features=VizServiceDisplayCompositor")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-logging")
        options.add_argument("--disable-dev-tools")
        
        if self.headless:
            options.add_argument("--headless=new")
        
        # Memory and performance
        options.add_argument("--memory-pressure-off")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-translate")
        
        if self.download_dir:
            os.makedirs(self.download_dir, exist_ok=True)
            prefs = {
                "download.default_directory": self.download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            options.add_experimental_option("prefs", prefs)
        
        # Find driver executable
        if not self.driver_path:
            self.driver_path = self._find_driver_executable("chromedriver")
            
        if not self.driver_path:
            raise WebAutomationError("Chromedriver not found. Install with: apt-get install chromium-chromedriver")
        
        try:
            service = ChromeService(executable_path=self.driver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            raise WebAutomationError(f"Failed to initialize Chrome: {str(e)}")

    # Test method to verify setup
    def test_browser_setup(self) -> Dict[str, any]:
        """Test browser setup and return diagnostics"""
        diagnostics = {
            'browser': self.browser,
            'driver_path': self.driver_path,
            'driver_exists': os.path.exists(self.driver_path) if self.driver_path else False,
            'driver_executable': os.access(self.driver_path, os.X_OK) if self.driver_path else False,
            'driver_initialized': self.driver is not None,
            'test_navigation': False,
            'page_title': None,
            'user_agent': None
        }
        
        if self.driver:
            try:
                self.driver.get('https://httpbin.org/user-agent')
                diagnostics['test_navigation'] = True
                diagnostics['page_title'] = self.driver.title
                diagnostics['user_agent'] = self.driver.execute_script("return navigator.userAgent;")
            except Exception as e:
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
                print(f"Warning: Error during driver quit: {str(e)}")
            finally:
                self.driver = None
                
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


