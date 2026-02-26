import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Gdk, Adw, GObject, Gio


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_default_size(1000, 700)
        self.set_title("Mixtapes")

        # Add custom icons path relative to current file or project root
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        assets_path = os.path.join(project_root, "assets", "icons")

        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        # Add GResource path
        # Add GResource path
        # The resource prefix is /com/pocoguy/muse/icons
        # The content inside is hicolor/scalable/actions/compass2-symbolic.svg
        icon_theme.add_resource_path("/com/pocoguy/muse/icons")

        # Keep file path as backup/dev
        icon_theme.add_search_path(assets_path)

        # Setup Actions
        self.setup_actions()

        # Key Controller (Global Type to Search)
        ctrl = Gtk.EventControllerKey()
        ctrl.connect("key-released", self.on_window_key_released)
        self.add_controller(ctrl)

        # Menu (About/Preferences)
        menu = Gio.Menu()
        menu.append("Preferences", "win.preferences")  # Changed to win.
        menu.append("About Mixtapes", "win.about")  # Changed to win.

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(menu)

        # Content setup: ViewStack
        self.view_stack = Adw.ViewStack()
        self.view_stack.connect("notify::visible-child", self.on_view_changed)

        # Toolbar View (Root) - Wraps EVERYTHING
        self.root_content_view = Adw.ToolbarView()

        # Global Header Setup
        self.header_bar = Adw.HeaderBar()

        # Back Button
        self.back_btn = Gtk.Button(icon_name="go-previous-symbolic")
        self.back_btn.set_visible(False)  # Hidden by default
        self.back_btn.connect("clicked", self.on_back_clicked)
        self.header_bar.pack_start(self.back_btn)

        # Center Widget (Switcher / Title)
        self.title_bin = Adw.Bin()

        self.switcher = Adw.ViewSwitcher()
        self.switcher.set_stack(self.view_stack)
        self.switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)

        self.title_widget = Adw.WindowTitle(title="Mixtapes")

        # Default to Desktop
        self.title_bin.set_child(self.switcher)
        self.header_bar.set_title_widget(self.title_bin)

        # Add Menu Button
        self.header_bar.pack_end(menu_btn)

        # Search Button (Mobile/Contextual) - Toggle
        self.search_btn = Gtk.ToggleButton(icon_name="system-search-symbolic")
        self.header_bar.pack_start(self.search_btn)

        self.root_content_view.add_top_bar(self.header_bar)

        self.search_bar = Gtk.SearchBar()
        self.search_bar.set_key_capture_widget(self)  # Capture keys
        self.search_bar.connect(
            "notify::search-mode-enabled", self.on_search_mode_changed
        )

        # Ensure it stays in sync (Binding)
        # We need to bind self.search_btn.active <-> self.search_bar.search_mode_enabled
        # But Gtk.SearchBar property is 'search-mode-enabled'
        self.search_bar.bind_property(
            "search-mode-enabled",
            self.search_btn,
            "active",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )

        # Configure Search Entry
        search_clamp = Adw.Clamp()
        search_clamp.set_maximum_size(600)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self.on_global_search_changed)
        self.search_entry.connect("stop-search", self.on_search_stop)

        search_clamp.set_child(self.search_entry)
        self.search_bar.set_child(search_clamp)
        self.search_bar.connect_entry(self.search_entry)  # NOW it exists

        self.root_content_view.add_top_bar(self.search_bar)

        # Wrap content in OverlaySplitView for Sidebar
        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_sidebar_position(Gtk.PackType.END)
        self.split_view.set_min_sidebar_width(320)
        # self.split_view.set_collapsed(True) # Optional: Force overlay even on wide screens?
        # "toggling queue" suggests overlay or dismissible sidebar.
        # OverlaySplitView automatically handles collapsing based on width, but we can toggle sidebar visibility.

        # Main Content Area (Scrolled)
        self.content_bin = Gtk.ScrolledWindow()
        self.content_bin.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.content_bin.set_child(self.view_stack)

        self.split_view.set_content(self.content_bin)

        # Queue Sidebar (Right Side)
        from ui.queue_panel import QueuePanel

        # Global Player (Init before queue panel)
        from player.player import Player

        self.player = Player()

        self.queue_panel = QueuePanel(self.player)

        self.split_view.set_sidebar(self.queue_panel)
        self.split_view.set_show_sidebar(False)  # Hidden by default

        # Signal for Sidebar visibility sync
        self.split_view.connect(
            "notify::show-sidebar", self._on_sidebar_visibility_changed
        )
        self.split_view.connect("notify::collapsed", self._on_split_view_collapsed)

        self.root_content_view.set_content(self.split_view)

        # Global Player Bar (Always Visible)
        from ui.player_bar import PlayerBar
        from ui.pages.playlist import (
            PlaylistPage,
        )  # Import here to avoid circular dep if any
        from ui.pages.artist import ArtistPage

        # Player already inited above
        self.player_bar = PlayerBar(
            self.player,
            on_artist_click=self.on_player_bar_artist_click,
            on_queue_click=self.toggle_queue,
            on_album_click=self.on_player_bar_album_click,
        )
        self.player_bar.connect("expand-requested", self.on_expand_requested)
        self.root_content_view.add_bottom_bar(self.player_bar)

        # View Switcher Bar (Mobile) - Stacked above Player Bar?
        self.view_switcher_bar = Adw.ViewSwitcherBar()
        self.view_switcher_bar.set_stack(self.view_stack)
        self.view_switcher_bar.set_reveal(False)
        self.view_switcher_bar.set_visible(False)
        self.root_content_view.add_bottom_bar(self.view_switcher_bar)

        from ui.expanded_player import ExpandedPlayer

        # 1. Initialize the BottomSheet
        self.bottom_sheet = Adw.BottomSheet()
        self.bottom_sheet.set_show_drag_handle(True)

        # 2. Set the main app as the content
        self.bottom_sheet.set_content(self.root_content_view)

        # 3. Initialize your ExpandedPlayer (now as a standalone Box/Widget)
        self.expanded_player = ExpandedPlayer(
            self.player,
            on_artist_click=self.on_player_bar_artist_click,
            on_album_click=self.on_player_bar_album_click,
        )
        self.expanded_player.add_css_class("player-drawer")

        # Connect the dismiss signal to close the sheet
        self.expanded_player.connect(
            "dismiss", lambda x: self.bottom_sheet.set_open(False)
        )

        # 4. Set the player as the sheet
        self.bottom_sheet.set_sheet(self.expanded_player)

        # 5. Set the window content to the BottomSheet
        self.set_content(self.bottom_sheet)

        # Initialize Pages (Must be before breakpoint)
        self.init_pages()

        # Responsive Breakpoint
        breakpoint = Adw.Breakpoint.new(
            Adw.BreakpointCondition.new_length(
                Adw.BreakpointConditionLengthType.MAX_WIDTH, 550, Adw.LengthUnit.PX
            )
        )
        breakpoint.add_setter(self.view_switcher_bar, "reveal", True)
        breakpoint.add_setter(self.view_switcher_bar, "visible", True)
        breakpoint.add_setter(self.split_view, "collapsed", True)

        # Compact Mode for Player Bar
        breakpoint.connect("apply", lambda _: self.player_bar.set_compact(True))
        breakpoint.connect("unapply", lambda _: self.player_bar.set_compact(False))

        # We need to propagate set_compact_mode to the ACTIVE playlist page if exists
        # Since we have multiple NavViews, we need a smarter handler
        breakpoint.connect("apply", self._on_mobile_breakpoint_apply)
        breakpoint.connect("unapply", self._on_mobile_breakpoint_unapply)
        self.add_breakpoint(breakpoint)

        # Check Authentication
        self.check_auth()

    def _get_active_playlist_page(self):
        # Helper to find if visible view is a Playlist Page
        nav = self.view_stack.get_visible_child()
        if isinstance(nav, Adw.NavigationView):
            # Get visible page
            page = nav.get_visible_page()
            # Check child
            if page:
                child = page.get_child()  # ToolbarView
                if isinstance(child, Adw.ToolbarView):
                    content = child.get_content()
                    if hasattr(content, "set_compact_mode"):
                        return content
                elif hasattr(child, "set_compact_mode"):
                    return child
        return None

    def _on_mobile_breakpoint_apply(self, breakpoint):
        page = self._get_active_playlist_page()
        if page:
            page.set_compact_mode(True)

        # Switch to Mobile Title
        if hasattr(self, "title_bin"):
            self.title_bin.set_child(self.title_widget)

    def _on_mobile_breakpoint_unapply(self, breakpoint):
        page = self._get_active_playlist_page()
        if page:
            page.set_compact_mode(False)

        # Switch to Desktop Switcher
        if hasattr(self, "title_bin"):
            self.title_bin.set_child(self.switcher)

        # Close the bottom sheet when returning to desktop size
        if hasattr(self, "bottom_sheet") and self.bottom_sheet.get_open():
            self.bottom_sheet.set_open(False)

    def on_view_changed(self, stack, param):
        # Update Back Button for the new active tab
        self.update_back_button_visibility()

        # Close Search Bar when switching tabs (unless we switched TO search because of typing)
        # Check if we are in search mode
        if self.search_bar.get_search_mode():
            # Close search bar if we are leaving the search tab (e.g. clicking Home).
            if self.view_stack.get_visible_child_name() != "search":
                self.search_bar.set_search_mode(False)

    def on_playlist_header_title_changed(self, page, title):
        if hasattr(self, "title_widget"):
            self.title_widget.set_title(title if title else "Mixtapes")

    def update_back_button_visibility(self, *args):
        nav = self._get_active_nav_view()
        if nav:
            visible_page = nav.get_visible_page()
            if visible_page and nav.get_previous_page(visible_page):
                self.back_btn.set_visible(True)
            else:
                self.back_btn.set_visible(False)
                # Reset title when back at root
                if hasattr(self, "title_widget"):
                    self.title_widget.set_title("Mixtapes")
        else:
            self.back_btn.set_visible(False)

    def on_back_clicked(self, btn):
        nav = self._get_active_nav_view()
        if nav:
            nav.pop()

    def _get_active_nav_view(self):
        nav = self.view_stack.get_visible_child()
        if isinstance(nav, Adw.NavigationView):
            return nav
        return None

    def setup_actions(self):
        # About Action
        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", self.show_about)
        self.add_action(action)

        # Preferences Action
        pref_action = Gio.SimpleAction.new("preferences", None)
        pref_action.connect("activate", self.show_preferences)
        self.add_action(pref_action)

    def show_about(self, action, param):
        about = Adw.AboutDialog()
        about.set_application_name("Mixtapes")
        about.set_developer_name("POCOGuy")
        about.set_version("alpha 202602262349")
        about.set_website("https://www.pocoguy.com/")
        about.set_copyright("© 2026 POCOGuy")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.present(self)

    def show_preferences(self, action, param):
        prefs = Adw.PreferencesDialog()

        page = Adw.PreferencesPage()
        page.set_title("General")
        page.set_icon_name("settings-symbolic")
        prefs.add(page)

        group = Adw.PreferencesGroup()
        group.set_title("Account")
        page.add(group)

        # Sign Out Row
        row = Adw.ActionRow()
        row.set_title("Sign Out")
        row.set_subtitle("Remove saved credentials and log out of YouTube Music")

        logout_btn = Gtk.Button(label="Sign Out")
        logout_btn.set_valign(Gtk.Align.CENTER)
        logout_btn.add_css_class("destructive-action")
        logout_btn.connect("clicked", self.on_logout_clicked, prefs)

        row.add_suffix(logout_btn)
        group.add(row)

        prefs.present(self)

    def on_logout_clicked(self, btn, prefs_window):
        from api.client import MusicClient

        client = MusicClient()
        if client.logout():
            prefs_window.close()
            # Clear library UI immediately
            if hasattr(self, "library_page"):
                self.library_page.clear()
            # Trigger auth check to show login dialog
            self.check_auth()

    def init_pages(self):
        from ui.pages.home import HomePage
        from ui.pages.library import LibraryPage
        from ui.pages.search import SearchPage
        # PlaylistPage imported at top level now

        # Create Pages
        # Refactored to Single Global Header architecture
        # Each tab is just a NavigationView wrapping the content

        def create_tab_nav(page_content, title, icon, name):
            # Nav Page & View
            # We wrap content in NavigationPage because NavigationView requires it
            nav_page = Adw.NavigationPage(child=page_content, title=title)
            nav_page.set_tag("root")  # Tag for resetting
            nav_view = Adw.NavigationView()
            nav_view.add(nav_page)

            # Connect to page changes to update Back Button
            nav_view.connect("notify::visible-page", self.update_back_button_visibility)
            nav_view.connect("notify::visible-page", self.update_back_button_visibility)

            return nav_view

        # Instantiate Pages
        home_page = HomePage(self.player)
        self.library_page = LibraryPage(self.player, self.open_playlist)
        search_page = SearchPage(self.player, self.open_playlist)
        self.search_page = search_page  # Store for global key controller

        self.tab_header_widgets = []  # Init list

        # Add to Stack and Configure Pages
        page_home = self.view_stack.add_named(
            create_tab_nav(home_page, "Home", "user-home-symbolic", "home"), "home"
        )
        page_home.set_title("Home")
        page_home.set_icon_name("user-home-symbolic")

        page_lib = self.view_stack.add_named(
            create_tab_nav(
                self.library_page, "Library", "media-optical-symbolic", "library"
            ),
            "library",
        )
        page_lib.set_title("Library")
        page_lib.set_icon_name("media-optical-symbolic")

        page_lib.set_icon_name("media-optical-symbolic")

        page_search = self.view_stack.add_named(
            create_tab_nav(search_page, "Explore", "compass2-symbolic", "search"),
            "search",
        )
        page_search.set_title("Explore")
        page_search.set_icon_name("compass2-symbolic")

        self.previous_view_stack_item = "home"

    def set_header_title(self, title):
        pass

    def _get_page_content(self, tab_name):
        # Helper to traverse: NavView -> NavPage -> ToolbarView -> Content
        nav_view = self.view_stack.get_child_by_name(tab_name)
        if isinstance(nav_view, Adw.NavigationView):
            # We assume the root page of the nav view is our tab page
            # We stored page instances in init_pages, so direct traversal is not needed for Search/Library.
            pass
        return None

    def on_window_key_released(self, controller, keyval, keycode, state):
        # Allow type-to-search from anywhere
        # Check if focus is already in an entry
        focus = self.get_focus()
        if isinstance(focus, (Gtk.Entry, Gtk.SearchEntry, Gtk.TextView, Gtk.Editable)):
            return False

        # Get Unicode character
        uni = Gdk.keyval_to_unicode(keyval)
        if uni == 0:
            return False

        char = chr(uni)
        if not char.isprintable():
            return False

        # Ignore control keys
        mask = state & (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.ALT_MASK
            | Gdk.ModifierType.META_MASK
        )
        if mask:
            return False

        # Switch to Search Page AND Reveal Bar
        self.search_bar.set_search_mode(True)

        # Only switch page if NOT in a playlist (Context-Aware)
        playlist_page = self._get_active_playlist_page()

        if not playlist_page:
            self.view_stack.set_visible_child_name("search")
            # Reset search view to root
            nav = self.view_stack.get_child_by_name("search")
            if isinstance(nav, Adw.NavigationView):
                nav.pop_to_tag("root")

        # Forward event to search entry manually if needed,
        # but GtkSearchBar's key capture widget usually handles it.
        # If we return False (propagate), SearchBar sees it.
        # Let's ensure focus.
        self.search_entry.grab_focus()

        # Append logic is usually handled by Capture Widget automatically?
        # If we return False, it bubbles to MainWindow -> captured by SearchBar.
        return False

    def on_global_search_changed(self, entry):
        text = entry.get_text()

        # Context-Aware Search Logic
        playlist_page = self._get_active_playlist_page()
        if playlist_page:
            # Filter Playlist Content
            if hasattr(playlist_page, "filter_content"):
                playlist_page.filter_content(text)
        else:
            # Global Search: Switch to Explore Tab if not already there
            if self.view_stack.get_visible_child_name() != "search":
                self.view_stack.set_visible_child_name("search")
                # Reset search view to root
                nav = self.view_stack.get_child_by_name("search")
                if isinstance(nav, Adw.NavigationView):
                    nav.pop_to_tag("root")

            if hasattr(self, "search_page"):
                self.search_page.on_external_search(text)

    def on_search_stop(self, entry):
        self.search_bar.set_search_mode(False)
        # Clear filter if we were filtering?
        playlist_page = self._get_active_playlist_page()
        if playlist_page and hasattr(playlist_page, "filter_content"):
            playlist_page.filter_content("")

    def on_search_mode_changed(self, search_bar, param):
        mode = search_bar.get_search_mode()

        if mode:
            # Enabling search
            self.search_entry.grab_focus()

            # If we are NOT in a playlist, switch to Explore tab
            if not self._get_active_playlist_page():
                self.view_stack.set_visible_child_name("search")
                # Reset search view to root
                nav = self.view_stack.get_child_by_name("search")
                if isinstance(nav, Adw.NavigationView):
                    nav.pop_to_tag("root")

    # on_search_btn_clicked removed (replaced by binding)

    def open_playlist(self, playlist_id, initial_data=None):
        # Close search bar when navigating to a detail page
        if self.search_bar.get_search_mode():
            self.search_bar.set_search_mode(False)

        # Find active navigation view
        active_nav = self.view_stack.get_visible_child()
        if not isinstance(active_nav, Adw.NavigationView):
            print("Error: Active view is not a NavigationView")
            return

        # Create fresh playlist page (to ensure clean state and avoid parent issues)
        # We need to pass self.network_client? No, PlaylistPage creates its own.
        # We need self.player.
        # We need self.player.
        from ui.pages.playlist import PlaylistPage

        playlist_page = PlaylistPage(self.player)

        # Wrap in NavigationPage
        # PlaylistPage already has a ToolbarView/Header internally.
        # Adw.NavigationView expects Adw.NavigationPage.
        # Adw.NavigationPage expects a child widget.
        nav_page = Adw.NavigationPage(child=playlist_page, title="Playlist")

        # Push to stack
        active_nav.push(nav_page)

        # Load data
        playlist_page.load_playlist(playlist_id, initial_data)

        # Connect title change signal
        playlist_page.connect(
            "header-title-changed", self.on_playlist_header_title_changed
        )

        # Check if we are in mobile mode (compact) - Force true if width < 650
        # self.view_switcher_bar.get_reveal() might be delayed?
        width = self.get_width()
        if width < 650:
            playlist_page.set_compact_mode(True)
        elif hasattr(self, "view_switcher_bar") and self.view_switcher_bar.get_reveal():
            playlist_page.set_compact_mode(True)

        # Note: We don't need to manually update window title or back button.
        # Adw.NavigationView handles the transition.
        # PlaylistPage's internal header will show a back button IF it's an Adw.HeaderBar
        # AND we are using Adw.NavigationView.
        # BUT: PlaylistPage has `self.header_bar = Adw.HeaderBar()`.
        # When inside NavigationView, this header should automatically get a back button.
        pass

    def on_playlist_back(self):
        # Called when playlist internal back is triggered (if any)
        # We rely on NavView pop.
        pass

    def open_artist(self, channel_id, initial_name=None):
        # Close search bar when navigating to a detail page
        if self.search_bar.get_search_mode():
            self.search_bar.set_search_mode(False)

        # Find active navigation view
        active_nav = self.view_stack.get_visible_child()
        if not isinstance(active_nav, Adw.NavigationView):
            print("Error: Active view is not a NavigationView")
            return

        from ui.pages.artist import ArtistPage

        # Create fresh artist page
        artist_page = ArtistPage(self.player, self.open_playlist)

        nav_page = Adw.NavigationPage(
            child=artist_page, title=initial_name if initial_name else "Artist"
        )

        active_nav.push(nav_page)

        artist_page.load_artist(channel_id, initial_name)

        # Connect title change
        artist_page.connect(
            "header-title-changed", self.on_playlist_header_title_changed
        )  # Reuse same handler

    def on_player_bar_artist_click(self):
        pass

        print("Player Bar Artist Clicked")
        video_id = self.player.current_video_id
        if video_id:
            # We need to fetch details to get channel ID if we don't have it.
            # Or if we have simple implementation: search for artist name?
            # Better: fetch song details.
            pass
            # I'll implement a quick fetch in a thread
            import threading

            threading.Thread(target=self._resolve_artist_from_player).start()

    def _resolve_artist_from_player(self):
        vid = self.player.current_video_id
        if not vid:
            return

        from api.client import MusicClient

        client = MusicClient()
        song_data = client.get_song(vid)
        if song_data and "videoDetails" in song_data:
            channel_id = song_data["videoDetails"].get("channelId")
            if channel_id:
                # Open on main thread
                artist_name = song_data["videoDetails"].get("author", "Artist")
                GObject.idle_add(self.open_artist, channel_id, artist_name)

    def on_player_bar_album_click(self):
        print("Player Bar Album Clicked")
        import threading

        threading.Thread(target=self._resolve_album_from_player).start()

    def _resolve_album_from_player(self):
        vid = self.player.current_video_id
        if not vid:
            return

        # First check if the current track object in queue has the album ID natively
        track = None
        if 0 <= self.player.current_queue_index < len(self.player.queue):
            track = self.player.queue[self.player.current_queue_index]

        album_id = None
        album_name = "Album"

        if track and "album" in track and track["album"]:
            album = track["album"]
            if isinstance(album, dict):
                album_id = album.get("id")
                album_name = album.get("name", album_name)
            elif isinstance(album, str):
                album_name = album

        if not album_id:
            # Fall back to fetching watch playlist to see if it belongs to an album
            from api.client import MusicClient

            client = MusicClient()
            if client.api:
                try:
                    res = client.api.get_watch_playlist(videoId=vid)
                    tracks = res.get("tracks", [])
                    if tracks and "album" in tracks[0] and tracks[0]["album"]:
                        album = tracks[0]["album"]
                        if isinstance(album, dict):
                            album_id = album.get("id")
                            album_name = album.get("name", "Album")
                        elif isinstance(album, str):
                            album_name = album
                except Exception as e:
                    print(f"Failed to resolve album: {e}")

        if album_id:
            # Check if it starts with 'MPREb'
            if album_id.startswith("MPREb_"):
                # Get album, then take the audioPlaylistId
                from api.client import MusicClient

                client = MusicClient()
                playlist_id = client.api.get_album(album_id).get("audioPlaylistId")
                GObject.idle_add(self.open_playlist, playlist_id, {"title": album_name})
            else:
                # It's an implied playlist ID or similar
                GObject.idle_add(self.open_playlist, album_id, {"title": album_name})
        else:
            print("No album found for the current track.")

    def on_sidebar_row_selected(self, box, row):
        if row:
            # Ensure we are not in playlist view (pop if needed)
            # Basic logic: If we are deep in nav stack, pop to root.
            # self.nav_view.pop_to_tag("root")? No, "root" isn't a tag in that sense.
            # pop_to_page(self.root_nav_page)
            self.nav_view.pop_to_page(self.root_nav_page)

            self.view_stack.set_visible_child_name(row.name_id)
            self.set_header_title("Mixtapes")

            if row.name_id == "library":
                self.library_page.load_library()

    def check_auth(self):
        from api.client import MusicClient
        from ui.login import LoginDialog

        client = MusicClient()
        # Check if auth file exists AND is valid
        if not client.is_authenticated() or not client.validate_session():
            print("Authentication missing or invalid. Showing login dialog.")
            # Show login dialog
            # We need to do this after the window is shown or using a timeout
            GObject.timeout_add(500, lambda: self.show_login(LoginDialog))

    def show_login(self, dialog_cls):
        dialog = dialog_cls(self)
        dialog.connect("close-request", self.on_login_close)  # Handle close if needed
        dialog.present()
        return False

    def on_login_close(self, dialog):
        # Refresh data
        if hasattr(self, "library_page"):
            self.library_page.load_library()

    def _on_sidebar_visibility_changed(self, split_view, param):
        is_visible = split_view.get_show_sidebar()
        if hasattr(self, "player_bar"):
            self.player_bar.set_queue_active(is_visible)

    def _on_split_view_collapsed(self, split_view, param):
        is_collapsed = split_view.get_collapsed()
        if not is_collapsed:
            # We are un-collapsing (Mobile -> Desktop)
            # Ensure sidebar state matches our source of truth (the toggle button)
            if hasattr(self, "player_bar") and hasattr(self.player_bar, "queue_btn"):
                should_be_open = self.player_bar.queue_btn.get_active()
                if not should_be_open:
                    # Force closed if it tries to auto-open
                    split_view.set_show_sidebar(False)

    def toggle_queue(self):
        """Toggles the visibility of the Queue Sidebar."""
        if hasattr(self, "split_view"):
            current = self.split_view.get_show_sidebar()
            self.split_view.set_show_sidebar(not current)

        # Refresh explore/search
        if hasattr(self, "search_page"):
            self.search_page.refresh_explore()

        return False

    def on_expand_requested(self, player_bar):
        # Sync Initial State (Metadata/Art)
        v_id = self.player.current_video_id
        if v_id:
            t = (
                self.player_bar.current_title
                if hasattr(self.player_bar, "current_title")
                else "Loading..."
            )
            a = (
                self.player_bar.current_artist
                if hasattr(self.player_bar, "current_artist")
                else "Unknown"
            )
            self.expanded_player.on_metadata_changed(
                self.player, t, a, self.player_bar.cover_img.url, v_id, "INDIFFERENT"
            )

        # Open the sheet
        self.bottom_sheet.set_open(True)
