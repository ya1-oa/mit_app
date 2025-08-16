import os
import time
from typing import Dict, List, Optional, Tuple, Union
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
    StaleElementReferenceException
)

class WebAutomationError(Exception):
    """Base exception for automation errors"""
    pass


class WebAutomator:
    """
    Modular Selenium Automation Framework
    
    Features:
    - Supports multiple browsers (Chrome, Firefox, Edge)
    - Element location by various strategies (ID, XPath, CSS, etc.)
    - Automatic waiting and retry mechanisms
    - Common actions (click, input, hover, etc.)
    - Download handling
    - Screenshot capability
    - Cookie management
    - Tab/window management
    - Right-click context menu support
    - Modular and extensible design
    
    Usage:
    1. Initialize with browser type
    2. Define elements in page_objects or pass directly to methods
    3. Perform actions on elements
    """
    
    def __init__(
        self,
        browser: str = "chrome",
        headless: bool = False,
        implicit_wait: int = 10,
        download_dir: Optional[str] = None,
        driver_path: Optional[str] = None
    ):
        """
        Initialize the WebAutomator
        
        :param browser: Browser to use ('chrome', 'firefox', 'edge')
        :param headless: Run in headless mode
        :param implicit_wait: Default implicit wait time in seconds
        :param download_dir: Directory for downloads (None for default)
        :param driver_path: Path to webdriver executable (None for system PATH)
        """
        self.browser = browser.lower()
        self.headless = headless
        self.implicit_wait = implicit_wait
        self.download_dir = download_dir
        self.driver_path = driver_path
        self.driver = None
        self.page_objects = {}  # Store page element definitions
        self.original_window = None
        
        self._init_driver()
        
    def _init_driver(self):
        """Initialize the WebDriver based on configuration"""
        if self.browser == "chrome":
            options = webdriver.ChromeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            
            # Add these lines to handle the user data directory
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument(f"--user-data-dir=/tmp/chrome-user-data-{time.time()}")
            
            if self.download_dir:
                prefs = {
                    "download.default_directory": self.download_dir,
                    "download.prompt_for_download": False,
                    "download.directory_upgrade": True,
                    "safebrowsing.enabled": True
                }
                options.add_experimental_option("prefs", prefs)
            
            # Rest of your initialization code...
                options.add_experimental_option("prefs", prefs)
                
                if self.driver_path:
                    self.driver = webdriver.Chrome(
                        executable_path=self.driver_path,
                        options=options
                    )
                else:
                    self.driver = webdriver.Chrome(options=options)
                    
            elif self.browser == "firefox":
                options = webdriver.FirefoxOptions()
                if self.headless:
                    options.add_argument("--headless")
                if self.download_dir:
                    profile = webdriver.FirefoxProfile()
                    profile.set_preference("browser.download.folderList", 2)
                    profile.set_preference("browser.download.dir", self.download_dir)
                    profile.set_preference(
                        "browser.helperApps.neverAsk.saveToDisk",
                        "application/octet-stream,application/pdf,application/vnd.ms-excel"
                    )
                    self.driver = webdriver.Firefox(
                        firefox_profile=profile,
                        options=options,
                        executable_path=self.driver_path if self.driver_path else None
                    )
                else:
                    self.driver = webdriver.Firefox(
                        options=options,
                        executable_path=self.driver_path if self.driver_path else None
                    )
                    
            elif self.browser == "edge":
                options = webdriver.EdgeOptions()
                if self.headless:
                    options.add_argument("--headless")
                if self.download_dir:
                    prefs = {
                        "download.default_directory": self.download_dir,
                        "download.prompt_for_download": False
                    }
                    options.add_experimental_option("prefs", prefs)
                
                if self.driver_path:
                    self.driver = webdriver.Edge(
                        executable_path=self.driver_path,
                        options=options
                    )
                else:
                    self.driver = webdriver.Edge(options=options)
            
            else:
                raise ValueError(f"Unsupported browser: {self.browser}")
                
            self.driver.implicitly_wait(self.implicit_wait)
            self.original_window = self.driver.current_window_handle
        
    def define_page(
        self,
        page_name: str,
        elements: Dict[str, Dict[str, str]],
        base_url: Optional[str] = None
    ):
        """
        Define a page with its elements for easy reference
        
        :param page_name: Name to identify this page
        :param elements: Dictionary of element definitions
                        Format: {'element_name': {'by': By strategy, 'value': locator}}
        :param base_url: Optional base URL for this page
        """
        self.page_objects[page_name] = {
            'elements': elements,
            'base_url': base_url
        }
        
    def navigate_to(self, url: str):
        """Navigate to a URL"""
        self.driver.get(url)
        
    def navigate_to_page(self, page_name: str, path: str = ""):
        """
        Navigate to a predefined page
        
        :param page_name: Name of the predefined page
        :param path: Additional path to append to base URL
        """
        if page_name not in self.page_objects:
            raise ValueError(f"Page '{page_name}' not defined")
            
        base_url = self.page_objects[page_name]['base_url']
        if not base_url:
            raise ValueError(f"No base URL defined for page '{page_name}'")
            
        full_url = base_url + path
        self.driver.get(full_url)
        
    def find_element(
        self,
        locator: Union[Tuple[str, str], str],
        page_name: Optional[str] = None,
        timeout: Optional[int] = None,
        retries: int = 3
    ):
        """
        Find a web element with retry and wait logic
        
        :param locator: Either a tuple of (by, value) or element name if page_name is provided
        :param page_name: Name of predefined page containing element
        :param timeout: Maximum time to wait in seconds (None for implicit wait)
        :param retries: Number of retry attempts
        :return: WebElement if found
        """
        by, value = self._resolve_locator(locator, page_name)
        
        for attempt in range(retries):
            try:
                if timeout is not None:
                    wait = WebDriverWait(self.driver, timeout)
                    return wait.until(EC.presence_of_element_located((by, value)))
                return self.driver.find_element(by, value)
            except (NoSuchElementException, TimeoutException) as e:
                if attempt == retries - 1:
                    raise
                time.sleep(1)
            except StaleElementReferenceException:
                if attempt == retries - 1:
                    raise
                time.sleep(1)
                
    def find_elements(
        self,
        locator: Union[Tuple[str, str], str],
        page_name: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        """
        Find multiple web elements
        
        :param locator: Either a tuple of (by, value) or element name if page_name is provided
        :param page_name: Name of predefined page containing element
        :param timeout: Maximum time to wait in seconds (None for implicit wait)
        :return: List of WebElements if found
        """
        by, value = self._resolve_locator(locator, page_name)
        
        if timeout is not None:
            wait = WebDriverWait(self.driver, timeout)
            return wait.until(EC.presence_of_all_elements_located((by, value)))
        return self.driver.find_elements(by, value)
        
    def _resolve_locator(
        self,
        locator: Union[Tuple[str, str], str],
        page_name: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Resolve a locator to (by, value) tuple
        
        :param locator: Either a tuple or element name
        :param page_name: Page name if using predefined elements
        :return: Tuple of (by, value)
        """
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
        
    def click(
        self,
        locator: Union[Tuple[str, str], str],
        page_name: Optional[str] = None,
        timeout: Optional[int] = None,
        retries: int = 3
    ):
        """
        Click on an element
        
        :param locator: Element locator
        :param page_name: Page name if using predefined elements
        :param timeout: Maximum time to wait in seconds
        :param retries: Number of retry attempts
        """
        for attempt in range(retries):
            try:
                element = self.find_element(locator, page_name, timeout)
                element.click()
                return
            except (ElementNotInteractableException, StaleElementReferenceException) as e:
                if attempt == retries - 1:
                    raise
                time.sleep(1)
                
    def input_text(
        self,
        locator: Union[Tuple[str, str], str],
        text: str,
        page_name: Optional[str] = None,
        timeout: Optional[int] = None,
        clear_first: bool = True,
        press_enter: bool = False
    ):
        """
        Input text into a field
        
        :param locator: Element locator
        :param text: Text to input
        :param page_name: Page name if using predefined elements
        :param timeout: Maximum time to wait in seconds
        :param clear_first: Whether to clear the field first
        :param press_enter: Whether to press Enter after input
        """
        element = self.find_element(locator, page_name, timeout)
        
        if clear_first:
            element.clear()
            
        element.send_keys(text)
        
        if press_enter:
            element.send_keys(Keys.RETURN)
            
    def hover(
        self,
        locator: Union[Tuple[str, str], str],
        page_name: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        """
        Hover over an element
        
        :param locator: Element locator
        :param page_name: Page name if using predefined elements
        :param timeout: Maximum time to wait in seconds
        """
        element = self.find_element(locator, page_name, timeout)
        ActionChains(self.driver).move_to_element(element).perform()
        
    def right_click(
        self,
        locator: Union[Tuple[str, str], str],
        page_name: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        """
        Right-click on an element
        
        :param locator: Element locator
        :param page_name: Page name if using predefined elements
        :param timeout: Maximum time to wait in seconds
        """
        element = self.find_element(locator, page_name, timeout)
        ActionChains(self.driver).context_click(element).perform()
        
    def select_dropdown_option(
        self,
        locator: Union[Tuple[str, str], str],
        option: Union[str, int],
        page_name: Optional[str] = None,
        timeout: Optional[int] = None,
        by_value: bool = False
    ):
        """
        Select an option from a dropdown
        
        :param locator: Dropdown element locator
        :param option: Option text or index to select
        :param page_name: Page name if using predefined elements
        :param timeout: Maximum time to wait in seconds
        :param by_value: Whether to select by value attribute instead of visible text
        """
        from selenium.webdriver.support.ui import Select
        
        element = self.find_element(locator, page_name, timeout)
        select = Select(element)
        
        if isinstance(option, int):
            select.select_by_index(option)
        elif by_value:
            select.select_by_value(option)
        else:
            select.select_by_visible_text(option)
            
    def wait_for_element(
        self,
        locator: Union[Tuple[str, str], str],
        page_name: Optional[str] = None,
        timeout: int = 10,
        visible: bool = True,
        clickable: bool = False
    ):
        """
        Wait for an element to meet certain conditions
        
        :param locator: Element locator
        :param page_name: Page name if using predefined elements
        :param timeout: Maximum time to wait in seconds
        :param visible: Wait for element to be visible
        :param clickable: Wait for element to be clickable
        :return: WebElement if found
        """
        by, value = self._resolve_locator(locator, page_name)
        wait = WebDriverWait(self.driver, timeout)
        
        if clickable:
            return wait.until(EC.element_to_be_clickable((by, value)))
        elif visible:
            return wait.until(EC.visibility_of_element_located((by, value)))
        else:
            return wait.until(EC.presence_of_element_located((by, value)))
            
    def reload_page(self):
        """Reload the current page"""
        self.driver.refresh()
        
    def switch_to_frame(
        self,
        locator: Union[Tuple[str, str], str],
        page_name: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        """
        Switch to an iframe
        
        :param locator: Frame element locator
        :param page_name: Page name if using predefined elements
        :param timeout: Maximum time to wait in seconds
        """
        frame = self.find_element(locator, page_name, timeout)
        self.driver.switch_to.frame(frame)
        
    def switch_to_default_content(self):
        """Switch back to default content from iframe"""
        self.driver.switch_to.default_content()
        
    def switch_to_window(self, window_handle: Optional[str] = None, index: Optional[int] = None):
        """
        Switch to another window/tab
        
        :param window_handle: Window handle to switch to
        :param index: Index of window to switch to (0-based)
        """
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
        """Close the current window/tab"""
        self.driver.close()
        
    def take_screenshot(self, filename: str):
        """
        Take a screenshot of the current window
        
        :param filename: Path to save the screenshot
        """
        self.driver.save_screenshot(filename)
        
    def get_cookies(self) -> Dict[str, str]:
        """Get all cookies as a dictionary"""
        return {cookie['name']: cookie['value'] for cookie in self.driver.get_cookies()}
        
    def add_cookie(self, name: str, value: str):
        """
        Add a cookie to the current session
        
        :param name: Cookie name
        :param value: Cookie value
        """
        self.driver.add_cookie({'name': name, 'value': value})
        
    def delete_cookie(self, name: str):
        """
        Delete a cookie by name
        
        :param name: Cookie name to delete
        """
        self.driver.delete_cookie(name)
        
    def clear_cookies(self):
        """Delete all cookies"""
        self.driver.delete_all_cookies()
        
    def execute_js(self, script: str, *args):
        """
        Execute JavaScript in the current context
        
        :param script: JavaScript code to execute
        :param args: Arguments to pass to the script
        :return: Result of the script execution
        """
        return self.driver.execute_script(script, *args)
        
    def scroll_to_element(
        self,
        locator: Union[Tuple[str, str], str],
        page_name: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        """
        Scroll to make an element visible in the viewport
        
        :param locator: Element locator
        :param page_name: Page name if using predefined elements
        :param timeout: Maximum time to wait in seconds
        """
        element = self.find_element(locator, page_name, timeout)
        self.execute_js("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        
    def wait_for_download(self, filename: str, timeout: int = 30, check_interval: int = 1):
        """
        Wait for a file to be downloaded
        
        :param filename: Name of the file to wait for
        :param timeout: Maximum time to wait in seconds
        :param check_interval: Time between checks in seconds
        :return: Path to downloaded file
        :raises: TimeoutException if file not found within timeout
        """
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
        """Close the browser and end the session"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            
    def __enter__(self):
        """Context manager entry"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure browser is closed"""
        self.close()


