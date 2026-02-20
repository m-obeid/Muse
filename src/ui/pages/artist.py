from gi.repository import Gtk, Adw, GObject, GLib, Pango, Gdk, Gio
import threading
from api.client import MusicClient
from ui.utils import AsyncImage, AsyncPicture

class ArtistPage(Adw.Bin):
    __gsignals__ = {
        'header-title-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }

    def __init__(self, player, open_playlist_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.open_playlist_callback = open_playlist_callback
        self.client = MusicClient()
        self.channel_id = None
        self.artist_name = ""
        self.current_songs = []
        
        # Main Layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Content Scrolled Window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        
        # Monitor scroll for title
        vadjust = scrolled.get_vadjustment()
        self.vadjust = vadjust
        vadjust.connect("value-changed", self._on_scroll)
        
        # Main Clamp
        self.clamp = Adw.Clamp()
        
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0) 
        content_box.set_margin_bottom(24)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        self.content_box = content_box
        
        # 1. Header Info (Banner Style)
        self.banner_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.banner_container.set_vexpand(False)
        self.banner_container.set_hexpand(True)
        self.banner_container.set_size_request(-1, 260) 
        
        # Banner Image
        self.avatar = AsyncPicture() 
        self.avatar.set_hexpand(True)
        self.avatar.set_vexpand(True) 
        self.avatar.set_halign(Gtk.Align.FILL)
        self.avatar.set_valign(Gtk.Align.FILL)
        self.avatar.set_content_fit(Gtk.ContentFit.COVER)
        
        self.banner_wrapper = Gtk.Box()
        self.banner_wrapper.set_overflow(Gtk.Overflow.HIDDEN)
        self.banner_wrapper.add_css_class("card")
        self.banner_wrapper.set_hexpand(True)
        self.banner_wrapper.set_vexpand(True)
        self.banner_wrapper.append(self.avatar)
        
        self.banner_container.append(self.banner_wrapper)
        content_box.append(self.banner_container)
        
        # Info Box
        self.info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.info_box.set_margin_top(24)
        self.info_box.set_margin_start(12)
        self.info_box.set_margin_end(12)
        
        self.name_label = Gtk.Label(label="Artist Name")
        self.name_label.add_css_class("title-1") 
        self.name_label.set_halign(Gtk.Align.START)
        self.info_box.append(self.name_label)
        
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.subscribers_label = Gtk.Label(label="")
        self.subscribers_label.add_css_class("title-4")
        self.subscribers_label.set_opacity(0.8)
        stats_box.append(self.subscribers_label)
        self.info_box.append(stats_box)
        
        self.description_label = Gtk.Label(label="")
        self.description_label.add_css_class("body")
        self.description_label.set_wrap(True)
        self.description_label.set_max_width_chars(80)
        self.description_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.description_label.set_lines(3)
        self.description_label.set_halign(Gtk.Align.START)
        self.info_box.append(self.description_label)
        
        # Actions
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.shuffle_btn = Gtk.Button(label="Shuffle")
        self.shuffle_btn.add_css_class("suggested-action")
        self.shuffle_btn.add_css_class("pill")
        self.shuffle_btn.connect("clicked", self.on_shuffle_clicked)
        actions.append(self.shuffle_btn)
        
        self.subscribe_btn = Gtk.Button(label="Subscribe")
        self.subscribe_btn.add_css_class("pill")
        actions.append(self.subscribe_btn)
        
        self.info_box.append(actions)
        content_box.append(self.info_box)
        
        # 2. Sections
        self.sections_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=32)
        self.sections_box.set_margin_top(12)
        content_box.append(self.sections_box)
        
        self.clamp.set_child(content_box)
        scrolled.set_child(self.clamp)
        self.main_box.append(scrolled)
        
        # Stack for Loading vs Content
        self.stack = Adw.ViewStack()
        
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        
        self.spinner = Adw.Spinner()
        loading_box.append(self.spinner)
        
        self.stack.add_named(loading_box, "loading")
        self.stack.add_named(self.main_box, "content")
        
        self.set_child(self.stack)    

    def load_artist(self, channel_id, initial_name=None):
        self.channel_id = channel_id
        if initial_name:
            self.artist_name = initial_name
            self.name_label.set_label(initial_name)
        
        self.stack.set_visible_child_name("loading")
        
        thread = threading.Thread(target=self._fetch_artist, args=(channel_id,))
        thread.daemon = True
        thread.start()

    def _fetch_artist(self, channel_id):
        try:
            data = self.client.get_artist(channel_id)
            GObject.idle_add(self.update_ui, data)
        except Exception as e:
            print(f"Error fetching artist: {e}")

    def update_ui(self, data):
        if not data:
            return
            
        self.stack.set_visible_child_name("content")
        
        # Header
        self.artist_name = data.get('name') or 'Unknown Artist'
        self.name_label.set_label(self.artist_name)
        self.description_label.set_label(data.get('description') or '')
        
        subs = data.get('subscribers') or ''
        if subs:
            subs += " Subscribers"
        
        views = data.get('views') 
        if views:
            if subs:
                subs += " • " + views
            else:
                subs = views
                
        self.subscribers_label.set_label(subs)
        
        thumbnails = data.get('thumbnails', [])
        if thumbnails:
            self.avatar.load_url(thumbnails[-1]['url'])
            
        # Clear Sections
        child = self.sections_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.sections_box.remove(child)
            child = next_child
            
        # Songs
        if 'songs' in data and data['songs'].get('results'):
            self.add_songs_section("Top Songs", data['songs']['results'])
            
        # Albums
        if 'albums' in data and data['albums'].get('results'):
            self.add_grid_section("Albums", data['albums']['results'])
            
        # Singles
        if 'singles' in data and data['singles'].get('results'):
            self.add_grid_section("Singles", data['singles']['results'])
            
        # Videos
        if 'videos' in data and data['videos'].get('results'):
             self.add_grid_section("Videos", data['videos']['results'])

    def add_songs_section(self, title, items):
        self.current_songs = items # Store for queue
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        
        label = Gtk.Label(label=title)
        label.add_css_class("heading")
        label.set_halign(Gtk.Align.START)
        box.append(label)
        
        list_box = Gtk.ListBox()
        list_box.add_css_class("boxed-list")
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.connect("row-activated", self.on_song_activated)
        
        for item in items[:5]: # Top 5
            row = Adw.ActionRow()
            row.set_activatable(True)
            
            song_title = item.get('title', 'Unknown')
            row.set_title(GLib.markup_escape_text(song_title))
            
            album_name = item.get('album', {}).get('name') if isinstance(item.get('album'), dict) else item.get('album')
            if album_name == song_title:
                album_name = "Single"
            
            row.set_subtitle(GLib.markup_escape_text(album_name or ''))
            
            thumbnails = item.get('thumbnails', [])
            thumb_url = thumbnails[-1]['url'] if thumbnails else None
            
            img = AsyncImage(url=thumb_url, size=40)
            if not thumb_url:
                 img.set_from_icon_name("media-optical-symbolic")
            row.add_prefix(img)
            
            row.item_data = item
            list_box.append(row)
            
        box.append(list_box)
        self.sections_box.append(box)

    def add_grid_section(self, title, items):
        if not items:
            return
            
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        
        label = Gtk.Label(label=title)
        label.add_css_class("heading")
        label.set_halign(Gtk.Align.START)
        box.append(label)
        
        flow_box = Gtk.FlowBox()
        flow_box.set_valign(Gtk.Align.START)
        flow_box.set_max_children_per_line(5) 
        flow_box.set_min_children_per_line(2)
        flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        flow_box.set_column_spacing(0) 
        flow_box.set_row_spacing(0)
        flow_box.set_homogeneous(True)
        flow_box.set_activate_on_single_click(True)
        flow_box.connect("child-activated", self.on_grid_child_activated)
        
        for item in items[:10]:
            thumb_url = item.get('thumbnails', [])[-1]['url'] if item.get('thumbnails') else None
            
            item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            item_box.item_data = item
            
            img = AsyncImage(url=thumb_url, size=140)
            
            wrapper = Gtk.Box()
            wrapper.set_overflow(Gtk.Overflow.HIDDEN)
            wrapper.add_css_class("card") 
            wrapper.set_halign(Gtk.Align.CENTER)
            wrapper.append(img)
            
            item_box.append(wrapper)
            
            lbl = Gtk.Label(label=item.get('title', ''))
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_max_width_chars(20) 
            lbl.set_wrap(True)
            lbl.set_lines(2)
            lbl.set_justify(Gtk.Justification.CENTER)
            item_box.append(lbl)
            
            flow_box.append(item_box)
            
            gesture = Gtk.GestureClick()
            gesture.set_button(3)
            gesture.connect("pressed", self.on_grid_right_click, item_box)
            item_box.add_controller(gesture)
            
        box.append(flow_box)
        self.sections_box.append(box)

    def on_grid_right_click(self, gesture, n_press, x, y, item_box):
        if not hasattr(item_box, 'item_data'):
            return
        data = item_box.item_data
        group = Gio.SimpleActionGroup()
        item_box.insert_action_group("item", group)
        
        url = None
        if 'videoId' in data:
            url = f"https://music.youtube.com/watch?v={data['videoId']}"
        elif 'audioPlaylistId' in data:
             url = f"https://music.youtube.com/playlist?list={data['audioPlaylistId']}"
        elif 'browseId' in data:
             bid = data['browseId']
             if bid.startswith("MPRE") or bid.startswith("OLAK"): 
                 url = f"https://music.youtube.com/playlist?list={bid}"
             else:
                 url = f"https://music.youtube.com/browse/{bid}"
        elif 'playlistId' in data:
             url = f"https://music.youtube.com/playlist?list={data['playlistId']}"
             
        def copy_link_action(action, param):
            if url:
                try:
                    clipboard = Gdk.Display.get_default().get_clipboard()
                    clipboard.set(url)
                except: pass
                
        action_copy = Gio.SimpleAction.new("copy_link", None)
        action_copy.connect("activate", copy_link_action)
        group.add_action(action_copy)
        
        menu = Gio.Menu()
        if url:
            menu.append("Copy Link", "item.copy_link")
            
        if menu.get_n_items() > 0:
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

    def on_song_activated(self, listbox, row):
        data = getattr(row, 'item_data', None)
        if not data:
            return

        if 'videoId' in data:
            if hasattr(self, 'current_songs') and self.current_songs:
                 start_index = 0
                 for i, song in enumerate(self.current_songs):
                     if song.get('videoId') == data.get('videoId'):
                         start_index = i
                         break
                 
                 queue_tracks = []
                 for song in self.current_songs:
                     artist_name = ", ".join([a.get('name', '') for a in song.get('artists', [])])
                     thumb = song.get('thumbnails', [])[-1]['url'] if song.get('thumbnails') else None
                     queue_tracks.append({
                         'videoId': song.get('videoId'),
                         'title': song.get('title'),
                         'artist': artist_name,
                         'thumb': thumb
                     })
                 self.player.set_queue(queue_tracks, start_index)
            else:
                 print(f"DEBUG: 'current_songs' missing on {self}. Data: {data}")
                 artist_name = ", ".join([a.get('name', '') for a in data.get('artists', [])])
                 thumb = data.get('thumbnails', [])[-1]['url'] if data.get('thumbnails') else None
                 self.player.load_video(data['videoId'], data.get('title'), artist_name, thumb)
        else:
            print("No videoId in song data", data)

    def on_grid_child_activated(self, flowbox, child):
        item_box = child.get_child()
        if hasattr(item_box, 'item_data'):
            data = item_box.item_data
            if 'videoId' in data:
                thumb = data.get('thumbnails', [])[-1]['url'] if data.get('thumbnails') else None
                self.player.load_video(data['videoId'], data.get('title'), self.artist_name, thumb)
            elif 'browseId' in data:
                 self.open_playlist_callback(data['browseId'], {
                     'title': data.get('title'),
                     'thumb': data.get('thumbnails', [])[-1]['url'] if data.get('thumbnails') else None,
                     'author': self.artist_name
                 })

    def on_shuffle_clicked(self, btn):
        if hasattr(self, 'current_songs') and self.current_songs:
            queue_tracks = []
            for song in self.current_songs:
                artist_name = ", ".join([a.get('name', '') for a in song.get('artists', [])])
                thumb = song.get('thumbnails', [])[-1]['url'] if song.get('thumbnails') else None
                queue_tracks.append({
                    'videoId': song.get('videoId'),
                    'title': song.get('title'),
                    'artist': artist_name,
                    'thumb': thumb
                })
            self.player.set_queue(queue_tracks, -1, shuffle=True)

    def _on_scroll(self, vadjust):
        if vadjust.get_value() > 100:
            self.emit('header-title-changed', self.artist_name)
        else:
            self.emit('header-title-changed', "")
