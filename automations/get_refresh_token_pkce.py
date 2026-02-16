import base64
import hashlib
import os
import secrets
import sys
import urllib.parse
import webbrowser
import requests

# ---- set these to your app ----
CLIENT_ID    = "2f69825e-fea1-4701-b933-d7112424e873"
TENANT       = "consumers"  # "consumers" for personal; "common" also works
REDIRECT_URI = "https://login.microsoftonline.com/common/oauth2/nativeclient"
SCOPES       = ["offline_access", "Files.ReadWrite.All"]

AUTH_URL  = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def make_code_verifier() -> str:
    return b64url(secrets.token_bytes(32))

def make_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return b64url(digest)

def main():
    code_verifier  = make_code_verifier()
    code_challenge = make_code_challenge(code_verifier)
    scope = " ".join(SCOPES)

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    print("\nOpening browser to sign in...")
    print(url, "\n")
    webbrowser.open(url)

    print("After sign-in, Azure will display an authorization code.")
    auth_code = input("Paste the authorization code here: ").strip()

    data = {
        "client_id": CLIENT_ID,
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "scope": scope,
        "code_verifier": code_verifier,
    }
    r = requests.post(TOKEN_URL, data=data, timeout=60)
    if r.status_code >= 400:
        print("Token exchange failed:", r.status_code, r.text)
        sys.exit(1)

    js = r.json()
    print("\nSUCCESS.\n")
    print("Access token (truncated):", js.get("access_token","")[:32], "...")
    print("Refresh token:", js.get("refresh_token"))
    print("\nSave the refresh token securely (e.g., in your .env as GRAPH_REFRESH_TOKEN).")

if __name__ == "__main__":
    main()
