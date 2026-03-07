from gi.repository import Gtk, Adw, GLib, Gio, Pango, Gdk
import threading
import json
from api.client import MusicClient
from ui.utils import AsyncImage, parse_item_metadata


class DiscographyPage(Adw.Bin):
    def __init__(self, player, open_playlist_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.open_playlist_callback = open_playlist_callback
        self.client = MusicClient()
        self.channel_id = None
        self.browse_id = None
        self.params = None
        self.title = ""
        self.items = []
        self._is_loading = False
        self._has_more = True
        self._next_continuation = None

        # Main Layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header Bar removed because Adw.NavigationPage handles it

        # Scrolled Window
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_vexpand(True)

        vadjust = self.scrolled.get_vadjustment()
        vadjust.connect("value-changed", self._on_scroll)

        # Content Box
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.content_box.set_margin_top(24)
        self.content_box.set_margin_bottom(24)
        self.content_box.set_margin_start(24)
        self.content_box.set_margin_end(24)

        # FlowBox for Grid
        self.flow_box = Gtk.FlowBox()
        self.flow_box.set_valign(Gtk.Align.START)
        self.flow_box.set_max_children_per_line(5)
        self.flow_box.set_min_children_per_line(2)
        self.flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow_box.set_column_spacing(0)
        self.flow_box.set_row_spacing(0)
        self.flow_box.set_homogeneous(True)
        self.flow_box.set_activate_on_single_click(True)
        self.flow_box.connect("child-activated", self.on_grid_child_activated)

        self.content_box.append(self.flow_box)

        # Loading Spinner
        self.loading_spinner = Adw.Spinner()
        self.loading_spinner.set_halign(Gtk.Align.CENTER)
        self.loading_spinner.set_margin_top(16)
        self.loading_spinner.set_margin_bottom(16)
        self.loading_spinner.set_visible(False)
        self.content_box.append(self.loading_spinner)

        # Clamp for consistent width
        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(1024)
        self.clamp.set_tightening_threshold(600)
        self.clamp.set_child(self.content_box)

        self.scrolled.set_child(self.clamp)
        self.main_box.append(self.scrolled)

        self.set_child(self.main_box)

    def load_discography(
        self, channel_id, title, browse_id=None, params=None, initial_items=None
    ):
        self.channel_id = channel_id
        self.title = title
        self.browse_id = browse_id
        self.params = params

        # Clear existing items
        self.items = []
        child = self.flow_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.flow_box.remove(child)
            child = next_child

        self._has_more = True
        self._next_continuation = None

        if initial_items:
            self.items.extend(initial_items)
            self._render_items(initial_items)

        self._load_more()

    def _on_scroll(self, adjustment):
        if self._is_loading or not self._has_more:
            return

        value = adjustment.get_value()
        upper = adjustment.get_upper()
        page_size = adjustment.get_page_size()

        # Load more when we are near the bottom
        if upper - (value + page_size) < 200:
            self._load_more()

    def _load_more(self):
        if self._is_loading or not self._has_more:
            return

        self._is_loading = True
        self.loading_spinner.set_visible(True)

        def fetch_func():
            try:
                new_items = []
                if self.browse_id and "Top Songs" in self.title:
                    # Note: We likely won't use DiscographyPage for Top Songs since it's a list, not a grid
                    pass
                elif self.browse_id and self.params:
                    # For albums and singles
                    new_items = self.client.get_artist_albums(
                        self.browse_id, self.params, limit=100
                    )

                    if len(new_items) < 100:
                        self._has_more = False
                    else:
                        self._has_more = False
                elif self.browse_id and not self.params:
                    # For videos (which is a playlist)
                    res = self.client.get_playlist(self.browse_id)
                    new_items = res.get("tracks", [])
                    self._has_more = False

                def update_cb():
                    if new_items:
                        # Filter out items we already have
                        existing_ids = {
                            item.get("browseId")
                            for item in self.items
                            if item.get("browseId")
                        }
                        filtered_items = [
                            item
                            for item in new_items
                            if item.get("browseId") not in existing_ids
                        ]

                        self.items.extend(filtered_items)
                        self._render_items(filtered_items)

                    self._is_loading = False
                    self.loading_spinner.set_visible(False)

                    if not new_items:
                        self._has_more = False

                GLib.idle_add(update_cb)
            except Exception as e:
                print(f"Error loading discography: {e}")
                GLib.idle_add(lambda: self.loading_spinner.set_visible(False))
                self._is_loading = False

        threading.Thread(target=fetch_func, daemon=True).start()

    def _render_items(self, items):
        for item in items:
            thumb_url = (
                item.get("thumbnails", [])[-1]["url"]
                if item.get("thumbnails")
                else None
            )

            item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            item_box.item_data = item

            img = AsyncImage(url=thumb_url, size=140)

            wrapper = Gtk.Box()
            wrapper.set_overflow(Gtk.Overflow.HIDDEN)
            wrapper.add_css_class("card")
            wrapper.set_halign(Gtk.Align.CENTER)
            wrapper.append(img)

            item_box.append(wrapper)

            lbl = Gtk.Label(label=item.get("title", ""))
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lbl.set_lines(2)
            lbl.set_justify(Gtk.Justification.LEFT)
            lbl.set_halign(Gtk.Align.START)

            text_clamp = Adw.Clamp(maximum_size=140)
            text_clamp.set_child(lbl)
            item_box.append(text_clamp)

            # Subtitle (Year / Type / Explicit)
            meta = parse_item_metadata(item)
            parts = []
            if meta["year"]:
                parts.append(meta["year"])
            if meta["type"] and meta["type"].lower() not in [p.lower() for p in parts]:
                parts.append(meta["type"])

            subtitle_text = " • ".join(parts)

            subtitle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            subtitle_box.set_halign(Gtk.Align.START)

            if subtitle_text:
                subtitle_lbl = Gtk.Label(label=subtitle_text)
                subtitle_lbl.add_css_class("caption")
                subtitle_lbl.add_css_class("dim-label")
                subtitle_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                subtitle_box.append(subtitle_lbl)

            if meta["is_explicit"]:
                explicit_lbl = Gtk.Label(label="E")
                explicit_lbl.set_justify(Gtk.Justification.CENTER)
                explicit_lbl.set_halign(Gtk.Align.CENTER)
                explicit_lbl.add_css_class("explicit-badge")
                subtitle_box.append(explicit_lbl)

            if subtitle_text or meta["is_explicit"]:
                subtitle_clamp = Adw.Clamp(maximum_size=140)
                subtitle_clamp.set_child(subtitle_box)
                item_box.append(subtitle_clamp)

            self.flow_box.append(item_box)

            gesture = Gtk.GestureClick()
            gesture.set_button(3)
            gesture.connect("pressed", self.on_grid_right_click, item_box)
            item_box.add_controller(gesture)

    def on_grid_child_activated(self, flowbox, child):
        box = child.get_child()
        if not hasattr(box, "item_data"):
            return

        item = box.item_data
        browse_id = item.get("browseId")
        video_id = item.get("videoId")

        if browse_id:
            # Check if it's a playlist or album based on ID prefix or other metadata
            # Most albums/singles returned by get_artist_albums have a browseId starting with MPREb
            self.open_playlist_callback(browse_id)
        elif video_id:
            # It's a video!
            app = Gtk.Application.get_default()
            window = app.get_active_window()
            if window and hasattr(window, "player"):
                window.player.play_tracks([item])

    def on_grid_right_click(self, gesture, n_press, x, y, item_box):
        if not hasattr(item_box, "item_data"):
            return
        data = item_box.item_data
        group = Gio.SimpleActionGroup()
        item_box.insert_action_group("item", group)

        # Play Action
        play_action = Gio.SimpleAction.new("play", None)
        play_action.connect("activate", self._on_play_item, data)
        group.add_action(play_action)

        # Queue Action
        queue_action = Gio.SimpleAction.new("queue", None)
        queue_action.connect("activate", self._on_queue_item, data)
        group.add_action(queue_action)

        def copy_json_action(action, param):
            try:
                json_str = json.dumps(data, indent=2)
                clipboard = Gdk.Display.get_default().get_clipboard()
                clipboard.set(json_str)
            except Exception:
                pass

        action_json = Gio.SimpleAction.new("copy_json", None)
        action_json.connect("activate", copy_json_action)
        group.add_action(action_json)

        menu = Gio.Menu()
        menu.append("Play", "item.play")
        menu.append("Add to queue", "item.queue")
        menu.append("Copy JSON (Debug)", "item.copy_json")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(item_box)
        popover.set_has_arrow(False)
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.popup()

    def _on_play_item(self, action, param, data):
        app = Gtk.Application.get_default()
        window = app.get_active_window()
        if not window or not hasattr(window, "player"):
            return

        video_id = data.get("videoId")
        if video_id:
            GLib.idle_add(window.player.play_tracks, [data])
            return

        browse_id = data.get("browseId")
        if not browse_id:
            return

        # Play the album/single
        def thread_func():
            playlist_data = self.client.get_playlist(browse_id)
            tracks = playlist_data.get("tracks", [])
            if tracks:
                GLib.idle_add(window.player.play_tracks, tracks)

        threading.Thread(target=thread_func, daemon=True).start()

    def _on_queue_item(self, action, param, data):
        app = Gtk.Application.get_default()
        window = app.get_active_window()
        if not window or not hasattr(window, "player"):
            return

        video_id = data.get("videoId")
        if video_id:
            GLib.idle_add(window.player.extend_queue, [data])
            return

        browse_id = data.get("browseId")
        if not browse_id:
            return

        def thread_func():
            playlist_data = self.client.get_playlist(browse_id)
            tracks = playlist_data.get("tracks", [])
            if tracks:
                GLib.idle_add(window.player.extend_queue, tracks)

        threading.Thread(target=thread_func, daemon=True).start()
