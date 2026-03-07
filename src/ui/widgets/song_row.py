import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import threading
from gi.repository import Gtk, Adw, GLib, Gdk, Gio, Pango
from ui.utils import AsyncPicture, LikeButton


class SongRowWidget(Gtk.Box):
    def __init__(self, player, client):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.player = player
        self.client = client
        self.model_item = None
        self._notify_handler_id = None
        self._player_handler_id = None
        self._start_x = 0
        self._start_y = 0

        self.row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.row.set_hexpand(True)
        self.row.add_css_class("song-row")
        self.append(self.row)

        # Image with playing indicator overlay
        self.img = AsyncPicture(crop_to_square=True, target_size=44)
        self.img.add_css_class("song-img")

        self.img_overlay = Gtk.Overlay()
        self.img_overlay.set_child(self.img)
        self.img_overlay.set_valign(Gtk.Align.CENTER)

        # Track number label (for album view)
        self.track_num_label = Gtk.Label()
        self.track_num_label.add_css_class("dim-label")
        self.track_num_label.add_css_class("caption")
        self.track_num_label.set_valign(Gtk.Align.CENTER)
        self.track_num_label.set_halign(Gtk.Align.CENTER)
        self.track_num_label.set_size_request(40, 40)
        self.track_num_label.set_visible(False)

        # Playing indicator: 3 animated bars
        self.playing_indicator = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.playing_indicator.set_halign(Gtk.Align.CENTER)
        self.playing_indicator.set_valign(Gtk.Align.CENTER)
        self.playing_indicator.add_css_class("playing-indicator")
        self.playing_indicator.set_visible(False)

        self.bar1 = Gtk.Box()
        self.bar1.add_css_class("playing-bar")
        self.bar1.add_css_class("playing-bar-1")
        self.bar2 = Gtk.Box()
        self.bar2.add_css_class("playing-bar")
        self.bar2.add_css_class("playing-bar-2")
        self.bar3 = Gtk.Box()
        self.bar3.add_css_class("playing-bar")
        self.bar3.add_css_class("playing-bar-3")

        self.playing_indicator.append(self.bar1)
        self.playing_indicator.append(self.bar2)
        self.playing_indicator.append(self.bar3)

        self._anim_timer_id = None
        self._anim_state = False

        self.img_overlay.add_overlay(self.playing_indicator)
        self.row.append(self.track_num_label)
        self.row.append(self.img_overlay)

        # Main Title / Subtitle Box
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.vbox.set_valign(Gtk.Align.CENTER)
        self.vbox.set_hexpand(True)

        self.title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.title_label = Gtk.Label()
        self.title_label.set_halign(Gtk.Align.START)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_lines(1)

        self.explicit_badge = Gtk.Label(label="E")
        self.explicit_badge.add_css_class("explicit-badge")
        self.explicit_badge.set_valign(Gtk.Align.CENTER)
        self.explicit_badge.set_visible(False)

        self.title_box.append(self.title_label)
        self.title_box.append(self.explicit_badge)

        self.subtitle_label = Gtk.Label()
        self.subtitle_label.set_halign(Gtk.Align.START)
        self.subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.subtitle_label.set_lines(1)
        self.subtitle_label.add_css_class("dim-label")
        self.subtitle_label.add_css_class("caption")

        self.vbox.append(self.title_box)
        self.vbox.append(self.subtitle_label)
        self.row.append(self.vbox)

        # Suffixes: Duration, Like

        self.dur_lbl = Gtk.Label()
        self.dur_lbl.add_css_class("caption")
        self.dur_lbl.set_valign(Gtk.Align.CENTER)
        self.dur_lbl.set_margin_end(6)
        self.row.append(self.dur_lbl)

        self.like_btn = LikeButton(self.client, None)
        self.like_btn.set_valign(Gtk.Align.CENTER)
        self.row.append(self.like_btn)

        # Gesture for Right Click (Context Menu)
        gesture = Gtk.GestureClick()
        gesture.set_button(3)  # Right click
        gesture.connect("released", self.on_right_click)
        self.row.add_controller(gesture)

        # Gesture for Left Click (Activation)
        left_click = Gtk.GestureClick()
        left_click.set_button(1)
        left_click.connect("pressed", self._on_left_pressed)
        left_click.connect("released", self._on_left_released)
        self.row.add_controller(left_click)

    def bind(self, item, page):
        print(f"[SONG-ROW-BIND] binding vid={item.video_id} title={item.title}")
        # Disconnect previous player signal handler
        if self._player_handler_id is not None:
            self.player.disconnect(self._player_handler_id)
            self._player_handler_id = None
        # Disconnect previous item notify handler
        if self._notify_handler_id is not None and self.model_item is not None:
            try:
                self.model_item.disconnect(self._notify_handler_id)
            except Exception:
                pass
            self._notify_handler_id = None

        self.model_item = item
        self.page = page

        self.title_label.set_label(item.title)
        self.title_label.set_tooltip_text(item.title)
        self.subtitle_label.set_label(item.artist)
        self.subtitle_label.set_tooltip_text(item.artist)

        self.dur_lbl.set_label(item.duration)
        self.explicit_badge.set_visible(item.is_explicit)

        # Check if this is an album view
        from ui.pages.album import AlbumPage

        is_album = isinstance(page, AlbumPage)

        if is_album:
            # Show track number instead of thumbnail
            self.track_num_label.set_label(str(item.index + 1))
            self.track_num_label.set_visible(True)
            self.img_overlay.set_visible(False)
        else:
            self.track_num_label.set_visible(False)
            self.img_overlay.set_visible(True)
            self.img.load_url(item.thumbnail_url)

        self.like_btn.set_data(item.video_id, item.like_status)

        if not item.video_id:
            self.row.set_sensitive(False)
        else:
            self.row.set_sensitive(True)

        # CSS handles responsiveness and size limits natively now

        # Set initial playing state based on current player state
        self._apply_playing_state(
            bool(item.video_id and item.video_id == self.player.current_video_id)
        )

        # Connect directly to the player metadata signal (reliable than GObject property notify)
        self._player_handler_id = self.player.connect(
            "metadata-changed", self._on_player_metadata_changed
        )

    def _on_player_metadata_changed(self, player, *args):
        print(
            f"[SONG-ROW-META] handler called, my_vid={self.model_item.video_id if self.model_item else None} player_vid={player.current_video_id}"
        )
        if self.model_item:
            is_playing = bool(
                self.model_item.video_id
                and self.model_item.video_id == player.current_video_id
            )
            if is_playing:
                print(
                    f"[PLAYING-INDICATOR] match! vid={self.model_item.video_id} player={player.current_video_id}"
                )
            self._apply_playing_state(is_playing)

    def stop_handlers(self):
        """Disconnect all signal handlers. Called on factory unbind."""
        if self._player_handler_id is not None:
            try:
                self.player.disconnect(self._player_handler_id)
            except Exception:
                pass
            self._player_handler_id = None
        if self._notify_handler_id is not None and self.model_item is not None:
            try:
                self.model_item.disconnect(self._notify_handler_id)
            except Exception:
                pass
            self._notify_handler_id = None
        self._stop_animation()

    def _apply_playing_state(self, is_playing):
        if is_playing:
            print(
                f"[PLAYING-INDICATOR] Applying PLAYING state to row: {self.model_item.title if self.model_item else '?'}"
            )
            self.row.add_css_class("playing")
            self.playing_indicator.set_visible(True)
            self._start_animation()
        else:
            self.row.remove_css_class("playing")
            self.playing_indicator.set_visible(False)
            self._stop_animation()

    def _start_animation(self):
        if self._anim_timer_id is not None:
            return  # Already running
        self._anim_state = False
        self._anim_timer_id = GLib.timeout_add(350, self._tick_animation)

    def _stop_animation(self):
        if self._anim_timer_id is not None:
            GLib.source_remove(self._anim_timer_id)
            self._anim_timer_id = None
        # Reset bars to default state
        self.bar1.remove_css_class("bar-up")
        self.bar2.remove_css_class("bar-up")
        self.bar3.remove_css_class("bar-up")

    def _tick_animation(self):
        self._anim_state = not self._anim_state
        if self._anim_state:
            self.bar1.add_css_class("bar-up")
            self.bar3.add_css_class("bar-up")
            self.bar2.remove_css_class("bar-up")
        else:
            self.bar2.add_css_class("bar-up")
            self.bar1.remove_css_class("bar-up")
            self.bar3.remove_css_class("bar-up")
        return GLib.SOURCE_CONTINUE

    def _on_left_pressed(self, gesture, n_press, x, y):
        self._start_x = x
        self._start_y = y

    def _on_left_released(self, gesture, n_press, x, y):
        # Displacement check
        dx = abs(x - self._start_x)
        dy = abs(y - self._start_y)
        if dx > 10 or dy > 10:
            return

        if self.model_item and self.page:
            # Trigger page activation logic
            if hasattr(self.page, "on_song_activated"):
                # We need the position in the model.
                # In Gtk.ListView, the widget doesn't know its' own position easily
                # but we stored it in model_item.index when creating SongItem
                self.page.on_song_activated(None, self.model_item.index)

    def on_right_click(self, gesture, n_press, x, y):
        if not self.model_item:
            return

        item = self.model_item
        group = Gio.SimpleActionGroup()
        self.row.insert_action_group("row", group)

        # Copy Link
        def copy_link_action(action, param):
            vid = item.video_id
            if vid:
                url = f"https://music.youtube.com/watch?v={vid}"
                clipboard = Gdk.Display.get_default().get_clipboard()
                clipboard.set(url)
                self._show_toast("Link copied to clipboard")

        def goto_artist_action(action, param):
            # We need to find the artist ID. It's in item.track_data
            artists = item.track_data.get("artists", [])
            if artists:
                artist = artists[0]
                aid = artist.get("id")
                name = artist.get("name")
                if aid:
                    root = self.get_root()
                    if hasattr(root, "open_artist"):
                        root.open_artist(aid, name)

        action_copy = Gio.SimpleAction.new("copy_link", None)
        action_copy.connect("activate", copy_link_action)
        group.add_action(action_copy)

        action_goto = Gio.SimpleAction.new("goto_artist", None)
        action_goto.connect("activate", goto_artist_action)
        group.add_action(action_goto)

        # Add to Playlist
        def add_to_playlist_action(action, param):
            target_pid = param.get_string()
            target_vid = item.video_id
            if target_pid and target_vid:

                def thread_func():
                    success = self.client.add_playlist_items(target_pid, [target_vid])
                    if success:
                        msg = "Added track to playlist"
                        print(msg)
                        GLib.idle_add(self._show_toast, msg)
                    else:
                        GLib.idle_add(self._show_toast, "Failed to add track")

                threading.Thread(target=thread_func, daemon=True).start()

        action_add = Gio.SimpleAction.new("add_to_playlist", GLib.VariantType.new("s"))
        action_add.connect("activate", add_to_playlist_action)
        group.add_action(action_add)

        menu_model = Gio.Menu()
        if item.video_id:
            menu_model.append("Copy Link", "row.copy_link")

        artists = item.track_data.get("artists", [])
        if artists and artists[0].get("id"):
            menu_model.append("Go to Artist", "row.goto_artist")

        # Add to Playlist Submenu
        if item.video_id:
            playlists = self.client.get_editable_playlists()
            if playlists:
                playlist_menu = Gio.Menu()
                for p in playlists:
                    p_title = p.get("title", "Unknown Playlist")
                    p_id = p.get("playlistId")
                    if p_id:
                        # Add action with parameter
                        playlist_menu.append(p_title, f"row.add_to_playlist('{p_id}')")
                menu_model.append_submenu("Add to Playlist", playlist_menu)

        if menu_model.get_n_items() > 0:
            popover = Gtk.PopoverMenu.new_from_model(menu_model)
            popover.set_parent(self.row)
            popover.set_has_arrow(False)

            rect = Gdk.Rectangle()
            rect.x = int(x)
            rect.y = int(y)
            rect.width = 1
            rect.height = 1
            popover.set_pointing_to(rect)

            popover.popup()

    def _show_toast(self, message):
        root = self.get_root()
        if hasattr(root, "add_toast"):
            root.add_toast(message)
