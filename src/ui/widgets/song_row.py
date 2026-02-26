import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GObject, GLib, Gdk, Gio
from ui.utils import AsyncImage, LikeButton


class SongRowWidget(Gtk.Box):
    def __init__(self, player, client):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.player = player
        self.client = client
        self.model_item = None

        self.row = Adw.ActionRow()
        self.row.set_hexpand(True)
        self.append(self.row)

        # Image
        self.img = AsyncImage(size=40)
        self.row.add_prefix(self.img)

        # Suffixes: Duration, Like
        self.dur_lbl = Gtk.Label()
        self.dur_lbl.add_css_class("caption")
        self.dur_lbl.set_valign(Gtk.Align.CENTER)
        self.dur_lbl.set_margin_end(6)
        self.row.add_suffix(self.dur_lbl)

        self.like_btn = LikeButton(self.client, None)
        self.row.add_suffix(self.like_btn)

        # Gesture for Right Click (Context Menu)
        gesture = Gtk.GestureClick()
        gesture.set_button(3)  # Right click
        gesture.connect("pressed", self.on_right_click)
        self.row.add_controller(gesture)

    def bind(self, item, page):
        self.model_item = item
        self.page = page

        self.row.set_title(GLib.markup_escape_text(item.title))
        self.row.set_subtitle(GLib.markup_escape_text(item.artist))
        self.row.set_title_lines(1)
        self.row.set_subtitle_lines(1)

        self.dur_lbl.set_label(item.duration)
        self.img.load_url(item.thumbnail_url)

        self.like_btn.set_data(item.video_id, item.like_status)

        if not item.video_id:
            self.row.set_sensitive(False)
            self.row.set_activatable(False)
        else:
            self.row.set_sensitive(True)
            self.row.set_activatable(True)

        if item.is_playing:
            self.row.add_css_class("playing")
        else:
            self.row.remove_css_class("playing")

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

        menu_model = Gio.Menu()
        if item.video_id:
            menu_model.append("Copy Link", "row.copy_link")

        artists = item.track_data.get("artists", [])
        if artists and artists[0].get("id"):
            menu_model.append("Go to Artist", "row.goto_artist")

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
