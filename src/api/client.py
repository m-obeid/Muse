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
            if (
                k == "musicVisualHeaderRenderer"
                and isinstance(current, dict)
                and k not in current
                and "musicImmersiveHeaderRenderer" in current
            ):
                k = "musicImmersiveHeaderRenderer"
            # Fallback for musicDetailHeaderRenderer -> musicResponsiveHeaderRenderer
            if (
                k == "musicDetailHeaderRenderer"
                and isinstance(current, dict)
                and k not in current
                and "musicResponsiveHeaderRenderer" in current
            ):
                k = "musicResponsiveHeaderRenderer"
            if k == "runs" and isinstance(current, dict) and k not in current:
                if none_if_absent:
                    return None
                if i < len(items) - 1 and items[i + 1] == 0:
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
        self.auth_path = os.path.join(os.getcwd(), "data", "headers_auth.json")
        self._is_authed = False
        self._playlist_cache = {}  # Cache fully-fetched playlists
        self.try_login()

    def try_login(self):
        # 1. Try saved headers_auth.json (Preferred)
        if os.path.exists(self.auth_path):
            try:
                print(f"Loading saved auth from {self.auth_path}")
                # Load headers to check/fix them before init
                with open(self.auth_path, "r") as f:
                    headers = json.load(f)

                # Normalize keys for ytmusicapi and remove Bearer tokens
                headers = self._normalize_headers(headers)

                self.api = YTMusic(auth=headers)
                if self.validate_session():
                    print("Authenticated via saved session.")
                    self._is_authed = True
                    return True
                else:
                    print("Saved session invalid.")
            except Exception as e:
                print(f"Failed to load saved session: {e}")

        # 2. Check for browser.json in cwd (Manually provided)
        browser_path = os.path.join(os.getcwd(), "browser.json")
        if os.path.exists(browser_path):
            print(f"Found browser.json at {browser_path}. Importing...")
            if self.login(browser_path):
                return True

        # 3. Fallback
        print("Falling back to unauthenticated mode.")
        self.api = YTMusic()
        self._is_authed = False
        return False

    def _normalize_headers(self, headers):
        """
        Ensures headers match what ytmusicapi expects for a browser session.
        Preserves Authorization (if not Bearer) and ensures required keys exist.
        """
        print("Standardizing headers for ytmusicapi...")
        normalized = {}
        for k, v in headers.items():
            lk = k.lower().replace("-", "_")

            # Whitelist standard browser headers with Title-Case
            if lk == "cookie":
                normalized["Cookie"] = v
            elif lk == "user_agent":
                normalized["User-Agent"] = v
            elif lk == "accept_language":
                normalized["Accept-Language"] = v
            elif lk == "content_type":
                normalized["Content-Type"] = v
            elif lk == "authorization":
                # Only keep if it's NOT an OAuth Bearer token
                if v.lower().startswith("bearer"):
                    print("  [Security] Dropping OAuth Bearer token.")
                else:
                    normalized["Authorization"] = v
            elif lk == "x_goog_authuser":
                normalized["X-Goog-AuthUser"] = v
            # Blacklist OAuth-triggering keys
            elif lk in [
                "oauth_credentials",
                "client_id",
                "client_secret",
                "access_token",
                "refresh_token",
                "token_type",
                "expires_at",
                "expires_in",
            ]:
                print(f"  [Security] Dropping OAuth-triggering field: {k}")
                continue
            else:
                # Title-Case other headers as a safe default
                nk = "-".join([part.capitalize() for part in k.split("-")])
                if nk.lower().startswith("x-"):
                    nk = k  # Preserve X-Goog etc. original casing
                normalized[nk] = v

        # Cleanup duplicates that might have been created by normalization
        final = {}
        for k, v in normalized.items():
            if k in [
                "Cookie",
                "User-Agent",
                "Accept-Language",
                "Content-Type",
                "Authorization",
                "X-Goog-AuthUser",
            ]:
                final[k] = v
            elif k.lower() not in [
                "cookie",
                "user-agent",
                "accept-language",
                "content-type",
                "authorization",
                "x-goog-authuser",
            ]:
                final[k] = v

        # Ensure minimal required headers for stability
        if "Accept-Language" not in final:
            final["Accept-Language"] = "en-US,en;q=0.9"
        if "Content-Type" not in final:
            final["Content-Type"] = "application/json"

        print(f"Finalized headers: {list(final.keys())}")
        return final

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
                    with open(auth_input, "r") as f:
                        headers = json.load(f)
                else:
                    # Try parsing as JSON string
                    try:
                        headers = json.loads(auth_input)
                    except json.JSONDecodeError:
                        # Legacy raw headers string support
                        from ytmusicapi.auth.browser import setup_browser

                        headers = json.loads(
                            setup_browser(filepath=None, headers_raw=auth_input)
                        )
            elif isinstance(auth_input, dict):
                headers = auth_input

            if not headers:
                print("Invalid auth input.")
                return False

            # CRITICAL: Enforce Headers for Stability
            # 1. Accept-Language must be English to avoid parsing errors
            headers["Accept-Language"] = "en-US,en;q=0.9"

            # 2. Ensure User-Agent is consistent/modern if missing
            if "User-Agent" not in headers:
                headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
                )

            # 3. Content-Type often needed for JSON payloads
            if "Content-Type" not in headers:
                headers["Content-Type"] = "application/json; charset=UTF-8"

            # 4. Standardize headers and remove Bearer tokens
            headers = self._normalize_headers(headers)

            # Save to data/headers_auth.json (Overwrite)
            os.makedirs(os.path.dirname(self.auth_path), exist_ok=True)
            if os.path.exists(self.auth_path):
                try:
                    os.remove(self.auth_path)
                except Exception:
                    pass
            with open(self.auth_path, "w") as f:
                json.dump(headers, f)

            # Initialize API with dict directly
            print(f"Initializing YTMusic with headers: {list(headers.keys())}")
            self.api = YTMusic(auth=headers)

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
            import traceback

            print(f"Login exception: {e}")
            traceback.print_exc()
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

    def get_watch_playlist(
        self, video_id=None, playlist_id=None, limit=25, radio=False
    ):
        if not self.api:
            return {}
        try:
            res = self.api.get_watch_playlist(
                videoId=video_id, playlistId=playlist_id, limit=limit, radio=radio
            )
            print(
                f"--- API RESPONSE: get_watch_playlist({video_id}, {playlist_id}) ---"
            )
            print(json.dumps(res, indent=2))
            return res
        except Exception as e:
            print(f"Error getting watch playlist: {e}")
            return {}

    def get_cached_playlist_tracks(self, playlist_id):
        return self._playlist_cache.get(playlist_id)

    def set_cached_playlist_tracks(self, playlist_id, tracks):
        self._playlist_cache[playlist_id] = tracks

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
        print("--- API RESPONSE: get_liked_songs ---")
        print(json.dumps(res, indent=2))
        return res

    def get_charts(self, country="US"):
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

    def rate_song(self, video_id, rating="LIKE"):
        """
        Rate a song: 'LIKE', 'DISLIKE', or 'INDIFFERENT'.
        """
        if not self.is_authenticated():
            return False
        try:
            res = self.api.rate_song(video_id, rating)
            print(f"--- API RESPONSE: rate_song({video_id}, {rating}) ---")
            print(json.dumps(res, indent=2))
            return True
        except Exception as e:
            print(f"Error rating song: {e}")
            return False

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

    def logout(self):
        """
        Log out by deleting the saved auth file and resetting the API.
        """
        if os.path.exists(self.auth_path):
            try:
                os.remove(self.auth_path)
                print(f"Removed auth file at {self.auth_path}")
            except Exception as e:
                print(f"Could not remove auth file: {e}")

        self.api = YTMusic()
        self._is_authed = False
        print("Logged out. API reset to unauthenticated mode.")
        return True

    def edit_playlist(
        self, playlist_id, title=None, description=None, privacy=None, moveItem=None
    ):
        if not self.is_authenticated():
            return False
        try:
            res = self.api.edit_playlist(
                playlist_id,
                title=title,
                description=description,
                privacyStatus=privacy,
                moveItem=moveItem,
            )
            print(f"--- API RESPONSE: edit_playlist({playlist_id}) ---")
            print(json.dumps(res, indent=2))
            return True
        except Exception as e:
            print(f"Error editing playlist: {e}")
            return False

    def set_playlist_thumbnail(self, playlist_id, image_path):
        """
        Sets a custom thumbnail for a playlist.
        Uses the internal endpoint 'playlist/set_playlist_thumbnail'.
        """
        # shit
        if not self.is_authenticated():
            return False
        try:
            import base64
            with open(image_path, "rb") as f:
                img_data = f.read()
                b64_img = base64.b64encode(img_data).decode("utf-8")

            # common internal payload formats
            # Format A: {"playlistId": "...", "image": "base64..."}
            # Format B: {"playlistId": "...", "image": {"encodedImage": "base64..."}}
            # Format C: {"playlistId": "...", "image": {"image": "base64..."}}
            formats = [
                {"playlistId": playlist_id, "image": b64_img},
                {"playlistId": playlist_id, "image": {"encodedImage": b64_img}},
                {"playlistId": playlist_id, "image": {"image": b64_img}},
            ]

            success = False
            for i, body in enumerate(formats):
                print(f"DEBUG: trying thumbnail upload format {chr(65+i)} for {playlist_id}")
                try:
                    res = self.api._send_request("playlist/set_playlist_thumbnail", body)
                    print(f"DEBUG: Format {chr(65+i)} response: {res}")
                    success = True
                    if isinstance(res, dict) and res.get("status") == "SUCCEEDED":
                        break
                except Exception as e:
                    print(f"DEBUG: Format {chr(65+i)} failed: {e}")
                    if "Expecting value" in str(e): # in some internal endpoints, empty response means success.. 
                        success = True
                        break
                    continue
            
            return success
        except Exception as e:
            print(f"Error setting playlist thumbnail: {e}")
            return False
