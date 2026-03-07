from gi.repository import Gtk, Adw, GObject, GLib, Pango, Gio, Gdk
import threading
from api.client import MusicClient
from ui.utils import AsyncPicture, LikeButton, parse_item_metadata


class SearchPage(Adw.Bin):
    def __init__(self, player, open_playlist_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.client = MusicClient()
        self.open_playlist_callback = open_playlist_callback

        # Layout
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Search Bar removed (Global in MainWindow)

        # Content Stack

        # Content Stack
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)

        # 1. Results View
        results_scrolled = Gtk.ScrolledWindow()
        results_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        results_clamp = Adw.Clamp()

        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.results_box.set_margin_top(24)
        self.results_box.set_margin_bottom(24)
        self.results_box.set_margin_start(12)
        self.results_box.set_margin_end(12)

        results_clamp.set_child(self.results_box)
        results_scrolled.set_child(results_clamp)

        self.stack.add_named(results_scrolled, "results")

        # 2. Loading View
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)

        self.spinner = Adw.Spinner()
        self.spinner.set_size_request(32, 32)
        # self.spinner.set_spinning(True) # Adw.Spinner spins by default
        loading_box.append(self.spinner)

        loading_label = Gtk.Label(label="Searching...")
        loading_label.add_css_class("dim-label")
        loading_box.append(loading_label)

        self.stack.add_named(loading_box, "loading")

        # 3. Explore View (Default)
        explore_scrolled = Gtk.ScrolledWindow()
        explore_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        # Clamp for Explore
        explore_clamp = Adw.Clamp()

        self.explore_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.explore_box.set_margin_top(24)
        self.explore_box.set_margin_bottom(24)
        self.explore_box.set_margin_start(12)
        self.explore_box.set_margin_end(12)

        explore_clamp.set_child(self.explore_box)
        explore_scrolled.set_child(explore_clamp)

        self.stack.add_named(explore_scrolled, "explore")

        box.append(self.stack)

        self.set_child(box)
        self.search_timer = None

        # Show explore initially
        self.stack.set_visible_child_name("explore")

        # Player listeners
        self.loading_row_spinner = None
        self.player.connect("state-changed", self.on_player_state_changed)

        # Load explore data
        self.load_explore_data()

    def on_key_pressed(self, controller, keyval, keycode, state):
        # If user types and entry is not focused, focus it
        # We ignore modifier keys to avoid grabbing shortcuts
        # We permit normal typing
        if not self.search_entry.is_focus():
            # Basic check to see if it's a printable character or backspace
            # We want to allow the event to propagate so the entry handles it
            # Focus the search entry to allow typing. Forwarding the event handles the first character.

            if keyval < 65000:  # Rough check for non-special keys?
                self.search_entry.grab_focus()
                return controller.forward(self.search_entry)

        return False

    def load_explore_data(self):
        thread = threading.Thread(target=self._fetch_explore)
        thread.daemon = True
        thread.start()

    def refresh_explore(self):
        self.load_explore_data()

    def _fetch_explore(self):
        try:
            # We can fetch both explore and charts if we want a super-home
            explore = self.client.get_explore()
            GObject.idle_add(self.update_explore_ui, explore)
        except Exception as e:
            print(f"Error fetching explore data: {e}")

    def update_explore_ui(self, data):
        if not data:
            return

        # Clear existing explore content
        child = self.explore_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.explore_box.remove(child)
            child = next_child

        # New Releases (Albums/Singles)
        if "new_releases" in data and isinstance(data["new_releases"], list):
            self.add_section(
                self.explore_box, "New Albums & Singles", data["new_releases"][:10]
            )

        # New Music Videos
        if "new_videos" in data and isinstance(data["new_videos"], list):
            self.add_section(
                self.explore_box, "New Music Videos", data["new_videos"][:5]
            )

        # Moods & Genres
        if "moods_and_genres" in data and isinstance(data["moods_and_genres"], list):
            self.add_grid_section(
                self.explore_box, "Moods & Genres", data["moods_and_genres"][:12]
            )

        # Trending
        if "trending" in data and data["trending"] and "items" in data["trending"]:
            self.add_section(
                self.explore_box, "Trending", data["trending"]["items"][:5]
            )

    def add_grid_section(self, parent_box, title, items):
        if not items:
            return

        label = Gtk.Label(label=title)
        label.add_css_class("heading")
        label.set_halign(Gtk.Align.START)
        parent_box.append(label)

        flow_box = Gtk.FlowBox()
        flow_box.set_valign(Gtk.Align.START)
        flow_box.set_max_children_per_line(30)  # Allow wrapping
        flow_box.set_min_children_per_line(2)
        flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        flow_box.set_column_spacing(12)
        flow_box.set_row_spacing(12)
        flow_box.set_homogeneous(True)  # Make buttons same size if possible

        for item in items:
            btn_label = Gtk.Label(label=item.get("title", "Unknown"))
            btn_label.set_ellipsize(Pango.EllipsizeMode.END)
            btn_label.set_width_chars(1)
            btn_label.set_max_width_chars(20)  # Reasonable max

            button = Gtk.Button()
            button.set_child(btn_label)
            button.item_data = item
            button.connect("clicked", self.on_grid_button_clicked)
            flow_box.append(button)

        parent_box.append(flow_box)

    def on_grid_button_clicked(self, button):
        if hasattr(button, "item_data"):
            data = button.item_data
            print(f"Clicked grid item: {data.get('title')}")
            # Here we would navigate to a mood page using data['params']
            if "params" in data:
                print(f"Open Mood params: {data['params']}")

    def add_section(self, parent_box, title, items):
        if not items:
            return

        # Wrap label and listbox in a box to control spacing
        section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        parent_box.append(section_box)

        label = Gtk.Label(label=title)
        label.add_css_class("heading")
        label.set_halign(Gtk.Align.START)
        section_box.append(label)

        list_box = Gtk.ListBox()
        list_box.add_css_class("boxed-list")
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.connect("row-activated", self.on_row_activated)

        for item in items:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.add_css_class("song-row")
            row.set_child(box)

            # Subtitle
            subtitle = ""

            # Special handling for Artist results to avoid redundant name
            if item.get("resultType") == "artist":
                if "subscribers" in item:
                    count = item.get("subscribers", "")
                    if (
                        count
                        and count[-1].isdigit() is False
                        and "listeners" not in count
                        and "subscribers" not in count
                    ):
                        subtitle = f"{count} monthly listeners"
                    else:
                        subtitle = count
            elif "artists" in item:
                artists = item.get("artists", [])
                subtitle = ", ".join([a["name"] for a in artists])

                # Check for Album type
                if "type" in item:
                    subtitle += f" • {item['type']}"
            elif "subscribers" in item:
                subtitle = item.get("subscribers", "")
            elif "itemCount" in item and item["itemCount"]:
                count = str(item["itemCount"])
                if "songs" not in count:
                    subtitle = f"{count} views"
                else:
                    subtitle = count

            # Cover Art
            thumbnails = item.get("thumbnails", [])
            thumb_url = thumbnails[-1]["url"] if thumbnails else None

            img = AsyncPicture(url=thumb_url, target_size=44, crop_to_square=True)
            img.add_css_class("song-img")
            if not thumb_url:
                img.set_from_icon_name("media-optical-symbolic")

            box.append(img)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_valign(Gtk.Align.CENTER)
            vbox.set_hexpand(True)

            title_label = Gtk.Label(label=item.get("title", "Unknown"))
            title_label.set_halign(Gtk.Align.START)
            title_label.set_ellipsize(Pango.EllipsizeMode.END)
            title_label.set_lines(1)

            subtitle_label = Gtk.Label(label=subtitle or "")
            subtitle_label.set_halign(Gtk.Align.START)
            subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
            subtitle_label.set_lines(1)
            subtitle_label.add_css_class("dim-label")
            subtitle_label.add_css_class("caption")

            title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            title_box.append(title_label)

            # Explicit Badge
            meta = parse_item_metadata(item)
            if meta["is_explicit"]:
                explicit_badge = Gtk.Label(label="E")
                explicit_badge.add_css_class("explicit-badge")
                explicit_badge.set_valign(Gtk.Align.CENTER)
                title_box.append(explicit_badge)

            vbox.append(title_box)
            vbox.append(subtitle_label)
            box.append(vbox)

            # Like Button
            if item.get("videoId"):
                like_btn = LikeButton(
                    self.client, item["videoId"], item.get("likeStatus", "INDIFFERENT")
                )
                like_btn.set_valign(Gtk.Align.CENTER)
                box.append(like_btn)

            row.item_data = item
            row.set_activatable(True)

            # Context Menu (Right Click)
            gesture = Gtk.GestureClick()
            gesture.set_button(3)  # Right click
            gesture.connect("released", self.on_row_right_click, row)
            row.add_controller(gesture)

            list_box.append(row)

        section_box.append(list_box)

    def on_external_search(self, text):
        if self.search_timer:
            GObject.source_remove(self.search_timer)

        if len(text) > 2:
            self.search_timer = GObject.timeout_add(600, self.perform_search, text)
        elif len(text) == 0:
            self.stack.set_visible_child_name("explore")

    def on_search_changed(self, entry):
        # Deprecated local handler
        pass

    def perform_search(self, query):
        self.search_timer = None

        # Show loading
        self.stack.set_visible_child_name("loading")
        # self.spinner.start()

        thread = threading.Thread(target=self._search_thread, args=(query,))
        thread.daemon = True
        thread.start()
        return False

    def _search_thread(self, query):
        results = self.client.search(query)
        GObject.idle_add(self.update_results, results)

    def update_results(self, results):
        # self.spinner.stop()
        self.stack.set_visible_child_name("results")

        # Clear existing results
        # Removing children from Box
        child = self.results_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.results_box.remove(child)
            child = next_child

        if not results:
            return

        # Group Results
        top_result = None
        artists = []
        songs = []
        albums = []
        videos = []
        playlists = []

        for r in results:
            # Normalize title for artists
            if "title" not in r:
                if "artist" in r:
                    r["title"] = r["artist"]
                elif "artists" in r and r["artists"]:
                    r["title"] = r["artists"][0]["name"]

            # Normalize browseId for Top Result (Artist)
            if "browseId" not in r and "artists" in r and r["artists"]:
                r["browseId"] = r["artists"][0]["id"]

            r_type = r.get("resultType")
            category = r.get("category")

            # Extract Top Result
            if category == "Top result" and not top_result:
                top_result = r
                continue

            if r_type == "artist":
                artists.append(r)
            elif r_type == "song":
                songs.append(r)
            elif r_type == "album":
                albums.append(r)
            elif r_type == "video":
                videos.append(r)
            elif r_type == "playlist" or category == "Community playlists":
                playlists.append(r)

        # Display Top Result first
        if top_result:
            self.add_section(self.results_box, "Top Result", [top_result])

        # Allow user specified order: Artists > Songs > Albums > Videos > Playlists
        self.add_section(self.results_box, "Artists", artists)
        self.add_section(self.results_box, "Songs", songs)
        self.add_section(self.results_box, "Albums", albums)
        self.add_section(self.results_box, "Videos", videos)
        self.add_section(self.results_box, "Community Playlists", playlists)

    def on_player_state_changed(self, player, state):
        if state == "playing" or state == "rec-started":
            # We need to find the row with the spinner and remove it.
            # Iterating through list box children is one way.
            # Or just keep a reference.
            if hasattr(self, "loading_row_spinner") and self.loading_row_spinner:
                # Remove suffix? AdwActionRow.remove(widget) works if it's a child.
                # Suffixes are children.
                try:
                    # We need the parent row of the spinner?
                    # or just: row.remove(spinner)
                    parent = self.loading_row_spinner.get_parent()
                    if parent:
                        parent.remove(self.loading_row_spinner)
                except Exception:
                    pass
                self.loading_row_spinner = None

    def on_row_activated(self, listbox, row):
        if hasattr(row, "playlist_data"):
            data = row.playlist_data
            if data["browseId"].startswith("VL"):
                data["browseId"] = data["browseId"][2:]

            initial_data = {
                "title": data.get("title"),
                "thumb": data["thumbnails"][-1]["url"]
                if data.get("thumbnails")
                else None,
                "author": data.get("runs", [{}])[0].get("text")
                if "runs" in data
                else None,  # basic guess
            }
            # For search results, author might be in subtitle or runs.
            # Pass title and thumb for immediate visual feedback.

            self.open_playlist_callback(data["browseId"], initial_data)

        elif hasattr(row, "item_data"):
            data = row.item_data
            title = data.get("title", "Unknown")
            res_type = data.get("resultType")

            # Helper to open playlist/album
            def open_pid(pid):
                initial_data = {
                    "title": title,
                    "thumb": data["thumbnails"][-1]["url"]
                    if data.get("thumbnails")
                    else None,
                    "author": ", ".join(
                        [a.get("name", "") for a in data.get("artists", [])]
                    )
                    if "artists" in data
                    else data.get("count", ""),
                }
                self.open_playlist_callback(pid, initial_data)

            # 1. Check resultType first (Robust for Search Results)
            if res_type in ["song", "video"]:
                if "videoId" in data:
                    # Build queue from the listbox (siblings)
                    queue_tracks = []
                    start_index = 0

                    # listbox is passed as argument
                    child = listbox.get_first_child()
                    idx = 0
                    while child:
                        if hasattr(child, "item_data"):
                            s_data = child.item_data
                            if "videoId" in s_data:
                                # Normalize
                                s_title = s_data.get("title", "Unknown")

                                s_thumb = ""
                                if s_data.get("thumbnails"):
                                    s_thumb = s_data["thumbnails"][-1]["url"]

                                s_artist = ""
                                if "artists" in s_data:
                                    s_artist = ", ".join(
                                        [a.get("name", "") for a in s_data["artists"]]
                                    )
                                elif "artist" in s_data:
                                    s_artist = s_data["artist"]

                                queue_tracks.append(
                                    {
                                        "videoId": s_data["videoId"],
                                        "title": s_title,
                                        "artist": s_artist,
                                        "thumb": s_thumb,
                                    }
                                )

                                if s_data.get("videoId") == data.get("videoId"):
                                    start_index = idx
                                idx += 1

                        child = child.get_next_sibling()

                    if queue_tracks:
                        self.player.set_queue(queue_tracks, start_index)
                    else:
                        # Fallback to single (shouldn't happen if we are here)
                        thumb_url = (
                            data.get("thumbnails", [])[-1]["url"]
                            if data.get("thumbnails")
                            else None
                        )
                        artist_name = (
                            ", ".join(
                                [a.get("name", "") for a in data.get("artists", [])]
                            )
                            if "artists" in data
                            else data.get("artist", "")
                        )
                        self.player.load_video(
                            data["videoId"], title, artist_name, thumb_url
                        )
                    return

            elif res_type in ["album", "single", "ep"]:
                # Prefer browseId (MPRE) or audioPlaylistId (OLAK)
                if "browseId" in data and data["browseId"].startswith("MPRE"):
                    open_pid(data["browseId"])
                    return
                elif "audioPlaylistId" in data:
                    open_pid(data["audioPlaylistId"])  # conversion will handle it
                    return
                elif "browseId" in data:
                    open_pid(data["browseId"])
                    return

            elif res_type == "playlist":
                if "playlistId" in data:
                    open_pid(data["playlistId"])
                    return
                elif "browseId" in data:
                    open_pid(data["browseId"])
                    return

            # 2. Fallback to Key-Based logic (for items without explicit resultType)
            if "videoId" in data and res_type not in [
                "album",
                "single",
                "ep",
                "playlist",
                "artist",
            ]:
                thumb_url = ""
                thumbnails = data.get("thumbnails", [])
                if thumbnails:
                    thumb_url = thumbnails[-1]["url"]

                artists_list = data.get("artists", [])
                if isinstance(artists_list, list):
                    artist_name = ", ".join([a.get("name", "") for a in artists_list])
                else:
                    artist_name = data.get("artist", "")

                self.player.load_video(data["videoId"], title, artist_name, thumb_url)

            elif "audioPlaylistId" in data:
                open_pid(data["audioPlaylistId"])
            elif "playlistId" in data:
                open_pid(data["playlistId"])
            elif "browseId" in data:
                # Check if it's a playlist or artist
                if res_type in ["playlist", "album"] or data["browseId"].startswith(
                    ("VL", "PL", "RD", "OL", "MPRE")
                ):
                    open_pid(data["browseId"])
                else:
                    print(f"Open BrowseID (Artist?): {data['browseId']}")
                    # Check if we can navigate
                    root = self.get_root()
                    if hasattr(root, "open_artist"):
                        root.open_artist(data["browseId"], title)

    def on_row_right_click(self, gesture, n_press, x, y, row):
        if not hasattr(row, "item_data"):
            return

        data = row.item_data

        # Create Action Group for this row
        group = Gio.SimpleActionGroup()
        # Insert into ROW, so the popover (child of row) finds it
        row.insert_action_group("row", group)

        # Determine URL
        url = None
        if "videoId" in data:
            url = f"https://music.youtube.com/watch?v={data['videoId']}"
        elif "audioPlaylistId" in data:  # OLAK ID (Album) - Prioritize this!
            url = f"https://music.youtube.com/playlist?list={data['audioPlaylistId']}"
        elif "playlistId" in data:
            url = f"https://music.youtube.com/playlist?list={data['playlistId']}"
        elif "browseId" in data:
            bid = data["browseId"]
            if bid.startswith("MPRE") or bid.startswith("OLAK"):  # Album Fallback
                url = f"https://music.youtube.com/playlist?list={bid}"
            elif bid.startswith("UC") or bid.startswith("U"):  # Artist
                url = f"https://music.youtube.com/channel={bid}"
            elif bid.startswith("VL"):  # Playlist
                url = f"https://music.youtube.com/playlist?list={bid[2:]}"
            else:  # Fallback
                url = f"https://music.youtube.com/browse/{bid}"

        # Copy Link
        def copy_link_action(action, param):
            if url:
                try:
                    clipboard = Gdk.Display.get_default().get_clipboard()
                    clipboard.set(url)
                    print(f"Copied to clipboard: {url}")
                except Exception as e:
                    print(f"Clipboard error: {e}")

        # Go To Artist
        def goto_artist_action(action, param):
            # Check for artist in data
            # Determine main artist
            artist_item = None
            if "artists" in data and data["artists"]:
                artist_item = data["artists"][0]
            elif "artist" in data:
                # sometimes simple string, sometimes dict? In search results usually list of dicts.
                pass
            elif data.get("resultType") == "artist":
                # It IS an artist
                artist_item = {
                    "id": data.get("browseId"),
                    "name": data.get("artist") or data.get("title"),
                }

            if artist_item and artist_item.get("id"):
                aid = artist_item.get("id")
                name = artist_item.get("name")
                root = self.get_root()
                if hasattr(root, "open_artist"):
                    root.open_artist(aid, name)

        # Add Actions
        action_copy = Gio.SimpleAction.new("copy_link", None)
        action_copy.connect("activate", copy_link_action)
        group.add_action(action_copy)

        action_goto = Gio.SimpleAction.new("goto_artist", None)
        action_goto.connect("activate", goto_artist_action)
        group.add_action(action_goto)

        # Add to Playlist
        def add_to_playlist_action(action, param):
            target_pid = param.get_string()
            target_vid = data.get("videoId")
            if target_pid and target_vid:

                def thread_func():
                    success = self.client.add_playlist_items(target_pid, [target_vid])
                    if success:
                        print(f"Added {target_vid} to {target_pid}")
                    else:
                        print(f"Failed to add {target_vid} to {target_pid}")

                threading.Thread(target=thread_func, daemon=True).start()

        action_add = Gio.SimpleAction.new("add_to_playlist", GLib.VariantType.new("s"))
        action_add.connect("activate", add_to_playlist_action)
        group.add_action(action_add)

        # Build Menu Model
        menu_model = Gio.Menu()

        if url:
            menu_model.append("Copy Link", "row.copy_link")

        # Add to Playlist Submenu
        if "videoId" in data:
            playlists = self.client.get_editable_playlists()
            if playlists:
                playlist_menu = Gio.Menu()
                for p in playlists:
                    p_title = p.get("title", "Unknown Playlist")
                    p_id = p.get("playlistId")
                    if p_id:
                        playlist_menu.append(p_title, f"row.add_to_playlist('{p_id}')")
                menu_model.append_submenu("Add to Playlist", playlist_menu)

        has_artist = False
        if "artists" in data and data["artists"] and data["artists"][0].get("id"):
            has_artist = True
        elif data.get("resultType") == "artist" and data.get("browseId"):
            # If it's an artist row, "Go to Artist" is just activating the row.
            # Maybe "Open" instead? Or just omit.
            # Let's keep it context menu usually has "Go to Artist" even on Artist.
            has_artist = True

        if has_artist:
            menu_model.append("Go to Artist", "row.goto_artist")

        if menu_model.get_n_items() > 0:
            popover = Gtk.PopoverMenu.new_from_model(menu_model)
            popover.set_parent(row)
            popover.set_has_arrow(False)

            # Set rectangle to click position
            rect = Gdk.Rectangle()
            rect.x = int(x)
            rect.y = int(y)
            rect.width = 1
            rect.height = 1
            popover.set_pointing_to(rect)

            popover.popup()
