import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Gtk, Adw, WebKit, GObject
import json


class WebkitLoginView(Adw.Bin):
    __gsignals__ = {
        "login-finished": (GObject.SignalFlags.RUN_FIRST, None, (bool, str)),
    }

    def __init__(self):
        super().__init__()

        self.captured_headers = {}
        self.finished = False

        self.webview = WebKit.WebView()
        settings = self.webview.get_settings()

        # Google blocks non-standard browsers. We must masquerade as standard browser and enable features it expects.
        settings.set_user_agent(
            "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0"
        )
        settings.set_enable_javascript(True)
        settings.set_enable_webgl(True)
        settings.set_enable_html5_local_storage(True)
        settings.set_enable_html5_database(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.webview)
        self.webview.set_vexpand(True)

        # Manual Fallback Button
        self.btn_done = Gtk.Button(label="I'm Logged In (Manual)")
        self.btn_done.set_halign(Gtk.Align.CENTER)
        self.btn_done.add_css_class("pill")
        self.btn_done.set_margin_top(8)
        self.btn_done.set_margin_bottom(8)
        self.btn_done.connect("clicked", self.on_done_clicked)
        box.append(self.btn_done)

        self.set_child(box)

        # Connect to resource-load-started on the webview
        self.webview.connect("resource-load-started", self._on_resource_load_started)

        # Load YouTube Music login - Point directly to login and redirect to library for better UX
        login_url = "https://accounts.google.com/ServiceLogin?ltmpl=music&service=youtube&uilel=3&passive=true&continue=https%3A%2F%2Fmusic.youtube.com%2Flibrary"
        self.webview.load_uri(login_url)

    def _on_resource_load_started(self, webview, resource, request):
        uri = request.get_uri()
        headers = request.get_http_headers()

        print(f"\n[NETWORK] Request to: {uri}")
        if headers:
            headers.foreach(lambda name, value: print(f"  > {name}: {value}"))

        if self.finished:
            return

        # Target browse request specifically
        if "music.youtube.com/youtubei/v1/browse" in uri:
            if headers:
                cookie = headers.get_one("Cookie")
                auth = headers.get_one("Authorization")

                # Success criteria: SAPISID in cookie OR SAPISIDHASH in Authorization
                has_sapisid = cookie and (
                    "SAPISID" in cookie or "__Secure-3PAPISID" in cookie
                )
                has_auth_hash = auth and "SAPISIDHASH" in auth

                if has_sapisid or has_auth_hash:
                    print(f"\n!!! AUTHENTICATED BROWSE MATCH: {uri}")

                    # 1. Capture ALL current headers
                    self.captured_headers = {}
                    headers.foreach(
                        lambda n, v: self.captured_headers.__setitem__(n, v)
                    )

                    # 2. Check if we have cookies. If not, we must fetch them from CookieManager
                    # because WebKit sometimes redacts the Cookie header in this signal.
                    if not has_sapisid:
                        print(
                            "!!! Cookie header missing/incomplete. Fetching from CookieManager..."
                        )
                        session = self.webview.get_network_session()
                        cm = session.get_cookie_manager()
                        cm.get_cookies(
                            "https://music.youtube.com",
                            None,
                            self._on_cookies_retrieved,
                        )
                        # We don't set finished=True yet; we wait for the callback
                    else:
                        print(
                            f"!!! Captured {len(self.captured_headers)} headers with Cookie."
                        )
                        self.finished = True
                        GObject.idle_add(self._notify_success)

    def on_done_clicked(self, btn):
        print(
            "Manual 'Done' clicked. Attempting to extract cookies from CookieManager..."
        )
        session = self.webview.get_network_session()
        cm = session.get_cookie_manager()
        cm.get_cookies("https://music.youtube.com", None, self._on_cookies_retrieved)

    def _on_cookies_retrieved(self, cm, result):
        try:
            cookies = cm.get_cookies_finish(result)
            if not cookies:
                print("No cookies retrieved for music.youtube.com")
                return

            cookie_strs = []
            for c in cookies:
                cookie_strs.append(f"{c.get_name()}={c.get_value()}")

            cookie_full = "; ".join(cookie_strs)
            if "SAPISID" in cookie_full or "__Secure-3PAPISID" in cookie_full:
                print("Successfully retrieved authenticated Cookie from CookieManager.")
                self.captured_headers["Cookie"] = cookie_full

                # Ensure we have a User-Agent if we came from a manual click and headers were empty
                if "User-Agent" not in self.captured_headers:
                    self.captured_headers["User-Agent"] = (
                        "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0"
                    )

                self.finished = True
                self._notify_success()
            else:
                print("Cookies retrieved but session seems incomplete (no SAPISID).")
        except Exception as e:
            print(f"Error retrieving cookies: {e}")

    def _notify_success(self):
        print("Emitting login-finished with captured headers.")
        # Pass the headers as a JSON string to keep it consistent with existing login logic
        self.emit("login-finished", True, json.dumps(self.captured_headers))

    def clear_webkit_cookies(self):
        """Clears all cookies from the WebKit session for security."""
        print("Clearing WebKit session cookies...")
        try:
            session = self.webview.get_network_session()
            manager = session.get_website_data_manager()
            # 0 means all time. WebKit.WebsiteDataTypes.COOKIES = 1 << 0
            manager.clear(WebKit.WebsiteDataTypes.COOKIES, 0, None, None, None)
            print("WebKit session cookies cleared.")
        except Exception as e:
            print(f"Error clearing WebKit cookies: {e}")
