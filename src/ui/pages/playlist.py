import threading
import re
import os
import tempfile
from gi.repository import Gtk, Adw, GObject, GLib, Pango, Gdk, Gio, GdkPixbuf
from api.client import MusicClient
from ui.utils import AsyncImage, LikeButton
from ui.crop_dialog import ImageCropDialog

# ── GObject Models ────────────────────────────────────────────────────────────


class HeaderItem(GObject.Object):
    __gtype_name__ = "HeaderItem"

    def __init__(self):
        super().__init__()


class TrackItem(GObject.Object):
    __gtype_name__ = "TrackItem"

    def __init__(self, data: dict):
        super().__init__()
        self.data = data


# ── Page ──────────────────────────────────────────────────────────────────────


class PlaylistPage(Adw.Bin):
    __gsignals__ = {
        "header-title-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }

    def __init__(self, player, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)
        self.client = MusicClient()
        self.playlist_id = None
        self.playlist_title_text = ""
        self.playlist_description_text = ""

        # ── 1. Header UI Container ────────────────────────────────────────────
        self.header_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header_container.set_margin_top(24)
        self.header_container.set_margin_bottom(12)

        self.header_info_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=24
        )
        self.header_info_box.set_valign(Gtk.Align.START)

        self.cover_img = AsyncImage(size=200)
        self.cover_img.set_valign(Gtk.Align.START)

        self.cover_wrapper = Gtk.Box()
        self.cover_wrapper.set_overflow(Gtk.Overflow.HIDDEN)
        self.cover_wrapper.add_css_class("rounded")
        self.cover_wrapper.set_valign(Gtk.Align.START)
        self.cover_wrapper.append(self.cover_img)
        self.header_info_box.append(self.cover_wrapper)

        cover_gesture = Gtk.GestureClick()
        cover_gesture.set_button(3)
        cover_gesture.connect("pressed", self.on_cover_right_click)
        self.cover_wrapper.add_controller(cover_gesture)

        self.details_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.details_col.set_valign(Gtk.Align.CENTER)
        self.details_col.set_hexpand(True)

        self.playlist_name_label = Gtk.Label(label="Playlist Title")
        self.playlist_name_label.add_css_class("title-1")
        self.playlist_name_label.set_wrap(True)
        self.playlist_name_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.playlist_name_label.set_justify(Gtk.Justification.LEFT)
        self.playlist_name_label.set_halign(Gtk.Align.START)
        self.playlist_name_label.set_vexpand(False)
        self.playlist_name_label.set_hexpand(True)
        self.playlist_name_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.playlist_name_label.set_lines(3)
        self.details_col.append(self.playlist_name_label)

        self.description_label = Gtk.Label(label="")
        self.description_label.add_css_class("body")
        self.description_label.set_wrap(True)
        self.description_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.description_label.set_justify(Gtk.Justification.LEFT)
        self.description_label.set_halign(Gtk.Align.START)
        self.description_label.set_vexpand(False)
        self.description_label.set_hexpand(True)
        self.description_label.set_visible(False)
        self.description_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.description_label.set_lines(3)
        self.details_col.append(self.description_label)

        self.meta_label = Gtk.Label(label="")
        self.meta_label.add_css_class("caption")
        self.meta_label.set_wrap(True)
        self.meta_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.meta_label.set_justify(Gtk.Justification.LEFT)
        self.meta_label.set_halign(Gtk.Align.START)
        self.meta_label.set_hexpand(True)
        self.meta_label.set_use_markup(True)
        self.meta_label.connect("activate-link", self.on_meta_link_activated)
        self.details_col.append(self.meta_label)

        self.stats_label = Gtk.Label(label="")
        self.stats_label.add_css_class("caption")
        self.stats_label.set_wrap(True)
        self.stats_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.stats_label.set_justify(Gtk.Justification.LEFT)
        self.stats_label.set_halign(Gtk.Align.START)
        self.stats_label.set_hexpand(True)
        self.details_col.append(self.stats_label)

        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions_box.set_margin_top(12)
        self.actions_box = actions_box

        play_btn = Gtk.Button(label="Play")
        play_btn.add_css_class("suggested-action")
        play_btn.add_css_class("pill")
        play_btn.connect("clicked", self.on_play_clicked)
        actions_box.append(play_btn)

        shuffle_btn = Gtk.Button()
        shuffle_btn.set_icon_name("media-playlist-shuffle-symbolic")
        shuffle_btn.add_css_class("circular")
        shuffle_btn.set_valign(Gtk.Align.CENTER)
        shuffle_btn.set_halign(Gtk.Align.CENTER)
        shuffle_btn.set_size_request(48, 48)
        shuffle_btn.connect("clicked", self.on_shuffle_clicked)
        actions_box.append(shuffle_btn)

        self.edit_btn = Gtk.Button()
        self.edit_btn.set_icon_name("document-edit-symbolic")
        self.edit_btn.add_css_class("circular")
        self.edit_btn.set_valign(Gtk.Align.CENTER)
        self.edit_btn.set_halign(Gtk.Align.CENTER)
        self.edit_btn.set_size_request(48, 48)
        self.edit_btn.set_visible(False)
        self.edit_btn.set_tooltip_text("Edit Playlist")
        self.edit_btn.connect("clicked", self.on_edit_clicked)
        actions_box.append(self.edit_btn)

        self.sort_dropdown = Gtk.DropDown.new_from_strings(
            ["Default", "Title (A-Z)", "Artist (A-Z)", "Album (A-Z)"]
        )
        self.sort_dropdown.set_valign(Gtk.Align.CENTER)
        self.sort_dropdown.add_css_class("pill")
        self.sort_dropdown.add_css_class("sort-dropdown")
        self.sort_dropdown.connect("notify::selected", self.on_sort_changed)

        self.details_col.append(actions_box)
        self.header_info_box.append(self.details_col)
        self.header_container.append(self.header_info_box)

        self.sort_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.sort_row.set_margin_top(12)
        self.sort_row.add_css_class("playlist-sort-row")
        self.sort_row.append(self.sort_dropdown)
        self.sort_row.set_visible(False)
        self.header_container.append(self.sort_row)

        self.empty_label = Gtk.Label(label="This playlist has no songs")
        self.empty_label.add_css_class("dim-label")
        self.empty_label.set_margin_top(24)
        self.empty_label.set_halign(Gtk.Align.CENTER)
        self.empty_label.set_visible(False)
        self.header_container.append(self.empty_label)

        self.content_spinner = Adw.Spinner()
        self.content_spinner.set_size_request(32, 32)
        self.content_spinner.set_halign(Gtk.Align.CENTER)
        self.content_spinner.set_margin_top(24)
        self.content_spinner.set_visible(False)
        self.header_container.append(self.content_spinner)

        # ── 2. Models ─────────────────────────────────────────────────────────
        self.header_store = Gio.ListStore(item_type=HeaderItem)
        self.header_store.append(HeaderItem())

        self.track_store = Gio.ListStore(item_type=TrackItem)
        self.track_filter = Gtk.CustomFilter.new(self._track_filter_func, None)
        self.filter_model = Gtk.FilterListModel.new(self.track_store, self.track_filter)

        self.master_store = Gio.ListStore(item_type=Gio.ListModel)
        self.master_store.append(self.header_store)
        self.master_store.append(self.filter_model)

        self.flatten_model = Gtk.FlattenListModel.new(self.master_store)
        self.selection_model = Gtk.SingleSelection.new(self.flatten_model)
        self.selection_model.set_autoselect(False)
        self.selection_model.set_can_unselect(True)

        # ── 3. List & ScrolledWindow ──────────────────────────────────────────
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup_list_item)
        factory.connect("bind", self._bind_list_item)
        factory.connect("unbind", self._unbind_list_item)
        factory.connect("teardown", self._teardown_list_item)

        self.songs_list = Gtk.ListView.new(self.selection_model, factory)
        self.songs_list.add_css_class("playlist-view")
        self.songs_list.set_single_click_activate(True)
        self.songs_list.connect("activate", self.on_song_activated)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self.vadjust = scrolled.get_vadjustment()
        self.vadjust.connect("value-changed", self._on_scroll)

        clamp = (
            Adw.ClampScrollable() if hasattr(Adw, "ClampScrollable") else Adw.Clamp()
        )
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(600)

        # Apply padding directly to the ListView so it remains Gtk.Scrollable
        self.songs_list.set_margin_start(12)
        self.songs_list.set_margin_end(12)
        self.songs_list.set_margin_bottom(0)

        # The ListView MUST be the direct child of the ClampScrollable
        clamp.set_child(self.songs_list)
        scrolled.set_child(clamp)

        # ── 4. Main & Page Stack ──────────────────────────────────────────────
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.main_box.append(scrolled)

        self.load_more_spinner = Adw.Spinner()
        self.load_more_spinner.set_size_request(24, 24)
        self.load_more_spinner.set_halign(Gtk.Align.CENTER)
        self.load_more_spinner.set_margin_top(12)
        self.load_more_spinner.set_margin_bottom(12)
        self.load_more_spinner.set_visible(False)
        self.main_box.append(self.load_more_spinner)

        self.stack = Adw.ViewStack()
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        self.spinner = Adw.Spinner()
        self.spinner.set_size_request(32, 32)
        loading_box.append(self.spinner)
        loading_label = Gtk.Label(label="Loading Playlist...")
        loading_label.add_css_class("title-2")
        loading_box.append(loading_label)

        self.stack.add_named(loading_box, "loading")
        self.stack.add_named(self.main_box, "content")
        self.set_child(self.stack)

        self.current_tracks = []
        self.current_limit = 50
        self.is_loading_more = False
        self.current_filter_text = ""

    # ── Factory callbacks ─────────────────────────────────────────────────────

    def _setup_list_item(self, factory, list_item):
        bin_widget = Adw.Bin()
        list_item.set_child(bin_widget)

        row = Adw.ActionRow()
        row.set_activatable(False)
        row.set_title_lines(1)
        row.set_subtitle_lines(1)

        img = AsyncImage(size=40)
        row.add_prefix(img)
        row._lv_img = img

        dur_lbl = Gtk.Label()
        dur_lbl.add_css_class("caption")
        dur_lbl.set_valign(Gtk.Align.CENTER)
        dur_lbl.set_margin_end(6)
        row.add_suffix(dur_lbl)
        row._lv_dur_lbl = dur_lbl

        like_box = Gtk.Box()
        like_box.set_valign(Gtk.Align.CENTER)
        row.add_suffix(like_box)
        row._lv_like_box = like_box

        gesture = Gtk.GestureClick()
        gesture.set_button(3)
        gesture.connect("pressed", self._on_row_right_click_gesture)
        row.add_controller(gesture)

        row._lv_video_data = None
        row._lv_full_track = None

        bin_widget._lv_track_ui = row

    def _bind_list_item(self, factory, list_item):
        bin_widget = list_item.get_child()
        item = list_item.get_item()
        if not item:
            return

        if type(item).__name__ == "HeaderItem":
            list_item.set_selectable(False)
            list_item.set_activatable(False)
            bin_widget.set_child(self.header_container)
            return

        bin_widget.set_child(bin_widget._lv_track_ui)
        list_item.set_selectable(True)
        list_item.set_activatable(True)

        row = bin_widget._lv_track_ui
        t = item.data

        title = t.get("title", "Unknown")
        artist_list = t.get("artists", [])
        artist = ", ".join(a.get("name", "") for a in artist_list)

        row.set_title(GLib.markup_escape_text(title))
        row.set_subtitle(GLib.markup_escape_text(artist))

        thumbnails = t.get("thumbnails", [])
        thumb_url = thumbnails[-1]["url"] if thumbnails else None
        if thumb_url:
            if row._lv_img.url != thumb_url:
                row._lv_img.load_url(thumb_url)
        else:
            row._lv_img.set_from_icon_name("media-optical-symbolic")
            row._lv_img.url = None

        dur_sec = t.get("duration_seconds")
        dur_text = (
            f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec else t.get("duration", "")
        )
        row._lv_dur_lbl.set_label(dur_text or "")
        row._lv_dur_lbl.set_visible(bool(dur_text))

        _clear_box(row._lv_like_box)
        if t.get("videoId"):
            like_btn = LikeButton(
                self.client, t["videoId"], t.get("likeStatus", "INDIFFERENT")
            )
            row._lv_like_box.append(like_btn)

        has_id = bool(t.get("videoId"))
        list_item.set_activatable(has_id)
        list_item.set_selectable(has_id)
        bin_widget.set_sensitive(has_id)

        row._lv_video_data = {
            "id": t.get("videoId"),
            "title": title,
            "artist": artist,
            "thumb": thumb_url,
            "setVideoId": t.get("setVideoId") or t.get("playlistId"),
        }
        row._lv_full_track = t

    def _unbind_list_item(self, factory, list_item):
        bin_widget = list_item.get_child()
        item = list_item.get_item()
        if not item:
            return

        if type(item).__name__ == "HeaderItem":
            bin_widget.set_child(None)
            return

        row = bin_widget._lv_track_ui
        row.set_title("")
        row.set_subtitle("")
        row._lv_img.set_from_icon_name("media-optical-symbolic")
        row._lv_img.url = None
        row._lv_dur_lbl.set_label("")
        row._lv_dur_lbl.set_visible(False)
        _clear_box(row._lv_like_box)
        row._lv_video_data = None
        row._lv_full_track = None

    def _teardown_list_item(self, factory, list_item):
        list_item.set_child(None)

    # ── Filter ────────────────────────────────────────────────────────────────

    def _track_filter_func(self, item, _user_data):
        if not self.current_filter_text:
            return True
        t = item.data
        title = t.get("title", "").lower()
        artist = ", ".join(a.get("name", "") for a in t.get("artists", [])).lower()
        return self.current_filter_text in title or self.current_filter_text in artist

    def filter_content(self, text):
        self.current_filter_text = text.lower().strip()
        self.track_filter.changed(Gtk.FilterChange.DIFFERENT)

    # ── Store helpers ─────────────────────────────────────────────────────────

    def _add_track_row(self, t):
        self.track_store.append(TrackItem(t))

    def _clear_track_store(self):
        self.track_store.remove_all()

    # ── Scroll / lazy load ────────────────────────────────────────────────────

    def _on_scroll(self, vadjust):
        val = vadjust.get_value()

        # Absolute position check for Window Title
        if val <= 50:
            self.emit("header-title-changed", "")
        else:
            self.emit("header-title-changed", self.playlist_title_text)

        max_val = vadjust.get_upper() - vadjust.get_page_size()
        if max_val > 0 and val >= max_val - 200:
            if (
                not self.is_loading_more
                and self.playlist_id
                and not getattr(self, "is_fully_loaded", False)
            ):
                self.load_more()

    def load_more(self):
        if getattr(self, "is_fully_fetched", False) and hasattr(
            self, "original_tracks"
        ):
            if len(self.current_tracks) < len(self.original_tracks):
                self.is_loading_more = True
                self.load_more_spinner.set_visible(True)

                start_index = len(self.current_tracks)
                end_index = min(start_index + 50, len(self.original_tracks))
                new_tracks = self.original_tracks[start_index:end_index]
                self.current_tracks.extend(new_tracks)

                if self.sort_dropdown.get_selected() != 0:
                    self.reorder_playlist(self.sort_dropdown.get_selected())
                else:
                    for t in new_tracks:
                        self._add_track_row(t)

                self.load_more_spinner.set_visible(False)
                self.is_loading_more = False
                return

        if getattr(self, "is_fully_loaded", False):
            return

        self.is_loading_more = True
        self.load_more_spinner.set_visible(True)
        self.current_limit = len(self.current_tracks) + 50
        print(f"Loading more... Limit now {self.current_limit}")

        thread = threading.Thread(
            target=self._fetch_playlist_details, args=(self.playlist_id, True)
        )
        thread.daemon = True
        thread.start()

    def _on_map(self, widget):
        if hasattr(self, "vadjust"):
            if self.vadjust.get_value() > 50:
                self.emit("header-title-changed", self.playlist_title_text)
            else:
                self.emit("header-title-changed", "")

    def _on_unmap(self, widget):
        self.emit("header-title-changed", "")

    # ── Load playlist ─────────────────────────────────────────────────────────

    def load_playlist(self, playlist_id, initial_data=None):
        if self.playlist_id != playlist_id:
            self.playlist_id = playlist_id
            self.playlist_title_text = ""
            self.current_limit = 50
            self.emit("header-title-changed", "")
            self.current_tracks = []
            self._clear_track_store()

        if initial_data:
            self.playlist_title_text = initial_data.get("title", "")
            self.playlist_name_label.set_label(self.playlist_title_text)
            self.description_label.set_label("")

            author = initial_data.get("author")
            if author and author != "Unknown":
                self.meta_label.set_label(f"{author} • Loading tracks...")
            else:
                self.meta_label.set_label("Loading tracks...")

            thumb = initial_data.get("thumb")
            if thumb:
                if self.cover_img.url != thumb:
                    self.cover_img.set_from_icon_name("media-playlist-audio-symbolic")
                    self.cover_img.load_url(thumb)
            else:
                self.cover_img.set_from_icon_name("media-playlist-audio-symbolic")
                self.cover_img.url = None

            self.stack.set_visible_child_name("content")
            self.content_spinner.set_visible(True)
        else:
            cached_tracks = self.client.get_cached_playlist_tracks(self.playlist_id)
            if cached_tracks is not None:
                print(
                    f"Loading playlist {playlist_id} from cache ({len(cached_tracks)} tracks)"
                )
                self.is_fully_loaded = True
                self.original_tracks = list(cached_tracks)
                self.current_tracks = list(cached_tracks)
                thread = threading.Thread(
                    target=self._fetch_playlist_details, args=(playlist_id,)
                )
                thread.daemon = True
                thread.start()
                return

            if self.stack.get_visible_child_name() != "content":
                self.stack.set_visible_child_name("loading")
                self.playlist_name_label.set_label("Loading...")
                self.description_label.set_label("")
                self.meta_label.set_label("")
                self.cover_img.set_from_icon_name("media-playlist-audio-symbolic")
                self.cover_img.url = None
                self.content_spinner.set_visible(True)
            else:
                self.content_spinner.set_visible(False)

        thread = threading.Thread(
            target=self._fetch_playlist_details, args=(playlist_id,)
        )
        thread.daemon = True
        thread.start()

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def _fetch_playlist_details(self, playlist_id, is_incremental=False):
        try:
            if playlist_id.startswith("OLAK"):
                try:
                    new_id = self.client.get_album_browse_id(playlist_id)
                    if new_id:
                        print(f"Converted {playlist_id} to {new_id}")
                        playlist_id = new_id
                except Exception as e:
                    print(f"Error converting OLAK to browseId: {e}")

            count_str = None
            album_type = None

            if playlist_id == "LM":
                data = self.client.get_liked_songs(limit=self.current_limit)
                title = "Your Likes"
                description = "Your liked songs from YouTube Music."
                tracks = data.get("tracks", []) if isinstance(data, dict) else data
                track_count = (
                    data.get("trackCount", len(tracks))
                    if isinstance(data, dict)
                    else len(tracks)
                )
                song_text = "song" if track_count == 1 else "songs"
                count_str = f"{track_count} {song_text}"
                year = None
                author = "You"
                thumbnails = []
                if tracks:
                    first = tracks[0]
                    if first.get("thumbnails"):
                        thumbnails = first.get("thumbnails")
                        new_thumbs = []
                        for t in thumbnails:
                            if "url" in t:
                                nt = t.copy()
                                nt["url"] = re.sub(r"w\d+-h\d+", "w544-h544", t["url"])
                                new_thumbs.append(nt)
                        if new_thumbs:
                            thumbnails = new_thumbs

            elif playlist_id.startswith("MPRE"):
                try:
                    data = self.client.get_album(playlist_id)
                    title = data.get("title", "Unknown Album")
                    description = data.get("description", "")
                    tracks = data.get("tracks", [])
                    thumbnails = data.get("thumbnails", [])
                    track_count = data.get("trackCount", len(tracks))
                    year = data.get("year", "")

                    if track_count == 1:
                        album_type = "Single"
                    elif 2 <= track_count <= 6:
                        album_type = "EP"
                    else:
                        album_type = "Album"

                    meta_parts = [album_type]
                    if year:
                        meta_parts.append(str(year))
                    song_text = "song" if track_count == 1 else "songs"
                    count_str = f"{track_count} {song_text}"
                    meta_parts.append(count_str)
                    count = " • ".join(meta_parts)

                    artist_data = data.get("artists", [])
                    if isinstance(artist_data, list):
                        parts = []
                        for a in artist_data:
                            name = GLib.markup_escape_text(a.get("name", "Unknown"))
                            aid = a.get("id")
                            parts.append(
                                f"<a href='artist:{aid}'>{name}</a>" if aid else name
                            )
                        author = ", ".join(parts)
                    else:
                        author = GLib.markup_escape_text(str(artist_data))

                    if thumbnails:
                        for t in thumbnails:
                            if "url" in t:
                                t["url"] = re.sub(r"w\d+-h\d+", "w544-h544", t["url"])
                        for track in tracks:
                            if not track.get("thumbnails"):
                                track["thumbnails"] = thumbnails
                except Exception as e:
                    print(f"Error fetching album details: {e}")
                    return
            else:
                try:
                    print(
                        f"Fetching playlist: {playlist_id} (Limit: {self.current_limit})"
                    )
                    data = self.client.get_playlist(
                        playlist_id, limit=self.current_limit
                    )
                    title = data.get("title", "Unknown Playlist")
                    description = data.get("description", "")
                    tracks = data.get("tracks", [])
                    thumbnails = data.get("thumbnails", [])

                    track_count = data.get("trackCount")
                    if track_count is None:
                        song_text = "Infinite"
                        count_str = "Infinite"
                    else:
                        song_text = "song" if track_count == 1 else "songs"
                        count_str = f"{track_count} {song_text}"

                    meta_parts = []
                    privacy = data.get("privacy")
                    if privacy:
                        meta_parts.append(privacy.capitalize())
                    year = data.get("year")
                    if year:
                        meta_parts.append(str(year))
                    meta_parts.append(count_str)
                    duration = data.get("duration")
                    if duration:
                        meta_parts.append(duration)
                    count = " • ".join(meta_parts)

                    author_data = data.get("author")
                    if isinstance(author_data, list):
                        parts = []
                        for a in author_data:
                            name = GLib.markup_escape_text(a.get("name", ""))
                            aid = a.get("id")
                            parts.append(
                                f"<a href='artist:{aid}'>{name}</a>" if aid else name
                            )
                        author = ", ".join(parts)
                    elif isinstance(author_data, dict):
                        name = GLib.markup_escape_text(
                            author_data.get("name", "Unknown")
                        )
                        aid = author_data.get("id")
                        author = f"<a href='artist:{aid}'>{name}</a>" if aid else name
                    else:
                        author = (
                            GLib.markup_escape_text(str(author_data))
                            if author_data
                            else "Unknown"
                        )

                    if "Unknown" in author and not author.startswith("<a"):
                        collab = data.get("collaborators")
                        if collab and isinstance(collab, dict):
                            text = collab.get("text", "")
                            if text:
                                clean = text[3:] if text.startswith("by ") else text
                                author = GLib.markup_escape_text(clean)
                except Exception as e:
                    print(f"Error processing playlists: {e}")
                    data = {}
                    title = "Error Loading Playlist"
                    description = str(e)
                    tracks = []
                    thumbnails = []
                    author = "Error"
                    track_count = 0
                    song_text = "songs"
                    count_str = "0 songs"

            total_seconds = 0
            if "duration_seconds" in data:
                total_seconds = data.get("duration_seconds")
            elif tracks and "track_count" in locals() and track_count is not None:
                total_seconds = sum(t.get("duration_seconds", 0) for t in tracks)

            if total_seconds and total_seconds > 0:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                duration_str = (
                    f"{hours} hr {minutes} min"
                    if hours > 0
                    else f"{minutes} min {seconds} sec"
                )
            else:
                duration_str = data.get("duration", "")

            meta1_parts = []
            if playlist_id.startswith("MPRE") or playlist_id.startswith("OLAK"):
                meta1_parts.append(album_type)
            else:
                privacy = data.get("privacy")
                meta1_parts.append(privacy.capitalize() if privacy else "Playlist")
            if year:
                meta1_parts.append(str(year))
            if author:
                meta1_parts.append(author)
            meta1 = " • ".join(meta1_parts)

            meta2_parts = []
            if count_str:
                meta2_parts.append(count_str)
            else:
                if "track_count" in locals() and track_count is None:
                    meta2_parts.append("Infinite")
                else:
                    meta2_parts.append(
                        f"{locals().get('track_count', 0)} {locals().get('song_text', 'songs')}"
                    )
            if duration_str:
                meta2_parts.append(duration_str)
            meta2 = " • ".join(meta2_parts)

            GObject.idle_add(
                self.update_ui,
                title,
                description,
                meta1,
                meta2,
                thumbnails,
                tracks,
                is_incremental,
                track_count,
            )

            if (
                not is_incremental
                and track_count is not None
                and len(tracks) < track_count
            ):
                if not self.playlist_id.startswith(
                    "MPRE"
                ) and not self.playlist_id.startswith("OLAK"):
                    self._start_background_full_fetch()

        except Exception as e:
            print(f"Critical error fetching playlist: {e}")
            self.is_loading_more = False
            GObject.idle_add(self.load_more_spinner.set_visible, False)

    # ── Update UI ─────────────────────────────────────────────────────────────

    def update_ui(
        self,
        title,
        description,
        meta1,
        meta2,
        thumbnails,
        tracks,
        append=False,
        total_tracks=None,
    ):
        self.stack.set_visible_child_name("content")
        self.content_spinner.set_visible(False)

        self.playlist_title_text = title
        self.playlist_description_text = description
        self.playlist_name_label.set_label(title)

        if description:
            self.description_label.set_label(description)
            self.description_label.set_visible(True)
        else:
            self.description_label.set_visible(False)

        self.meta_label.set_markup(meta1)
        self.stats_label.set_label(meta2)

        is_album = self.playlist_id and (
            self.playlist_id.startswith("MPRE") or self.playlist_id.startswith("OLAK")
        )
        has_tracks = bool(tracks)

        self.empty_label.set_visible(not has_tracks)
        self.sort_row.set_visible(has_tracks and not is_album)

        # Show edit button if it's an owned playlist
        is_editable = (
            self.client.is_authenticated() and not is_album and self.playlist_id != "LM"
        )
        # We can further check for 'privacy' in data to confirm ownership
        # In ytmusicapi, 'privacy' is usually only returned for owned playlists, obviously.
        self.edit_btn.set_visible(is_editable)

        if thumbnails and not append:
            url = thumbnails[-1]["url"]
            if self.cover_img.url != url:
                self.cover_img.load_url(url)
        elif not thumbnails and not self.cover_img.url:
            self.cover_img.set_from_icon_name("media-playlist-audio-symbolic")
            self.cover_img.url = None

        if append:
            start_index = len(self.current_tracks)
            new_tracks = tracks[start_index:]

            if not new_tracks:
                print("No new tracks found. Playlist fully loaded.")
                self.is_fully_loaded = True
                self.load_more_spinner.set_visible(False)
                self.is_loading_more = False
                return

            print(f"Appending {len(new_tracks)} new tracks (Total: {len(tracks)})")
            self.current_tracks.extend(new_tracks)
            if hasattr(self, "original_tracks"):
                self.original_tracks.extend(new_tracks)

            if self.sort_dropdown.get_selected() != 0:
                self.reorder_playlist(self.sort_dropdown.get_selected())
            else:
                for t in new_tracks:
                    self._add_track_row(t)

            self.load_more_spinner.set_visible(False)
            self.is_loading_more = False

            if len(tracks) < self.current_limit:
                print(
                    f"Playlist fully loaded ({len(tracks)} < limit {self.current_limit})"
                )
                self.is_fully_loaded = True
            elif total_tracks is not None and len(tracks) >= total_tracks:
                print(f"Playlist fully loaded ({len(tracks)} >= total {total_tracks})")
                self.is_fully_loaded = True
        else:
            self.is_fully_loaded = False
            if total_tracks is not None and len(tracks) >= total_tracks:
                self.is_fully_loaded = True
                self.is_fully_fetched = True
                self.client.set_cached_playlist_tracks(self.playlist_id, tracks)

            self.current_tracks = list(tracks)
            if not hasattr(self, "original_tracks") or not self.original_tracks:
                self.original_tracks = list(tracks)
            self.sort_dropdown.set_selected(0)

            self._clear_track_store()
            for t in tracks:
                self._add_track_row(t)

        if len(self.current_tracks) > 0 and len(self.current_tracks) == len(
            getattr(self, "original_tracks", [])
        ):
            self.is_fully_fetched = True

    # ── Background fetch ──────────────────────────────────────────────────────

    def _start_background_full_fetch(self):
        if getattr(self, "is_fully_fetched", False):
            return
        print(f"Starting background fetch for full playlist: {self.playlist_id}")

        def fetch_job():
            try:
                data = self.client.get_playlist(self.playlist_id, limit=5000)
                tracks = data.get("tracks", [])
                if tracks:
                    print(f"Background fetch complete. Fetched {len(tracks)} tracks.")
                    self.original_tracks = tracks
                    self.client.set_cached_playlist_tracks(self.playlist_id, tracks)
                    GObject.idle_add(self._on_background_fetch_complete)
            except Exception as e:
                print(f"Error in background fetch: {e}")

        self._is_background_fetching = True
        self._pending_queue_append = False
        thread = threading.Thread(target=fetch_job)
        thread.daemon = True
        thread.start()

    def _on_background_fetch_complete(self):
        self.is_fully_fetched = True
        self._is_background_fetching = False

        if self.sort_dropdown.get_selected() != 0:
            self.current_tracks = list(self.original_tracks)
            self.reorder_playlist(self.sort_dropdown.get_selected())

        if getattr(self, "_pending_queue_append", False):
            print("Background fetch complete, extending player queue.")
            start_index = len(self.current_tracks)
            new_tracks = self.original_tracks[start_index:]
            if new_tracks:
                self.player.extend_queue(new_tracks)
            self._pending_queue_append = False

    # ── Song activation ───────────────────────────────────────────────────────

    def on_song_activated(self, listview, position):
        item = self.flatten_model.get_item(position)
        if item is None or type(item).__name__ == "HeaderItem":
            return

        t = item.data
        if not t.get("videoId"):
            return

        tracks_to_queue = self._best_queue()
        start_index = 0
        for i, track in enumerate(tracks_to_queue):
            if track.get("videoId") == t.get("videoId"):
                start_index = i
                break

        print(
            f"\033[94m[DEBUG-PLAYLIST] on_song_activated. playlist_id={self.playlist_id}\033[0m"
        )
        self.player.set_queue(
            tracks_to_queue,
            start_index,
            source_id=self.playlist_id,
            is_infinite=self._is_inf(),
        )
        if getattr(self, "_is_background_fetching", False):
            self._pending_queue_append = True

    # ── Sort ──────────────────────────────────────────────────────────────────

    def on_sort_changed(self, dropdown, pspec):
        self.reorder_playlist(dropdown.get_selected())

    def reorder_playlist(self, sort_type):
        if not self.current_tracks:
            return

        if sort_type == 0:
            if hasattr(self, "original_tracks"):
                self.current_tracks = list(self.original_tracks)
            else:
                return
        elif sort_type == 1:
            self.current_tracks.sort(key=lambda x: x.get("title", "").lower())
        elif sort_type == 2:
            self.current_tracks.sort(
                key=lambda x: (
                    x.get("artists", [{}])[0].get("name", "").lower()
                    if x.get("artists")
                    else "",
                    x.get("title", "").lower(),
                )
            )
        elif sort_type == 3:
            self.current_tracks.sort(
                key=lambda x: (
                    x.get("album", {}).get("name", "").lower()
                    if isinstance(x.get("album"), dict)
                    else str(x.get("album") or "").lower(),
                    x.get("title", "").lower(),
                )
            )

        self._clear_track_store()
        for t in self.current_tracks:
            self._add_track_row(t)

    # ── Right-click ───────────────────────────────────────────────────────────

    def _on_row_right_click_gesture(self, gesture, n_press, x, y):
        row = gesture.get_widget()
        if not hasattr(row, "_lv_video_data") or row._lv_video_data is None:
            return

        data = row._lv_video_data
        full_track_data = row._lv_full_track

        group = Gio.SimpleActionGroup()
        row.insert_action_group("row", group)

        def copy_link_action(action, param):
            vid = data.get("id")
            if vid:
                clipboard = Gdk.Display.get_default().get_clipboard()
                clipboard.set(f"https://music.youtube.com/watch?v={vid}")

        def goto_artist_action(action, param):
            if full_track_data and "artists" in full_track_data:
                artist = full_track_data["artists"][0]
                aid = artist.get("id")
                name = artist.get("name")
                if aid:
                    root = self.get_root()
                    if hasattr(root, "open_artist"):
                        root.open_artist(aid, name)

        for name, cb in [
            ("copy_link", copy_link_action),
            ("goto_artist", goto_artist_action),
        ]:
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", cb)
            group.add_action(a)

        menu_model = Gio.Menu()
        if data.get("id"):
            menu_model.append("Copy Link", "row.copy_link")
        if (
            full_track_data
            and "artists" in full_track_data
            and full_track_data["artists"][0].get("id")
        ):
            menu_model.append("Go to Artist", "row.goto_artist")

        if menu_model.get_n_items() > 0:
            popover = Gtk.PopoverMenu.new_from_model(menu_model)
            popover.set_parent(row)
            popover.set_has_arrow(False)
            rect = Gdk.Rectangle()
            rect.x = int(x)
            rect.y = int(y)
            rect.width = 1
            rect.height = 1
            popover.set_pointing_to(rect)
            popover.popup()

    # ── Meta link ─────────────────────────────────────────────────────────────

    def on_meta_link_activated(self, label, uri):
        if uri.startswith("artist:"):
            aid = uri.split(":", 1)[1]
            root = self.get_root()
            if hasattr(root, "open_artist"):
                root.open_artist(aid, "Artist")
            return True
        return False

    # ── Play / Shuffle ────────────────────────────────────────────────────────

    def on_play_clicked(self, btn):
        if not self.current_tracks:
            return
        print(
            f"\033[94m[DEBUG-PLAYLIST] on_play_clicked. playlist_id={self.playlist_id}\033[0m"
        )
        self.player.set_queue(
            self._best_queue(),
            0,
            shuffle=False,
            source_id=self.playlist_id,
            is_infinite=self._is_inf(),
        )
        if getattr(self, "_is_background_fetching", False):
            self._pending_queue_append = True

    def on_shuffle_clicked(self, btn):
        if not self.current_tracks:
            return
        print(
            f"\033[94m[DEBUG-PLAYLIST] on_shuffle_clicked. playlist_id={self.playlist_id}\033[0m"
        )
        self.player.set_queue(
            self._best_queue(),
            -1,
            shuffle=True,
            source_id=self.playlist_id,
            is_infinite=self._is_inf(),
        )
        if getattr(self, "_is_background_fetching", False):
            self._pending_queue_append = True

    def _best_queue(self):
        if (
            getattr(self, "is_fully_fetched", False)
            and hasattr(self, "original_tracks")
            and self.sort_dropdown.get_selected() == 0
        ):
            return self.original_tracks
        return self.current_tracks

    def _is_inf(self):
        return bool(
            self.playlist_id
            and (
                self.playlist_id.startswith("RD") or self.playlist_id.startswith("VLRD")
            )
        )

    # ── Edit Playlist ─────────────────────────────────────────────────────────

    def on_edit_clicked(self, btn):
        self._show_edit_dialog()

    def on_cover_right_click(self, gesture, n_press, x, y):
        if self.edit_btn.get_visible():
            self._show_edit_dialog()

    def _show_edit_dialog(self):
        dialog = Adw.Dialog()
        dialog.set_title("Edit Playlist")
        dialog.set_content_width(500)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dialog.set_child(main_box)

        header = Adw.HeaderBar()
        header.add_css_class("flat")
        main_box.append(header)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        header.pack_start(save_btn)

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
        title_row.set_text(self.playlist_title_text)
        group.add(title_row)

        # Description
        desc_row = Adw.EntryRow(title="Description")
        desc_row.set_text(self.playlist_description_text)
        group.add(desc_row)

        # Cover Art
        cover_row = Adw.ActionRow(title="Playlist Cover")
        cover_row.set_subtitle("No file selected")
        group.add(cover_row)

        self._selected_cover_path = None

        def on_choose_file_clicked(btn):
            file_dialog = Gtk.FileDialog(title="Select Cover Image")
            filter_img = Gtk.FileFilter()
            filter_img.set_name("Images")
            filter_img.add_mime_type("image/jpeg")
            filter_img.add_mime_type("image/png")

            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(filter_img)
            file_dialog.set_filters(filters)

            def on_file_selected(dialog_inner, result):
                try:
                    file = dialog_inner.open_finish(result)
                    if file:
                        path = file.get_path()
                        # Load pixbuf
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)

                        # Open crop dialog
                        crop_dg = ImageCropDialog(self.get_root(), pixbuf)

                        def on_crop_response(dg, response_id):
                            if response_id == Gtk.ResponseType.OK:
                                result_pixbuf = dg.result_pixbuf
                                if result_pixbuf:
                                    # Save to temp file as PNG
                                    temp_dir = tempfile.gettempdir()
                                    temp_path = os.path.join(
                                        temp_dir, f"mixtape_crop_{os.getpid()}.png"
                                    )
                                    result_pixbuf.savev(temp_path, "png", [], [])

                                    self._selected_cover_path = temp_path
                                    cover_row.set_subtitle(
                                        f"Cropped PNG: {file.get_basename()}"
                                    )

                        crop_dg.connect("response", on_crop_response)
                        crop_dg.present()
                except Exception as e:
                    print(f"Error selecting or cropping file: {e}")

            # Use the actual application window as parent
            parent = self.get_root()
            if not isinstance(parent, Gtk.Window):
                parent = self.get_native()

            file_dialog.open(parent, None, on_file_selected)

        choose_btn = Gtk.Button(label="Choose File...")
        choose_btn.set_valign(Gtk.Align.CENTER)
        choose_btn.connect("clicked", on_choose_file_clicked)
        cover_row.add_suffix(choose_btn)

        def on_save_clicked(btn):
            new_title = title_row.get_text()
            new_desc = desc_row.get_text()
            img_path = getattr(self, "_selected_cover_path", None)

            # Store original values for the background job comparison
            old_title = self.playlist_title_text
            old_desc = self.playlist_description_text

            # Optimistic UI Update
            self.playlist_name_label.set_label(new_title)
            self.playlist_title_text = new_title
            if new_desc:
                self.description_label.set_label(new_desc)
                self.description_label.set_visible(True)
            else:
                self.description_label.set_visible(False)

            self.playlist_description_text = new_desc

            if img_path:
                print(f"Optimistically showing local image: {img_path}")
                self.cover_img.set_from_file(Gio.File.new_for_path(img_path))

            def save_job():
                try:
                    # 1. Update Metadata
                    # Strip to avoid whitespace-only differences
                    clean_title = new_title.strip()
                    clean_desc = new_desc.strip()

                    if (
                        clean_title != old_title.strip()
                        or clean_desc != old_desc.strip()
                    ):
                        print(f"DEBUG: Updating playlist metadata: '{clean_title}'")
                        success = self.client.edit_playlist(
                            self.playlist_id, title=clean_title, description=clean_desc
                        )
                        print(f"DEBUG: Metadata update success: {success}")

                    # 2. Update Image
                    if img_path:
                        print(f"DEBUG: Updating playlist thumbnail with {img_path}")
                        success = self.client.set_playlist_thumbnail(
                            self.playlist_id, img_path
                        )
                        print(f"DEBUG: Thumbnail update success: {success}")

                    # Refresh
                    # Clear cache and then reload
                    if hasattr(self.client, "_playlist_cache"):
                        if self.playlist_id in self.client._playlist_cache:
                            del self.client._playlist_cache[self.playlist_id]

                    GLib.idle_add(self.load_playlist, self.playlist_id)

                    # Update Library View if it exists
                    root = self.get_root()
                    if hasattr(root, "library_page"):
                        GLib.idle_add(root.library_page.load_library)
                except Exception as e:
                    import traceback

                    print(f"CRITICAL: Error in save_job thread: {e}")
                    traceback.print_exc()

            thread = threading.Thread(target=save_job, name="PlaylistSaveThread")
            thread.daemon = True
            thread.start()
            dialog.close()

        save_btn.connect("clicked", on_save_clicked)
        dialog.present(self.get_native())

    def _fetch_remaining_for_queue(self):
        if getattr(self, "is_fully_fetched", False):
            return
        print("Fetching remaining tracks for queue...")

        def fetch_job():
            try:
                existing_count = len(self.current_tracks)
                data = self.client.get_playlist(self.playlist_id, limit=5000)
                tracks = data.get("tracks", [])
                if len(tracks) > existing_count:
                    new_raw = tracks[existing_count:]
                    normalized = []
                    for t in new_raw:
                        artist = ", ".join(
                            a.get("name", "") for a in t.get("artists", [])
                        )
                        normalized.append(
                            {
                                "videoId": t.get("videoId"),
                                "title": t.get("title"),
                                "artist": artist,
                                "thumb": t.get("thumbnails", [])[-1]["url"]
                                if t.get("thumbnails")
                                else None,
                            }
                        )
                    if normalized:
                        GObject.idle_add(self.player.extend_queue, normalized)
                else:
                    print("DEBUG: No new tracks found.")
            except Exception as e:
                print(f"Error fetching remaining tracks: {e}")

        thread = threading.Thread(target=fetch_job)
        thread.daemon = True
        thread.start()

    # ── Compact mode ──────────────────────────────────────────────────────────

    def set_compact_mode(self, compact):
        if compact:
            self.header_info_box.set_orientation(Gtk.Orientation.VERTICAL)
            self.header_info_box.set_halign(Gtk.Align.CENTER)
            self.cover_wrapper.set_halign(Gtk.Align.CENTER)
            self.details_col.set_halign(Gtk.Align.CENTER)
            self.playlist_name_label.set_halign(Gtk.Align.CENTER)
            self.playlist_name_label.set_justify(Gtk.Justification.CENTER)
            self.description_label.set_halign(Gtk.Align.CENTER)
            self.description_label.set_justify(Gtk.Justification.CENTER)
            self.meta_label.set_halign(Gtk.Align.CENTER)
            self.stats_label.set_halign(Gtk.Align.CENTER)
            self.actions_box.set_halign(Gtk.Align.CENTER)
        else:
            self.header_info_box.set_orientation(Gtk.Orientation.HORIZONTAL)
            self.header_info_box.set_halign(Gtk.Align.START)
            self.cover_wrapper.set_halign(Gtk.Align.START)
            self.details_col.set_halign(Gtk.Align.FILL)
            self.playlist_name_label.set_halign(Gtk.Align.START)
            self.playlist_name_label.set_justify(Gtk.Justification.LEFT)
            self.description_label.set_halign(Gtk.Align.START)
            self.description_label.set_justify(Gtk.Justification.LEFT)
            self.meta_label.set_halign(Gtk.Align.START)
            self.stats_label.set_halign(Gtk.Align.START)
            self.actions_box.set_halign(Gtk.Align.START)


# ── Utility ───────────────────────────────────────────────────────────────────


def _clear_box(box: Gtk.Box):
    child = box.get_first_child()
    while child:
        nxt = child.get_next_sibling()
        box.remove(child)
        child = nxt
