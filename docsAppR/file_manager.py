# docsAppR/onedrive_manager.py

import requests
import logging
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

logger = logging.getLogger('onedrive_sync')


class OneDriveManager:
    """
    Manages all OneDrive API operations with Microsoft Graph
    """

    GRAPH_API_ENDPOINT = 'https://graph.microsoft.com/v1.0'
    TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'

    def __init__(self):
        self.client_id = settings.ONEDRIVE_CLIENT_ID
        self.client_secret = getattr(settings, 'ONEDRIVE_CLIENT_SECRET', None)
        self.redirect_uri = settings.ONEDRIVE_REDIRECT_URI
        self.access_token = None
        self.refresh_token = None
        self.drive_id = None
        if settings.TOKEN_ENCRYPTION_KEY:
            self.cipher_suite = Fernet(settings.TOKEN_ENCRYPTION_KEY.encode())
        else:
            logger.warning("TOKEN_ENCRYPTION_KEY not set! Tokens will not be encrypted.")
            self.cipher_suite = None

        # Initialize with existing refresh token from environment if available
        self._initialize_refresh_token()

    def _initialize_refresh_token(self):
        """Initialize refresh token from environment variable if not already in cache"""
        # Check if we already have a refresh token in cache
        cached_refresh_token = self._get_refresh_token_decrypted()

        if cached_refresh_token:
            logger.debug("Refresh token already in cache")
            return

        # Try to load from environment variable
        env_refresh_token = getattr(settings, 'ONEDRIVE_REFRESH_TOKEN', None)

        if env_refresh_token:
            logger.info("Loading refresh token from environment variable")
            # Store the refresh token encrypted in cache
            if self.cipher_suite:
                encrypted_refresh = self.cipher_suite.encrypt(env_refresh_token.encode()).decode()
                cache.set('onedrive_refresh_token', encrypted_refresh, timeout=86400 * 30)  # 30 days
            else:
                cache.set('onedrive_refresh_token', env_refresh_token, timeout=86400 * 30)
            logger.info("Refresh token stored in cache successfully")
        else:
            logger.warning("No refresh token found in environment or cache")

    # ==================== AUTHENTICATION ====================

    def get_auth_url(self):
        """Generate OAuth authorization URL"""
        scope = 'offline_access Files.ReadWrite.All'
        auth_url = (
            f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?"
            f"client_id={self.client_id}&"
            f"response_type=code&"
            f"redirect_uri={self.redirect_uri}&"
            f"scope={scope}"
        )
        return auth_url

    def exchange_code_for_tokens(self, auth_code):
        """Exchange authorization code for access and refresh tokens"""
        data = {
            'client_id': self.client_id,
            'scope': 'offline_access Files.ReadWrite.All',
            'code': auth_code,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code'
        }

        if self.client_secret:
            data['client_secret'] = self.client_secret

        try:
            response = requests.post(self.TOKEN_URL, data=data)
            response.raise_for_status()

            tokens = response.json()
            self.access_token = tokens['access_token']
            self.refresh_token = tokens.get('refresh_token')

            # Store encrypted tokens in cache
            self._store_tokens_encrypted(
                self.access_token,
                self.refresh_token,
                tokens.get('expires_in', 3600)
            )

            logger.info("Successfully exchanged code for tokens")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Token exchange failed: {str(e)}")
            raise Exception(f"Authentication failed: {str(e)}")

    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        refresh_token = self._get_refresh_token_decrypted()

        if not refresh_token:
            raise Exception("No refresh token available")

        data = {
            'client_id': self.client_id,
            'scope': 'offline_access Files.ReadWrite.All',
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }

        if self.client_secret:
            data['client_secret'] = self.client_secret

        try:
            response = requests.post(self.TOKEN_URL, data=data)
            response.raise_for_status()

            tokens = response.json()
            self.access_token = tokens['access_token']

            if 'refresh_token' in tokens:
                self.refresh_token = tokens['refresh_token']

            self._store_tokens_encrypted(
                self.access_token,
                self.refresh_token,
                tokens.get('expires_in', 3600)
            )

            logger.info("Successfully refreshed access token")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Token refresh failed: {str(e)}")
            raise Exception(f"Token refresh failed: {str(e)}")

    def authenticate(self):
        """Get valid access token from cache or refresh"""
        # Try to get cached access token
        self.access_token = self._get_access_token_decrypted()

        if self.access_token:
            logger.debug("Using cached access token")
            return True

        # Try to refresh token
        try:
            self.refresh_access_token()
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            raise Exception("No valid access token. Please authenticate via /auth/onedrive/")

    def _store_tokens_encrypted(self, access_token, refresh_token, expires_in):
        """Store tokens encrypted in cache"""
        if not self.cipher_suite:
            logger.warning("Storing tokens without encryption!")
            cache.set('onedrive_access_token', access_token, timeout=expires_in - 300)
            if refresh_token:
                cache.set('onedrive_refresh_token', refresh_token, timeout=86400 * 30)
            return

        # Encrypt tokens
        encrypted_access = self.cipher_suite.encrypt(access_token.encode()).decode()

        if refresh_token:
            encrypted_refresh = self.cipher_suite.encrypt(refresh_token.encode()).decode()
            cache.set('onedrive_refresh_token', encrypted_refresh, timeout=86400 * 30)  # 30 days

        cache.set('onedrive_access_token', encrypted_access, timeout=expires_in - 300)  # 5 min buffer

    def _get_access_token_decrypted(self):
        """Retrieve and decrypt access token from cache"""
        encrypted = cache.get('onedrive_access_token')
        if encrypted:
            if not self.cipher_suite:
                return encrypted
            return self.cipher_suite.decrypt(encrypted.encode()).decode()
        return None

    def _get_refresh_token_decrypted(self):
        """Retrieve and decrypt refresh token from cache"""
        encrypted = cache.get('onedrive_refresh_token')
        if encrypted:
            if not self.cipher_suite:
                return encrypted
            return self.cipher_suite.decrypt(encrypted.encode()).decode()
        return None

    # ==================== HTTP REQUEST WRAPPER ====================

    def _make_request(self, method, url, auto_retry=True, **kwargs):
        """Make authenticated request to Microsoft Graph API"""
        if not self.access_token:
            self.authenticate()

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
        kwargs['headers'] = headers

        # Make full URL if relative
        if not url.startswith('http'):
            url = f"{self.GRAPH_API_ENDPOINT}{url}"

        try:
            response = requests.request(method, url, **kwargs)

            # Handle token expiration
            if response.status_code == 401 and auto_retry:
                logger.info("Token expired, refreshing...")
                self.refresh_access_token()
                headers['Authorization'] = f'Bearer {self.access_token}'
                kwargs['headers'] = headers
                response = requests.request(method, url, **kwargs)

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {method} {url} - {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise

    # ==================== DRIVE OPERATIONS ====================

    def get_drive_id(self, use_shared=None):
        """Get drive ID (personal or shared)"""
        if use_shared is None:
            use_shared = settings.ONEDRIVE_USE_SHARED_DRIVE

        if use_shared:
            # Get shared drive
            response = self._make_request('GET', '/me/drive/sharedWithMe')
            data = response.json()

            if data.get('value'):
                self.drive_id = data['value'][0]['remoteItem']['parentReference']['driveId']
                cache.set('onedrive_drive_id', self.drive_id, timeout=86400)
                return self.drive_id

            raise Exception("No shared drives found")
        else:
            # Get personal drive
            response = self._make_request('GET', '/me/drive')
            self.drive_id = response.json()['id']
            cache.set('onedrive_drive_id', self.drive_id, timeout=86400)
            return self.drive_id

    def get_documents_folder(self):
        """Get Documents folder ID"""
        if not self.drive_id:
            self.get_drive_id()

        # Check cache
        cached_id = cache.get('onedrive_documents_id')
        if cached_id:
            return cached_id

        response = self._make_request(
            'GET',
            f'/drives/{self.drive_id}/root/children',
            params={'$filter': "name eq 'Documents'"}
        )

        data = response.json()
        if data.get('value'):
            documents_id = data['value'][0]['id']
            cache.set('onedrive_documents_id', documents_id, timeout=86400)
            return documents_id

        raise Exception("Documents folder not found")

    # ==================== FOLDER OPERATIONS ====================

    def get_or_create_folder(self, folder_name, parent_id):
        """Get folder ID if exists, otherwise create it"""
        if not self.drive_id:
            self.get_drive_id()

        # Try to find existing folder
        try:
            response = self._make_request(
                'GET',
                f'/drives/{self.drive_id}/items/{parent_id}/children',
                params={'$filter': f"name eq '{folder_name}'"}
            )

            data = response.json()
            if data.get('value'):
                logger.info(f"Folder '{folder_name}' already exists")
                return data['value'][0]['id']
        except:
            pass

        # Create new folder
        return self.create_folder(folder_name, parent_id)

    def create_folder(self, folder_name, parent_id):
        """Create a new folder"""
        if not self.drive_id:
            self.get_drive_id()

        data = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename"
        }

        response = self._make_request(
            'POST',
            f'/drives/{self.drive_id}/items/{parent_id}/children',
            json=data
        )

        folder_id = response.json()['id']
        logger.info(f"Created folder: {folder_name}")
        return folder_id

    def list_folder_contents(self, folder_id):
        """List all items in a folder"""
        if not self.drive_id:
            self.get_drive_id()

        response = self._make_request(
            'GET',
            f'/drives/{self.drive_id}/items/{folder_id}/children'
        )

        return response.json().get('value', [])

    # ==================== FILE OPERATIONS ====================

    def upload_file(self, filename, file_content, parent_id):
        """Upload a file to OneDrive"""
        if not self.drive_id:
            self.get_drive_id()

        # Handle BytesIO objects
        if hasattr(file_content, 'read'):
            file_content = file_content.read()

        file_size = len(file_content)

        # Use simple upload for files < 4MB
        if file_size < 4 * 1024 * 1024:
            return self._simple_upload(filename, file_content, parent_id)
        else:
            return self._upload_large_file(filename, file_content, parent_id)

    def _simple_upload(self, filename, file_content, parent_id):
        """Simple upload for small files"""
        response = self._make_request(
            'PUT',
            f'/drives/{self.drive_id}/items/{parent_id}:/{filename}:/content',
            data=file_content,
            headers={'Content-Type': 'application/octet-stream'}
        )

        file_data = response.json()
        logger.info(f"Uploaded file: {filename}")
        return file_data['id']

    def _upload_large_file(self, filename, file_content, parent_id):
        """Upload large file using upload session"""
        # Create upload session
        response = self._make_request(
            'POST',
            f'/drives/{self.drive_id}/items/{parent_id}:/{filename}:/createUploadSession',
            json={}
        )

        upload_url = response.json()['uploadUrl']

        # Upload in chunks
        chunk_size = 10 * 1024 * 1024  # 10MB chunks
        file_size = len(file_content)

        for start in range(0, file_size, chunk_size):
            end = min(start + chunk_size, file_size)
            chunk = file_content[start:end]

            headers = {
                'Content-Length': str(len(chunk)),
                'Content-Range': f'bytes {start}-{end-1}/{file_size}'
            }

            chunk_response = requests.put(upload_url, data=chunk, headers=headers)
            chunk_response.raise_for_status()

            logger.debug(f"Uploaded chunk {start}-{end} of {file_size}")

        file_data = chunk_response.json()
        logger.info(f"Uploaded large file: {filename}")
        return file_data['id']

    def upload_text_file(self, filename, content, parent_id):
        """Upload a text file"""
        file_bytes = content.encode('utf-8')
        return self.upload_file(filename, file_bytes, parent_id)

    def download_file(self, file_id):
        """Download a file from OneDrive"""
        if not self.drive_id:
            self.get_drive_id()

        # Get download URL
        response = self._make_request(
            'GET',
            f'/drives/{self.drive_id}/items/{file_id}'
        )

        download_url = response.json()['@microsoft.graph.downloadUrl']

        # Download file content
        file_response = requests.get(download_url)
        file_response.raise_for_status()

        logger.info(f"Downloaded file ID: {file_id}")
        return file_response.content

    def get_file_metadata(self, file_id):
        """Get file metadata"""
        if not self.drive_id:
            self.get_drive_id()

        response = self._make_request(
            'GET',
            f'/drives/{self.drive_id}/items/{file_id}'
        )

        return response.json()

    def delete_item(self, item_id):
        """Delete a file or folder"""
        if not self.drive_id:
            self.get_drive_id()

        self._make_request(
            'DELETE',
            f'/drives/{self.drive_id}/items/{item_id}'
        )

        logger.info(f"Deleted item ID: {item_id}")
        return True

    # ==================== SUBSCRIPTION (WEBHOOK) OPERATIONS ====================

    def create_subscription(self, folder_id, notification_url, expiration_minutes=60):
        """Create a webhook subscription for a folder"""
        if not self.drive_id:
            self.get_drive_id()

        # Calculate expiration (max 3 days for business, 1 hour for personal)
        expiration = timezone.now() + timedelta(minutes=expiration_minutes)

        subscription_data = {
            "changeType": "updated",
            "notificationUrl": notification_url,
            "resource": f"/drives/{self.drive_id}/items/{folder_id}",
            "expirationDateTime": expiration.isoformat(),
            "clientState": settings.ONEDRIVE_WEBHOOK_SECRET
        }

        response = self._make_request(
            'POST',
            '/subscriptions',
            json=subscription_data
        )

        subscription = response.json()
        logger.info(f"Created subscription: {subscription['id']}")

        return {
            'subscription_id': subscription['id'],
            'expires': datetime.fromisoformat(subscription['expirationDateTime'].replace('Z', '+00:00'))
        }

    def renew_subscription(self, subscription_id, expiration_minutes=60):
        """Renew an existing subscription"""
        expiration = timezone.now() + timedelta(minutes=expiration_minutes)

        data = {
            "expirationDateTime": expiration.isoformat()
        }

        response = self._make_request(
            'PATCH',
            f'/subscriptions/{subscription_id}',
            json=data
        )

        subscription = response.json()
        logger.info(f"Renewed subscription: {subscription_id}")

        return datetime.fromisoformat(subscription['expirationDateTime'].replace('Z', '+00:00'))

    def delete_subscription(self, subscription_id):
        """Delete a subscription"""
        self._make_request(
            'DELETE',
            f'/subscriptions/{subscription_id}'
        )

        logger.info(f"Deleted subscription: {subscription_id}")
        return True

    # ==================== DELTA SYNC OPERATIONS ====================

    def get_delta_changes(self, folder_id, delta_token=None):
        """Get changes since last delta sync"""
        if not self.drive_id:
            self.get_drive_id()

        if delta_token:
            # Use existing delta token
            url = delta_token
        else:
            # Initial delta query
            url = f'/drives/{self.drive_id}/items/{folder_id}/delta'

        response = self._make_request('GET', url)
        data = response.json()

        changes = data.get('value', [])
        next_delta_token = data.get('@odata.deltaLink', '')

        logger.info(f"Got {len(changes)} changes for folder {folder_id}")

        return {
            'changes': changes,
            'delta_token': next_delta_token
        }

    # ==================== HELPER METHODS ====================

    def get_sharing_link(self, item_id, link_type='view'):
        """Create a sharing link for a file or folder"""
        if not self.drive_id:
            self.get_drive_id()

        data = {
            "type": link_type,
            "scope": "anonymous"
        }

        response = self._make_request(
            'POST',
            f'/drives/{self.drive_id}/items/{item_id}/createLink',
            json=data
        )

        return response.json()['link']['webUrl']
