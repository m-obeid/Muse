from gi.repository import Gtk, Adw, GObject, GLib, Gdk, Gio, Pango
import threading
from api.client import MusicClient


class LibraryPage(Adw.Bin):
    def __init__(self, player, open_playlist_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.client = MusicClient()
        self.open_playlist_callback = open_playlist_callback
        self._is_loading = False

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Scrolled Window for all content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        clamp = Adw.Clamp()

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.content_box.set_margin_top(24)
        self.content_box.set_margin_bottom(24)
        self.content_box.set_margin_start(12)
        self.content_box.set_margin_end(12)

        clamp.set_child(self.content_box)
        scrolled.set_child(clamp)

        # 1. Playlists Section
        playlists_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        playlists_header_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12
        )
        playlists_header_box.set_size_request(
            -1, 34
        )  # Ensure consistent height with/without button

        playlists_label = Gtk.Label(label="Playlists")
        playlists_label.add_css_class("heading")
        playlists_label.set_halign(Gtk.Align.START)
        playlists_label.set_valign(Gtk.Align.CENTER)
        playlists_label.set_hexpand(True)
        playlists_header_box.append(playlists_label)

        self.new_playlist_btn = Gtk.Button(icon_name="list-add-symbolic")
        self.new_playlist_btn.add_css_class("flat")
        self.new_playlist_btn.add_css_class("circular")
        self.new_playlist_btn.set_valign(Gtk.Align.CENTER)
        self.new_playlist_btn.set_tooltip_text("New Playlist")
        self.new_playlist_btn.connect("clicked", self.on_new_playlist_clicked)
        playlists_header_box.append(self.new_playlist_btn)

        playlists_section.append(playlists_header_box)

        self.playlists_list = Gtk.ListBox()
        self.playlists_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.playlists_list.add_css_class("boxed-list")
        self.playlists_list.connect("row-activated", self.on_playlist_activated)
        playlists_section.append(self.playlists_list)

        self.content_box.append(playlists_section)

        # 2. Artists Section
        artists_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        artists_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        artists_header_box.set_size_request(-1, 34)

        artists_label = Gtk.Label(label="Artists")
        artists_label.add_css_class("heading")
        artists_label.set_halign(Gtk.Align.START)
        artists_label.set_valign(Gtk.Align.CENTER)
        artists_header_box.append(artists_label)

        artists_section.append(artists_header_box)

        self.artists_list = Gtk.ListBox()
        self.artists_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.artists_list.add_css_class("boxed-list")
        self.artists_list.connect("row-activated", self.on_artist_activated)
        artists_section.append(self.artists_list)

        self.content_box.append(artists_section)

        # We keep a Stack for compatibility or potential future detail views,
        # but the main library is now on a single page.
        self.stack = Adw.ViewStack()
        self.stack.add_named(scrolled, "root")

        # Loading Page
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)

        spinner = Gtk.Spinner()
        spinner.set_size_request(32, 32)
        spinner.start()
        loading_box.append(spinner)

        loading_label = Gtk.Label(label="Refreshing Library...")
        loading_label.add_css_class("caption")
        loading_box.append(loading_label)

        self.stack.add_named(loading_box, "loading")

        self.main_box.append(self.stack)
        self.set_child(self.main_box)

        # Load Library
        self.load_library()

        # Connect Player
        self.loading_row_spinner = None
        self.player.connect("state-changed", self.on_player_state_changed)

    def clear(self):
        """Clears all playlists from the UI."""
        print("Clearing LibraryPage playlists...")
        while row := self.playlists_list.get_row_at_index(0):
            self.playlists_list.remove(row)

    def load_library(self):
        if self._is_loading:
            return
        self._is_loading = True
        thread = threading.Thread(target=self._fetch_library)
        thread.daemon = True
        thread.start()

    def _fetch_library(self):
        try:
            # Only show loading UI if we have no data at all
            if self.playlists_list.get_row_at_index(0) is None:
                GLib.idle_add(self.stack.set_visible_child_name, "loading")

            playlists = self.client.get_library_playlists()
            artists = self.client.get_library_subscriptions()

            GObject.idle_add(self.update_playlists, playlists if playlists else [])
            GObject.idle_add(self.update_artists, artists if artists else [])
            GLib.idle_add(self.stack.set_visible_child_name, "root")
        finally:
            self._is_loading = False

    def update_playlists(self, playlists):
        # Sort: 2-letter IDs first (Automatic Playlists like LM, SE, etc.)
        def sort_key(p):
            pid = p.get("playlistId", "")
            return 0 if len(pid) == 2 else 1

        playlists.sort(key=sort_key)

        # 1. Map existing rows by playlist_id
        existing_rows = {}
        row = self.playlists_list.get_row_at_index(0)
        # ... (mapping logic remains same, but we can't easily skip lines in replacement without copying)
        # Let's just copy the mapping part briefly or assume it exists if I don't change it?
        # No, I must provide contiguous block.

        while row:
            if hasattr(row, "playlist_id"):
                existing_rows[row.playlist_id] = row
            row = row.get_next_sibling()

        processed_ids = set()

        for i, p in enumerate(playlists):
            p_id = p.get("playlistId")
            title = p.get("title", "Unknown")
            count = p.get("count")
            if not count:
                count = p.get("itemCount", "")

            thumbnails = p.get("thumbnails", [])
            thumb_url = thumbnails[-1]["url"] if thumbnails else None

            processed_ids.add(p_id)

            # Subtitle Logic
            subtitle = ""
            if len(p_id) == 2:
                subtitle = "Automatic Playlist"
                if count:
                    c_str = str(count)
                    if "songs" not in c_str:
                        c_str += " songs"
                    subtitle += f" • {c_str}"
            elif count:
                subtitle = f"{count} songs" if "songs" not in str(count) else str(count)

            row = existing_rows.get(p_id)

            if row:
                # Update existing
                box = row.get_child()
                if row.playlist_title != title:
                    row.playlist_title = title
                    box._title_label.set_label(title)

                box._subtitle_label.set_label(subtitle)
                row.playlist_count = count  # store raw count
                row.is_owned = self.client.is_own_playlist(p, playlist_id=p_id)

                # Image
                if hasattr(row, "cover_img"):
                    if row.cover_img.url != thumb_url:
                        row.cover_img.load_url(thumb_url)

                # Reordering
                current_idx = row.get_index()
                if current_idx != i:
                    self.playlists_list.remove(row)
                    self.playlists_list.insert(row, i)

            else:
                # Create New
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                box.add_css_class("song-row")
                row.set_child(box)

                from ui.utils import AsyncPicture

                img = AsyncPicture(url=thumb_url, target_size=44, crop_to_square=True)
                img.add_css_class("song-img")
                if not thumb_url:
                    img.set_from_icon_name("media-playlist-audio-symbolic")

                box.append(img)
                row.cover_img = img

                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                vbox.set_valign(Gtk.Align.CENTER)
                vbox.set_hexpand(True)

                title_label = Gtk.Label(label=title)
                title_label.set_halign(Gtk.Align.START)
                title_label.set_ellipsize(Pango.EllipsizeMode.END)
                title_label.set_lines(1)
                box._title_label = title_label

                subtitle_label = Gtk.Label(label=subtitle)
                subtitle_label.set_halign(Gtk.Align.START)
                subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
                subtitle_label.set_lines(1)
                subtitle_label.add_css_class("dim-label")
                subtitle_label.add_css_class("caption")
                box._subtitle_label = subtitle_label

                vbox.append(title_label)
                vbox.append(subtitle_label)
                box.append(vbox)

                row.playlist_id = p_id
                row.playlist_title = title
                row.playlist_count = count
                row.is_owned = self.client.is_own_playlist(p, playlist_id=p_id)
                row.set_activatable(True)

                # Context Menu
                gesture = Gtk.GestureClick()
                gesture.set_button(3)
                gesture.connect("released", self.on_row_right_click, row)
                row.add_controller(gesture)

                self.playlists_list.insert(row, i)

        # Identify and remove stale rows (those in existing_rows but not in processed_ids).
        # Moved widgets are kept safe by processed_ids check.
        for p_id, row in existing_rows.items():
            if p_id not in processed_ids:
                self.playlists_list.remove(row)

    def on_row_right_click(self, gesture, n_press, x, y, row):
        if not hasattr(row, "playlist_id"):
            return

        pid = row.playlist_id
        # Determine URL
        url = f"https://music.youtube.com/playlist?list={pid}"

        group = Gio.SimpleActionGroup()
        row.insert_action_group("row", group)

        def copy_link_action(action, param):
            try:
                clipboard = Gdk.Display.get_default().get_clipboard()
                clipboard.set(url)
            except Exception:
                pass

        action_copy = Gio.SimpleAction.new("copy_link", None)
        action_copy.connect("activate", copy_link_action)
        group.add_action(action_copy)

        menu = Gio.Menu()
        menu.append("Copy Link", "row.copy_link")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(row)
        popover.set_has_arrow(False)

        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)

        is_owned = getattr(row, "is_owned", False)
        if is_owned:
            menu.append("Delete Playlist", "row.delete_playlist")

            def delete_action(action, param):
                self._confirm_delete_playlist(row)

            action_delete = Gio.SimpleAction.new("delete_playlist", None)
            action_delete.connect("activate", delete_action)
            group.add_action(action_delete)

        popover.popup()

    def _confirm_delete_playlist(self, row):
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading="Delete Playlist?",
            body=f'Are you sure you want to delete "{row.playlist_title}"?\nThis action cannot be undone.',
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dg, response_id):
            if response_id == "delete":
                self._delete_playlist_confirmed(row)
            dg.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def _delete_playlist_confirmed(self, row):
        def thread_func():
            success = self.client.delete_playlist(row.playlist_id)
            if success:
                print(f"Playlist {row.playlist_id} deleted successfully.")
                GLib.idle_add(self.load_library)
            else:
                print(f"Failed to delete playlist {row.playlist_id}")

        threading.Thread(target=thread_func, daemon=True).start()

    def on_new_playlist_clicked(self, btn):
        dialog = Adw.Dialog()
        dialog.set_title("New Playlist")
        dialog.set_content_width(500)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dialog.set_child(main_box)

        header = Adw.HeaderBar()
        header.add_css_class("flat")
        main_box.append(header)

        create_btn = Gtk.Button(label="Create")
        create_btn.add_css_class("suggested-action")
        header.pack_start(create_btn)

        page = Adw.PreferencesPage()
        main_box.append(page)

        group = Adw.PreferencesGroup(title="Playlist Details")
        group.set_margin_start(12)
        group.set_margin_end(12)
        group.set_margin_top(12)
        group.set_margin_bottom(12)
        page.add(group)

        # Title
        title_row = Adw.EntryRow(title="Title")
        title_row.set_activates_default(True)
        group.add(title_row)

        # Description
        desc_row = Adw.EntryRow(title="Description")
        group.add(desc_row)

        # Privacy
        privacy_row = Adw.ComboRow(title="Visibility")
        privacy_options = ["Public", "Private", "Unlisted"]
        privacy_model = Gtk.StringList.new(privacy_options)
        privacy_row.set_model(privacy_model)
        privacy_row.set_selected(1)  # Private by default
        group.add(privacy_row)

        def on_create_clicked(button):
            title = title_row.get_text().strip()
            if not title:
                return

            description = desc_row.get_text().strip()
            privacy_idx = privacy_row.get_selected()
            privacy_status = ["PUBLIC", "PRIVATE", "UNLISTED"][privacy_idx]

            self._create_playlist_confirmed(title, description, privacy_status)
            dialog.close()

        create_btn.connect("clicked", on_create_clicked)
        dialog.present(self.get_root())
        title_row.grab_focus()

    def _create_playlist_confirmed(self, title, description, privacy_status):
        def thread_func():
            print(f"Creating playlist: {title}")
            playlist_id = self.client.create_playlist(
                title, description=description, privacy_status=privacy_status
            )

            if playlist_id:
                print(f"Playlist created successfully: {playlist_id}")
                # 1. Refresh library in background
                GLib.idle_add(self.load_library)

                # 2. Navigate to the new playlist immediately
                GLib.idle_add(
                    self.open_playlist_callback,
                    playlist_id,
                    {"title": title, "author": "You"},
                )
            else:
                print("Failed to create playlist.")

        threading.Thread(target=thread_func, daemon=True).start()

    def update_artists(self, artists):
        # 1. Map existing rows by browse_id
        existing_rows = {}
        row = self.artists_list.get_row_at_index(0)
        while row:
            if hasattr(row, "artist_id"):
                existing_rows[row.artist_id] = row
            row = row.get_next_sibling()

        processed_ids = set()

        for i, a in enumerate(artists):
            a_id = a.get("browseId")
            name = a.get("artist", "Unknown")
            subscribers = a.get("subscribers", "")
            if subscribers and "subscribers" not in subscribers.lower():
                subscribers = f"{subscribers} subscribers"

            thumbnails = a.get("thumbnails", [])
            thumb_url = thumbnails[-1]["url"] if thumbnails else None

            processed_ids.add(a_id)

            row = existing_rows.get(a_id)

            if row:
                # Update existing
                box = row.get_child()
                if row.artist_name != name:
                    row.artist_name = name
                    box._title_label.set_label(name)

                box._subtitle_label.set_label(subscribers)

                # Image
                if hasattr(row, "cover_img"):
                    if row.cover_img.url != thumb_url:
                        row.cover_img.load_url(thumb_url)

                # Reordering
                current_idx = row.get_index()
                if current_idx != i:
                    self.artists_list.remove(row)
                    self.artists_list.insert(row, i)

            else:
                # Create New
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                box.add_css_class("song-row")
                row.set_child(box)

                from ui.utils import AsyncPicture

                img = AsyncPicture(url=thumb_url, target_size=44, crop_to_square=True)
                img.add_css_class("song-img")
                if not thumb_url:
                    img.set_from_icon_name("avatar-default-symbolic")

                box.append(img)
                row.cover_img = img

                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                vbox.set_valign(Gtk.Align.CENTER)
                vbox.set_hexpand(True)

                title_label = Gtk.Label(label=name)
                title_label.set_halign(Gtk.Align.START)
                title_label.set_ellipsize(Pango.EllipsizeMode.END)
                title_label.set_lines(1)
                box._title_label = title_label

                subtitle_label = Gtk.Label(label=subscribers)
                subtitle_label.set_halign(Gtk.Align.START)
                subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
                subtitle_label.set_lines(1)
                subtitle_label.add_css_class("dim-label")
                subtitle_label.add_css_class("caption")
                box._subtitle_label = subtitle_label

                vbox.append(title_label)
                vbox.append(subtitle_label)
                box.append(vbox)

                row.artist_id = a_id
                row.artist_name = name
                row.set_activatable(True)

                self.artists_list.insert(row, i)

        # Remove stale
        for a_id, row in existing_rows.items():
            if a_id not in processed_ids:
                self.artists_list.remove(row)

    def on_artist_activated(self, box, row):
        if hasattr(row, "artist_id"):
            # The MainWindow has open_artist, but here we only have open_playlist_callback.
            # However, open_playlist_callback in MainWindow.init_pages is bound to self.open_playlist.
            # We might need a separate callback for artists or use the root window.
            root = self.get_root()
            if hasattr(root, "open_artist"):
                root.open_artist(row.artist_id, row.artist_name)

    def on_playlist_activated(self, box, row):
        if hasattr(row, "playlist_id"):
            initial_data = {
                "title": getattr(row, "playlist_title", None),
                "thumb": row.cover_img.url if hasattr(row, "cover_img") else None,
            }
            self.open_playlist_callback(row.playlist_id, initial_data)

    def on_player_state_changed(self, player, state):
        pass  # Not used currently for playlist list
