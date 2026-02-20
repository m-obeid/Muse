import os
import json
from ytmusicapi import YTMusic
import ytmusicapi.navigation

# Monkeypatch ytmusicapi.navigation.nav to handle UI changes like musicImmersiveHeaderRenderer
_original_nav = ytmusicapi.navigation.nav

def robust_nav(root, items, none_if_absent=False):
    if root is None:
        return None
    try:
        current = root
        for i, k in enumerate(items):
            # Fallback for musicVisualHeaderRenderer -> musicImmersiveHeaderRenderer
            if k == "musicVisualHeaderRenderer" and isinstance(current, dict) and k not in current and "musicImmersiveHeaderRenderer" in current:
                k = "musicImmersiveHeaderRenderer"
            
            # Fallback for musicDetailHeaderRenderer -> musicResponsiveHeaderRenderer
            if k == "musicDetailHeaderRenderer" and isinstance(current, dict) and k not in current and "musicResponsiveHeaderRenderer" in current:
                k = "musicResponsiveHeaderRenderer"

            # Fallback for missing 'runs' in things like subtitle
            if k == "runs" and isinstance(current, dict) and k not in current:
                if none_if_absent:
                    return None
                # If we expect runs[0].text, provide a dummy to continue navigation
                if i < len(items) - 1 and items[i+1] == 0:
                    current = [{"text": ""}]
                    continue
                else:
                    current = []
                    continue

            current = current[k]
        return current
    except (KeyError, IndexError, TypeError):
        if none_if_absent:
            return None
        return _original_nav(root, items, none_if_absent)

ytmusicapi.navigation.nav = robust_nav

class MusicClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MusicClient, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.api = None
        self.auth_path = os.path.join(os.getcwd(), 'data', 'headers_auth.json')
        self._is_authed = False
        self.try_login()

    def try_login(self):
        # 1. Try saved headers_auth.json (Preferred)
        if os.path.exists(self.auth_path):
            try:
                print(f"Loading saved auth from {self.auth_path}")
                # Load headers to check/fix them before init
                with open(self.auth_path, 'r') as f:
                     headers = json.load(f)
                
                # Enforce English
                if 'Accept-Language' not in headers or 'en-' not in headers['Accept-Language']:
                    headers['Accept-Language'] = 'en-US,en;q=0.9'
                    with open(self.auth_path, 'w') as f:
                        json.dump(headers, f)

                self.api = YTMusic(self.auth_path)
                if self.validate_session():
                    print("Authenticated via saved session.")
                    self._is_authed = True
                    return True
                else:
                    print("Saved session invalid.")
            except Exception as e:
                print(f"Failed to load saved session: {e}")

        # 2. Check for browser.json in cwd (Manually provided)
        browser_path = os.path.join(os.getcwd(), 'browser.json')
        if os.path.exists(browser_path):
             print(f"Found browser.json at {browser_path}. Importing...")
             if self.login(browser_path):
                 return True

        # 3. Fallback
        print("Falling back to unauthenticated mode.")
        self.api = YTMusic()
        self._is_authed = False
        return False

    def is_authenticated(self):
        return self._is_authed and self.api is not None

    def login(self, auth_input):
        """
        Robust login method for browser.json or headers dict.
        """
        try:
            headers = None
            if isinstance(auth_input, str):
                if os.path.exists(auth_input):
                    with open(auth_input, 'r') as f:
                        headers = json.load(f)
                else:
                    # Try parsing as JSON string
                    try:
                        headers = json.loads(auth_input)
                    except json.JSONDecodeError:
                        # Legacy raw headers string support
                        from ytmusicapi.auth.browser import setup_browser
                        headers = json.loads(setup_browser(filepath=None, headers_raw=auth_input))
            elif isinstance(auth_input, dict):
                headers = auth_input
            
            if not headers:
                print("Invalid auth input.")
                return False

            # CRITICAL: Enforce Headers for Stability
            # 1. Accept-Language must be English to avoid parsing errors
            headers['Accept-Language'] = 'en-US,en;q=0.9'
            
            # 2. Ensure User-Agent is consistent/modern if missing
            if 'User-Agent' not in headers:
                headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'

            # 3. Content-Type often needed for JSON payloads
            if 'Content-Type' not in headers:
                headers['Content-Type'] = 'application/json; charset=UTF-8'
                
            # 4. Remove OAuth fields if they accidentally crept in and are partial/broken
            # (Though if oauth.json is specifically imported, maybe we handle it differently? 
            #  But we are pivoting to browser.json for now.)
            if 'oauth_credentials' in headers and 'access_token' not in headers:
                 # If it looks like half-baked oauth, maybe ignore or warn?
                 # ideally we just use the cookie.
                 pass

            # Save to data/headers_auth.json (Overwrite)
            os.makedirs(os.path.dirname(self.auth_path), exist_ok=True)
            if os.path.exists(self.auth_path):
                try: os.remove(self.auth_path)
                except: pass
            with open(self.auth_path, 'w') as f:
                json.dump(headers, f)
            
            # Initialize API
            self.api = YTMusic(self.auth_path)
            
            # Validate
            if self.validate_session():
                self._is_authed = True
                print("Login successful and saved.")
                return True
            else:
                print("Login failed: Session invalid after init.")
                self.api = YTMusic()
                self._is_authed = False
                return False

        except Exception as e:
            print(f"Login exception: {e}")
            self.api = YTMusic()
            self._is_authed = False
            return False

    def search(self, query, *args, **kwargs):
        if not self.api:
            return []
        res = self.api.search(query, *args, **kwargs)
        print(f"--- API RESPONSE: search({query}) ---")
        print(json.dumps(res, indent=2))
        return res

    def get_song(self, video_id):
        if not self.api:
             return None
        try:
            res = self.api.get_song(video_id)
            print(f"--- API RESPONSE: get_song({video_id}) ---")
            print(json.dumps(res, indent=2))
            return res
        except Exception as e:
            print(f"Error getting song details: {e}")
            return None

    def get_library_playlists(self):
        if not self.is_authenticated():
            return []
        return self.api.get_library_playlists()

    def get_playlist(self, playlist_id, limit=None):
        if not self.api:
            return None
        res = self.api.get_playlist(playlist_id, limit=limit)
        print(f"--- API RESPONSE: get_playlist({playlist_id}) ---")
        print(json.dumps(res, indent=2))
        return res

    def get_album(self, browse_id):
        if not self.api:
            return None
        res = self.api.get_album(browse_id)
        print(f"--- API RESPONSE: get_album({browse_id}) ---")
        print(json.dumps(res, indent=2))
        return res

    def get_artist(self, channel_id):
        if not self.api:
            return None
        try:
            res = self.api.get_artist(channel_id)
            print(f"--- API RESPONSE: get_artist({channel_id}) ---")
            print(json.dumps(res, indent=2))
            return res
        except Exception as e:
            print(f"Error getting artist details: {e}")
            return None
        
    def get_liked_songs(self, limit=100):
        if not self.is_authenticated():
            return []
        # Liked songs is actually a playlist 'LM'
        res = self.api.get_liked_songs(limit=limit)
        print(f"--- API RESPONSE: get_liked_songs ---")
        print(json.dumps(res, indent=2))
        return res

    def get_charts(self, country='US'):
        if not self.api:
            return {}
        return self.api.get_charts(country=country)

    def get_explore(self):
        if not self.api:
            return {}
        return self.api.get_explore()

    def get_album_browse_id(self, audio_playlist_id):
        if not self.api:
            return None
        res = self.api.get_album_browse_id(audio_playlist_id)
        print(f"--- API RESPONSE: get_album_browse_id({audio_playlist_id}) ---")
        print(json.dumps(res, indent=2))
        return res

    def edit_playlist(self, playlist_id, **kwargs):
        if not self.is_authenticated():
            return None
        try:
            res = self.api.edit_playlist(playlist_id, **kwargs)
            print(f"--- API RESPONSE: edit_playlist({playlist_id}) ---")
            print(json.dumps(res, indent=2))
            return res
        except Exception as e:
            print(f"Error editing playlist: {e}")
            return None

    def validate_session(self):
        """
        Check if the current session is valid by attempting an authenticated request.
        """
        if self.api is None:
            return False
            
        try:
            # Try to fetch liked songs (requires auth)
            # Just metadata is enough
            self.api.get_liked_songs(limit=1)
            return True
        except Exception as e:
            print(f"Session validation failed: {e}")
            return False


