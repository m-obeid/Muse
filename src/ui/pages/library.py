from gi.repository import Gtk, Adw, GObject, GLib, Gdk, Gio
import threading
from api.client import MusicClient


class LibraryPage(Adw.Bin):
    def __init__(self, player, open_playlist_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.client = MusicClient()
        self.open_playlist_callback = open_playlist_callback

        # We want a list, not just status page.
        # Let's use a Box with status page as placeholder if empty, else list.
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Scrolled Window for Playlists
        list_scrolled = Gtk.ScrolledWindow()
        list_scrolled.set_vexpand(True)
        list_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.playlists_list = Gtk.ListBox()
        self.playlists_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.playlists_list.add_css_class("boxed-list")
        self.playlists_list.set_margin_top(24)
        self.playlists_list.set_margin_bottom(24)
        self.playlists_list.set_margin_start(12)
        self.playlists_list.set_margin_end(12)
        self.playlists_list.connect("row-activated", self.on_playlist_activated)

        # Clamp
        list_clamp = Adw.Clamp()
        list_clamp.set_child(self.playlists_list)
        list_scrolled.set_child(list_clamp)

        self.list_box.append(list_scrolled)

        self.set_child(self.list_box)

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
        thread = threading.Thread(target=self._fetch_library)
        thread.daemon = True
        thread.start()

    def _fetch_library(self):
        playlists = self.client.get_library_playlists()
        full_list = playlists if playlists else []
        GObject.idle_add(self.update_playlists, full_list)

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
                if row.playlist_title != title:
                    row.set_title(GLib.markup_escape_text(title))
                    row.playlist_title = title

                # Always update subtitle if it changed?
                # or check against stored?
                # simpler to just set it.
                row.set_subtitle(GLib.markup_escape_text(subtitle))
                row.playlist_count = count  # store raw count

                # Image
                if hasattr(row, "cover_img"):
                    if row.cover_img.url != thumb_url:
                        try:
                            row.cover_img.load_url(thumb_url)
                        except:
                            pass

                # Reordering
                current_idx = row.get_index()
                if current_idx != i:
                    self.playlists_list.remove(row)
                    self.playlists_list.insert(row, i)

            else:
                # Create New
                row = Adw.ActionRow()
                row.set_title(GLib.markup_escape_text(title))
                row.set_property("title-lines", 1)
                row.set_subtitle(GLib.markup_escape_text(subtitle))
                row.set_property("subtitle-lines", 1)

                from ui.utils import AsyncImage

                img = AsyncImage(url=thumb_url, size=40)
                if not thumb_url:
                    img.set_from_icon_name("media-playlist-audio-symbolic")

                row.add_prefix(img)
                row.cover_img = img

                row.playlist_id = p_id
                row.playlist_title = title
                row.playlist_count = count
                row.set_activatable(True)

                row.playlist_count = count
                row.set_activatable(True)

                # Context Menu
                gesture = Gtk.GestureClick()
                gesture.set_button(3)
                gesture.connect("pressed", self.on_row_right_click, row)
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
            except:
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

        popover.popup()

    def on_playlist_activated(self, box, row):
        if hasattr(row, "playlist_id"):
            initial_data = {
                "title": getattr(row, "playlist_title", None),
                "thumb": row.cover_img.url if hasattr(row, "cover_img") else None,
            }
            self.open_playlist_callback(row.playlist_id, initial_data)

    def on_player_state_changed(self, player, state):
        pass  # Not used currently for playlist list
