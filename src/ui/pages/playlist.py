from gi.repository import Gtk, Adw, GObject, GLib, Pango, Gdk, Gio
import threading
import re
from api.client import MusicClient
from ui.utils import AsyncImage

class PlaylistPage(Adw.Bin):
    __gsignals__ = {
        'header-title-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }

    def __init__(self, player, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)
        self.client = MusicClient()
        self.playlist_id = None
        self.playlist_title_text = ""
        
        # Main Layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Content Scrolled Window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        
        scrolled.set_vexpand(True)
        
        # Monitor scroll for title
        vadjust = scrolled.get_vadjustment()
        self.vadjust = vadjust # Save for map check
        vadjust.connect("value-changed", self._on_scroll)
        
        # Clamp for content
        clamp = Adw.Clamp()
        
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content_box.set_margin_top(24)
        content_box.set_margin_bottom(24)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        
        # Stack wrapper for main content to allow switching layouts or just use Box
        # We use a box directly.
        
        self.main_content_box = content_box
        
        # 1. Header Info (Cover + Details)
        self.header_info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        self.header_info_box.set_valign(Gtk.Align.START)
        
        # Cover Art
        self.cover_img = AsyncImage(size=200) # Large cover
        self.cover_img.set_valign(Gtk.Align.START)
        
        # Wrapper for rounding
        self.cover_wrapper = Gtk.Box()
        self.cover_wrapper.set_overflow(Gtk.Overflow.HIDDEN)
        self.cover_wrapper.add_css_class("rounded")
        self.cover_wrapper.set_valign(Gtk.Align.START) # Fix: Prevent stretching in horizontal mode
        self.cover_wrapper.append(self.cover_img)
        
        
        # Clamp for Header
        header_clamp = Adw.Clamp()
        header_clamp.set_maximum_size(800)
        header_clamp.set_tightening_threshold(600)
        header_clamp.set_child(self.header_info_box)
        
        self.header_info_box.append(self.cover_wrapper)
        
        # Details Column
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
        # Prevent width explosion
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
        self.meta_label.set_use_markup(True) # Enable markup
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
        
        self.header_info_box.append(self.details_col)
        
        # Actions Row (Play, Shuffle)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions_box.set_margin_top(12)
        
        self.actions_box = actions_box # Store for alignment
        
        play_btn = Gtk.Button(label="Play")
        play_btn.add_css_class("suggested-action")
        play_btn.add_css_class("pill")
        play_btn.connect("clicked", self.on_play_clicked)
        actions_box.append(play_btn)
        
        shuffle_btn = Gtk.Button()
        shuffle_content = Adw.ButtonContent()
        shuffle_content.set_label("Shuffle")
        shuffle_content.set_icon_name("media-playlist-shuffle-symbolic")
        shuffle_btn.set_child(shuffle_content)
        shuffle_btn.add_css_class("pill")
        shuffle_btn.connect("clicked", self.on_shuffle_clicked)
        actions_box.append(shuffle_btn)

        # Sort DropDown
        self.sort_dropdown = Gtk.DropDown.new_from_strings([
            "Default",
            "Title (A-Z)",
            "Artist (A-Z)",
            "Album (A-Z)"
        ])
        self.sort_dropdown.set_valign(Gtk.Align.CENTER)
        self.sort_dropdown.add_css_class("pill")
        self.sort_dropdown.connect("notify::selected", self.on_sort_changed)
        actions_box.append(self.sort_dropdown)
        
        self.details_col.append(actions_box)
        # self.header_info_box.append(self.details_col) # Already appended earlier
        
        content_box.append(header_clamp)
        
        # 2. Songs List
        self.songs_list = Gtk.ListBox()
        self.songs_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.songs_list.add_css_class("boxed-list")
        self.songs_list.connect("row-activated", self.on_song_activated)
        
        content_box.append(self.songs_list)
        
        # Content loading spinner (for when initial data is shown but tracks are loading)
        self.content_spinner = Adw.Spinner()
        self.content_spinner.set_size_request(32, 32)
        self.content_spinner.set_halign(Gtk.Align.CENTER)
        self.content_spinner.set_margin_top(24)
        self.content_spinner.set_visible(False)
        content_box.append(self.content_spinner)
        
        # Load More Spinner
        self.load_more_spinner = Adw.Spinner()
        self.load_more_spinner.set_size_request(24, 24)
        self.load_more_spinner.set_halign(Gtk.Align.CENTER)
        self.load_more_spinner.set_margin_top(12)
        self.load_more_spinner.set_visible(False)
        content_box.append(self.load_more_spinner)
        
        clamp.set_child(content_box)
        scrolled.set_child(clamp)
        self.main_box.append(scrolled)
        
        
        # Stack for Loading vs Content (Use Adw.ViewStack)
        self.stack = Adw.ViewStack()
        
        # 1. Loading Page
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
        
        # 2. Content Page
        self.stack.add_named(self.main_box, "content")
        
        # Set Stack as Content
        self.set_child(self.stack)
        
        self.current_tracks = []
        self.current_limit = 50 # Default limit
        self.is_loading_more = False
        self.current_filter_text = ""

    def filter_content(self, text):
        text = text.lower().strip()
        self.current_filter_text = text
        
        # Iterate over rows in songs_list
        child = self.songs_list.get_first_child()
        while child:
            if hasattr(child, 'video_data'):
                data = child.video_data
                title = data.get('title', '').lower()
                artist = data.get('artist', '').lower()
                
                # Check match
                match = (text in title) or (text in artist)
                child.set_visible(match)
            child = child.get_next_sibling()

    def _on_scroll(self, vadjust):
        val = vadjust.get_value()
        # If scrolled past a certain point, show title in header
        if val > 100:
             self.emit('header-title-changed', self.playlist_title_text)
        else:
             self.emit('header-title-changed', "")
             
        # Lazy Loading Check
        # If near bottom (e.g. within 200px) and not loading
        max_val = vadjust.get_upper() - vadjust.get_page_size()
        if max_val > 0 and val >= max_val - 200:
            if not self.is_loading_more and self.playlist_id and not getattr(self, 'is_fully_loaded', False):
                self.load_more()

    def load_more(self):
        self.is_loading_more = True
        self.load_more_spinner.set_visible(True)
        
        # Ensure we ask for MORE than we have
        self.current_limit = len(self.current_tracks) + 50
        print(f"Loading more... Limit now {self.current_limit}")
        
        thread = threading.Thread(target=self._fetch_playlist_details, args=(self.playlist_id, True))
        thread.daemon = True
        thread.start()

    def _on_map(self, widget):
        # Restore title if visible
        if hasattr(self, 'vadjust'):
             if self.vadjust.get_value() > 100:
                 self.emit('header-title-changed', self.playlist_title_text)
             else:
                 self.emit('header-title-changed', "")
    


    def _on_unmap(self, widget):
        self.emit('header-title-changed', "")

    def load_playlist(self, playlist_id, initial_data=None):
        if self.playlist_id != playlist_id:
            self.playlist_id = playlist_id
            self.playlist_title_text = ""
            self.current_limit = 50 # Reset limit
            self.emit('header-title-changed', "") # Reset header
            
            # Clear list
            self.current_tracks = []
            child = self.songs_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.songs_list.remove(child)
            child = next_child
        
        if initial_data:
            # Pre-fill data and show content immediately
            self.playlist_title_text = initial_data.get('title', '')
            self.playlist_name_label.set_label(self.playlist_title_text)
            self.description_label.set_label("")
            
            author = initial_data.get('author')
            if author and author != "Unknown":
                self.meta_label.set_label(f"{author} • Loading tracks...")
            else:
                 self.meta_label.set_label("Loading tracks...")
            
            thumb = initial_data.get('thumb')
            if thumb:
                if self.cover_img.url != thumb:
                    self.cover_img.set_from_icon_name("media-playlist-audio-symbolic") # Clear immediately
                    self.cover_img.load_url(thumb)
            else:
                self.cover_img.set_from_icon_name("media-playlist-audio-symbolic")
                self.cover_img.url = None 
                
            self.stack.set_visible_child_name("content")
            
            # Show content spinner while tracks load
            # Show content spinner while tracks load
            self.content_spinner.set_visible(True)
            
        else:
            # Show loading screen (full page)
            self.stack.set_visible_child_name("loading")
            # Ensure content spinner is off
            self.content_spinner.set_visible(False)
            
            # Reset UI elements in background
            self.playlist_name_label.set_label("Loading...")
            self.description_label.set_label("")
            self.meta_label.set_label("")
            self.cover_img.set_from_icon_name("media-playlist-audio-symbolic")
            self.cover_img.url = None
            
        thread = threading.Thread(target=self._fetch_playlist_details, args=(playlist_id,))
        thread.daemon = True
        thread.start()
    def _fetch_playlist_details(self, playlist_id, is_incremental=False):
        try:
            # Handle OLAK IDs by converting to MPRE (Album Browse ID)
            if playlist_id.startswith("OLAK"):
                try:
                    new_id = self.client.get_album_browse_id(playlist_id)
                    if new_id:
                        print(f"Converted {playlist_id} to {new_id}")
                        playlist_id = new_id
                except Exception as e:
                    print(f"Error converting OLAK to browseId: {e}")

            # Initialize variables to avoid UnboundLocalError
            count_str = None
            album_type = None

            if playlist_id == 'LM':
                 data = self.client.get_liked_songs(limit=self.current_limit)
                 title = "Your Likes"
                 description = "Your liked songs from YouTube Music."
                 tracks = data.get('tracks', []) if isinstance(data, dict) else data
                 track_count = data.get('trackCount', len(tracks)) if isinstance(data, dict) else len(tracks)
                 
                 song_text = "song" if track_count == 1 else "songs"
                 count_str = f"{track_count} {song_text}"
                 
                 year = None
                 author = "You"
                 thumbnails = []
                 
                 # Use first track's thumbnail as cover
                 if tracks and len(tracks) > 0:
                     first = tracks[0]
                     if first.get('thumbnails'):
                         thumbnails = first.get('thumbnails')
                         # Upgrade resolution
                         new_thumbs = []
                         for t in thumbnails:
                             if 'url' in t:
                                 # Try to upgrade to w544-h544
                                 # Pattern matching w120-h120 or similar
                                 new_url = re.sub(r'w\d+-h\d+', 'w544-h544', t['url'])
                                 new_t = t.copy()
                                 new_t['url'] = new_url
                                 new_thumbs.append(new_t)
                         if new_thumbs:
                             thumbnails = new_thumbs
                      
            elif playlist_id.startswith("MPRE"): # It's an album
                 try:
                     # Albums are finite, so LIMIT doesn't really apply typically
                     data = self.client.get_album(playlist_id)
                     title = data.get('title', 'Unknown Album')
                     description = data.get('description', '')
                     tracks = data.get('tracks', [])
                     thumbnails = data.get('thumbnails', [])
                     track_count = data.get('trackCount', len(tracks))
                     year = data.get('year', '')
                     
                     # Infer Type based on track count
                     if track_count == 1:
                         album_type = "Single"
                     elif 2 <= track_count <= 6:
                         album_type = "EP"
                     else:
                         album_type = "Album"
                         
                     # Construct Meta String
                     meta_parts = [album_type]
                     if year:
                         meta_parts.append(str(year))
                     
                     song_text = "song" if track_count == 1 else "songs"
                     count_str = f"{track_count} {song_text}"
                     meta_parts.append(count_str)
                     
                     count = " • ".join(meta_parts)
                     
                     artist_data = data.get('artists', [])
                     if isinstance(artist_data, list):
                         # author = ", ".join([a.get('name', '') for a in artist_data])
                         # Use Markup
                         parts = []
                         for a in artist_data:
                             name = GLib.markup_escape_text(a.get('name', 'Unknown'))
                             aid = a.get('id')
                             if aid:
                                 parts.append(f"<a href='artist:{aid}'>{name}</a>")
                             else:
                                 parts.append(name)
                         author = ", ".join(parts)
                     else:
                         author = GLib.markup_escape_text(str(artist_data))

                     # High-Res Cover Art Hack
                     if thumbnails:
                         for t in thumbnails:
                             if 'url' in t:
                                 # Replace specific resolution with high res
                                 # w120-h120 -> w544-h544
                                 # using regex to be safe against variations
                                 t['url'] = re.sub(r'w\d+-h\d+', 'w544-h544', t['url'])
                                 
                         # Propagate album cover to tracks if missing
                         for track in tracks:
                             if not track.get('thumbnails'):
                                 track['thumbnails'] = thumbnails
                                 
                 except Exception as e:
                     print(f"Error fetching album details: {e}")
                     return
            else:
                 try:
                     print(f"Fetching playlist: {playlist_id} (Limit: {self.current_limit})")
                     # Limit to 50 initially to prevent infinite loading on Mixes
                     data = self.client.get_playlist(playlist_id, limit=self.current_limit)
                     title = data.get('title', 'Unknown Playlist')
                     description = data.get('description', '')
                     tracks = data.get('tracks', [])
                     thumbnails = data.get('thumbnails', [])
                     
                     track_count = data.get('trackCount')
                     if track_count is None:
                         song_text = "Infinite"
                         count_str = "Infinite"
                     else:
                         song_text = "song" if track_count == 1 else "songs"
                         count_str = f"{track_count} {song_text}"
                     
                     # Construct Meta String for Playlist
                     meta_parts = []
                     
                     privacy = data.get('privacy')
                     if privacy:
                         meta_parts.append(privacy.capitalize())
                         
                     year = data.get('year')
                     if year:
                         meta_parts.append(str(year))
                         
                     meta_parts.append(count_str)
                     
                     duration = data.get('duration')
                     if duration:
                         meta_parts.append(duration)
                         
                     count = " • ".join(meta_parts)
                     author_data = data.get('author')
                     # print(f"DEBUG AUTHOR DATA: {author_data}") 
                     if isinstance(author_data, list):
                         parts = []
                         for a in author_data:
                             name = GLib.markup_escape_text(a.get('name', ''))
                             aid = a.get('id')
                             if aid:
                                  parts.append(f"<a href='artist:{aid}'>{name}</a>")
                             else:
                                  parts.append(name)
                         author = ", ".join(parts)
                     elif isinstance(author_data, dict):
                         name = GLib.markup_escape_text(author_data.get('name', 'Unknown'))
                         aid = author_data.get('id')
                         if aid:
                             author = f"<a href='artist:{aid}'>{name}</a>"
                         else:
                             author = name
                     else:
                         author = GLib.markup_escape_text(str(author_data)) if author_data else "Unknown"
                         
                     # Fallback for collaborative playlists where author might be "Unknown"
                     if "Unknown" in author and not author.startswith("<a"):
                         collab = data.get('collaborators')
                         if collab and isinstance(collab, dict):
                             text = collab.get('text', '')
                             if text:
                                 clean = text[3:] if text.startswith("by ") else text
                                 author = GLib.markup_escape_text(clean)
                             
                 except Exception as e:
                     print(f"Error processing playlists: {e}")
                     # If we fail here, we must provide fallback data or return
                     data = {}
                     title = "Error Loading Playlist"
                     description = str(e)
                     tracks = []
                     thumbnails = []
                     author = "Error"
                     track_count = 0
                     song_text = "songs"
                     count_str = "0 songs"

            # Determine Duration

            total_seconds = 0
            if 'duration_seconds' in data:
                total_seconds = data.get('duration_seconds')
            elif tracks and 'track_count' in locals() and track_count is not None: # Don't calc duration for infinite
                total_seconds = sum(t.get('duration_seconds', 0) for t in tracks)
                
            # Format Duration
            if total_seconds and total_seconds > 0:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                if hours > 0:
                    duration_str = f"{hours} hr {minutes} min"
                else:
                    duration_str = f"{minutes} min {seconds} sec"
            else:
                duration_str = data.get('duration', '')

            # Helper to construct Meta 1 (Type/Privacy • Year • Author)
            meta1_parts = []
            if playlist_id.startswith("MPRE") or playlist_id.startswith("OLAK"): # Album
                meta1_parts.append(album_type)
            else: # Playlist
                privacy = data.get('privacy')
                if privacy:
                    meta1_parts.append(privacy.capitalize())
                else:
                    meta1_parts.append("Playlist")

            if year:
                meta1_parts.append(str(year))
                
            if author:
                meta1_parts.append(author)
                
            meta1 = " • ".join(meta1_parts)
            
            # Helper to construct Meta 2 (Count • Duration)
            meta2_parts = []
            
            if count_str:
                 meta2_parts.append(count_str)
            else:
                 # fallback re-calc?
                 if 'track_count' in locals() and track_count is None:
                      meta2_parts.append("Infinite")
                 else:
                      meta2_parts.append(f"{locals().get('track_count', 0)} {locals().get('song_text', 'songs')}")
            
            if duration_str:
                meta2_parts.append(duration_str)
                
            meta2 = " • ".join(meta2_parts)

            GObject.idle_add(self.update_ui, title, description, meta1, meta2, thumbnails, tracks, is_incremental, track_count)
        except Exception as e:
            print(f"Critical error fetching playlist: {e}")
            self.is_loading_more = False
            GObject.idle_add(self.load_more_spinner.set_visible, False)

    def update_ui(self, title, description, meta1, meta2, thumbnails, tracks, append=False, total_tracks=None):
        self.stack.set_visible_child_name("content")
        self.content_spinner.set_visible(False)
        
        self.playlist_title_text = title
        self.playlist_name_label.set_label(title)
        
        if description:
            self.description_label.set_label(description)
            self.description_label.set_visible(True)
        else:
            self.description_label.set_visible(False)
            
        self.meta_label.set_markup(meta1) # Use markup
        self.stats_label.set_label(meta2)
        
        if thumbnails and not append: # Don't change cover on lazy load
            url = thumbnails[-1]['url']
            if self.cover_img.url != url:
                self.cover_img.load_url(url)
        elif not thumbnails and not self.cover_img.url:
             self.cover_img.set_from_icon_name("media-playlist-audio-symbolic")
             self.cover_img.url = None
             
        # Incremental Update logic
        if append:
            # We assume 'tracks' contains ALL tracks fetched with the new limit
            # So we only want to add the ones we don't have.
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
            if hasattr(self, 'original_tracks'):
                self.original_tracks.extend(new_tracks)
            
            # If we are currently sorted, we should probably re-sort
            if self.sort_dropdown.get_selected() != 0:
                self.reorder_playlist(self.sort_dropdown.get_selected())
            else:
                for t in new_tracks:
                     self._add_track_row(t)
                 
            # Hide spinner AFTER adding rows to avoid freeze perception
            self.load_more_spinner.set_visible(False)
            self.is_loading_more = False
            
            # Optimization: If we got fewer tracks than the limit, we reached the end.
            # OR if we know the total count
            if len(tracks) < self.current_limit:
                 print(f"Playlist fully loaded (fetched {len(tracks)} < limit {self.current_limit})")
                 self.is_fully_loaded = True
            elif total_tracks is not None and len(tracks) >= total_tracks:
                 print(f"Playlist fully loaded (fetched {len(tracks)} >= total {total_tracks})")
                 self.is_fully_loaded = True
                 
        else:
            self.is_fully_loaded = False # Reset on full load
            # Check if initial load is already the full thing
            if total_tracks is not None and len(tracks) >= total_tracks:
                self.is_fully_loaded = True
                
            # Full Reset
            self.current_tracks = list(tracks)
            self.original_tracks = list(tracks)
            self.sort_dropdown.set_selected(0) # Reset to Default
            
            for t in tracks:
                self._add_track_row(t)
                
    def _add_track_row(self, t):
            row = Adw.ActionRow()
            title = t.get('title', 'Unknown')
            artist_list = t.get('artists', [])
            artist = ", ".join([a.get('name', '') for a in artist_list])
            
            row.set_title(GLib.markup_escape_text(title))
            row.set_subtitle(GLib.markup_escape_text(artist))
            row.set_title_lines(1)
            row.set_subtitle_lines(1)
            
            # Apply Filter
            if self.current_filter_text:
                 match = (self.current_filter_text in title.lower()) or (self.current_filter_text in artist.lower())
                 row.set_visible(match)
            
            # Small thumb
            thumbnails = t.get('thumbnails', [])
            thumb_url = thumbnails[-1]['url'] if thumbnails else None
            
            img = AsyncImage(url=thumb_url, size=40)
            if not thumb_url:
                 img.set_from_icon_name("media-optical-symbolic")
            row.add_prefix(img)
            
            row.video_data = {
                'id': t.get('videoId'),
                'title': title,
                'artist': artist,
                'thumb': thumb_url,
                'setVideoId': t.get('setVideoId') or t.get('playlistId')
            }
            
            if not t.get('videoId'):
                row.set_sensitive(False)
                row.set_activatable(False)
            else:
                row.set_activatable(True)
                
            self.songs_list.append(row)
            
            # Context Menu (Right Click)
            gesture = Gtk.GestureClick()
            gesture.set_button(3) # Right click
            gesture.connect("pressed", self.on_row_right_click, row)
            row.add_controller(gesture)
            
            # Duration Label Suffix
            dur_sec = t.get('duration_seconds')
            dur_text = ""
            if dur_sec:
                m = dur_sec // 60
                s = dur_sec % 60
                dur_text = f"{m}:{s:02d}"
            else:
                dur_text = t.get('duration', '')
                
            if dur_text:
                dur_lbl = Gtk.Label(label=dur_text)
                dur_lbl.add_css_class("caption")
                dur_lbl.set_valign(Gtk.Align.CENTER)
                dur_lbl.set_margin_end(6)
                row.add_suffix(dur_lbl)

    def on_song_activated(self, box, row):
        if hasattr(row, 'video_data'):
            data = row.video_data
            if data['id']:
                # Find index of this song in current_tracks
                start_index = 0
                for i, t in enumerate(self.current_tracks):
                    if t.get('videoId') == data['id']:
                        start_index = i
                        break
                
                self.player.set_queue(self.current_tracks, start_index)

    def on_sort_changed(self, dropdown, pspec):
        selected = dropdown.get_selected()
        self.reorder_playlist(selected)

    def reorder_playlist(self, sort_type):
        if not self.current_tracks:
            return
            
        # 0: Default, 1: Title, 2: Artist, 3: Album
        if sort_type == 0:
            # Re-fetch default order (which is stored in a clean state if we had one)
            # For now, if we don't store it, we might need to re-fetch or just accept it's "sorted"
            # To properly support "Default", we should have stored original_tracks
            if hasattr(self, 'original_tracks'):
                self.current_tracks = list(self.original_tracks)
            else:
                return # Can't restore without backup
        elif sort_type == 1:
            self.current_tracks.sort(key=lambda x: x.get('title', '').lower())
        elif sort_type == 2:
            self.current_tracks.sort(key=lambda x: (x.get('artists', [{}])[0].get('name', '').lower() if x.get('artists') else '', x.get('title', '').lower()))
        elif sort_type == 3:
            self.current_tracks.sort(key=lambda x: (x.get('album', {}).get('name', '').lower() if isinstance(x.get('album'), dict) else str(x.get('album') or '').lower(), x.get('title', '').lower()))

        # Clear and Re-add
        child = self.songs_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.songs_list.remove(child)
            child = next_child
            
        for t in self.current_tracks:
            self._add_track_row(t)

    def on_meta_link_activated(self, label, uri):
        if uri.startswith("artist:"):
            # format: artist:ID
            aid = uri.split(":", 1)[1]
            root = self.get_root()
            if hasattr(root, 'open_artist'):
                 root.open_artist(aid, "Artist") 
            return True # Event handled
        return False
                
    def on_play_clicked(self, btn):
        if not self.current_tracks:
            return
            
        # Play immediate
        self.player.set_queue(self.current_tracks, 0, shuffle=False)
        
        # Load rest if not fully loaded
        if not self.is_fully_loaded and self.playlist_id:
             self._fetch_remaining_for_queue()

    def on_shuffle_clicked(self, btn):
        if not self.current_tracks:
            return
            
        # Play immediate (Shuffle loaded)
        self.player.set_queue(self.current_tracks, -1, shuffle=True)
        
        # Load rest
        if not self.is_fully_loaded and self.playlist_id:
             self._fetch_remaining_for_queue()

    def _fetch_remaining_for_queue(self):
        print("Fetching remaining tracks for queue...")
        # self.content_spinner.set_visible(True) # Don't block UI with spinner, let them listen
        
        def fetch_job():
            try:
                # Calculate how many we already have
                existing_count = len(self.current_tracks)
                
                # Fetch all
                data = self.client.get_playlist(self.playlist_id, limit=5000)
                tracks = data.get('tracks', [])
                
                # Filter new ones
                if len(tracks) > existing_count:
                    new_raw = tracks[existing_count:]
                    print(f"DEBUG: Found {len(new_raw)} new tracks to append.")
                    
                    normalized = []
                    for t in new_raw:
                        artist_list = t.get('artists', [])
                        artist = ", ".join([a.get('name', '') for a in artist_list])
                        normalized.append({
                            'videoId': t.get('videoId'),
                            'title': t.get('title'),
                            'artist': artist,
                            'thumb': t.get('thumbnails', [])[-1]['url'] if t.get('thumbnails') else None
                        })
                    
                    if normalized:
                        GObject.idle_add(self.player.extend_queue, normalized)
                else:
                    print("DEBUG: No new tracks found (or playlist matches loaded length).")
                
                # We can consider it fully loaded now?
                # GObject.idle_add(lambda: setattr(self, 'is_fully_loaded', True))

            except Exception as e:
                print(f"Error fetching remaining tracks: {e}")
        
        thread = threading.Thread(target=fetch_job)
        thread.daemon = True
        thread.start()

    def on_row_right_click(self, gesture, n_press, x, y, row):
        if not hasattr(row, 'video_data'):
            return
            
        data = row.video_data
        
        # We need Gdk, Gio imports if not present
        
        group = Gio.SimpleActionGroup()
        row.insert_action_group("row", group)
        
        # Copy Link
        def copy_link_action(action, param):
            vid = data.get('id')
            if vid:
                url = f"https://music.youtube.com/watch?v={vid}"
                clipboard = Gdk.Display.get_default().get_clipboard()
                clipboard.set(url)
        
        full_track_data = None
        if hasattr(self, 'current_tracks'):
             for t in self.current_tracks:
                 if t.get('videoId') == data.get('id'):
                     full_track_data = t
                     break
                     
        def goto_artist_action(action, param):
            if full_track_data and 'artists' in full_track_data:
                # Use first artist
                artist = full_track_data['artists'][0]
                aid = artist.get('id')
                name = artist.get('name')
                if aid:
                    root = self.get_root()
                    if hasattr(root, 'open_artist'):
                        root.open_artist(aid, name)

        def set_as_cover_action(action, param):
            vid = data.get('id')
            set_id = data.get('playlistId') # This is the setVideoId for playlists
            if self.playlist_id and set_id:
                # To change cover, we move the item to the top
                thread = threading.Thread(target=self._move_to_top, args=(set_id, vid))
                thread.daemon = True
                thread.start()

        action_copy = Gio.SimpleAction.new("copy_link", None)
        action_copy.connect("activate", copy_link_action)
        group.add_action(action_copy)
        
        action_goto = Gio.SimpleAction.new("goto_artist", None)
        action_goto.connect("activate", goto_artist_action)
        group.add_action(action_goto)

        action_set_cover = Gio.SimpleAction.new("set_cover", None)
        action_set_cover.connect("activate", set_as_cover_action)
        group.add_action(action_set_cover)
        
        menu_model = Gio.Menu()
        if data.get('id'):
            menu_model.append("Copy Link", "row.copy_link")
            
        if full_track_data and 'artists' in full_track_data and full_track_data['artists'][0].get('id'):
            menu_model.append("Go to Artist", "row.goto_artist")
        
        # Only allow setting cover if it's a playlist (not album) and we have auth
        if self.client.is_authenticated() and self.playlist_id and not (self.playlist_id.startswith("MPRE") or self.playlist_id.startswith("OLAK")):
             menu_model.append("Set as Playlist Cover", "row.set_cover")
            
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

    def _move_to_top(self, set_video_id, video_id):
        print(f"Moving track {video_id} (setVideoId: {set_video_id}) to top of playlist {self.playlist_id}")
        try:
            # moveItem can be a tuple (fromSetVideoId, toSetVideoId)
            # Or just a setVideoId if we want to move it relatively?
            # Actually ytmusicapi edit_playlist moveItem: 
            # "The setVideoId of the item to move" or "(setVideoId, setVideoId)"
            # If we want to move to TOP, we can use addToTop=True in some cases, but edit_playlist moveItem is for specific position.
            # Wait, let's check ytmusicapi docs for edit_playlist moveItem.
            # Usually moveItem is the setVideoId of the track you want to move.
            # And it moves it? Where?
            # ytmusicapi: moveItem (str | tuple): Move an item to a new position. 
            # If a string is provided, the item is moved to the position before the item with the provided setVideoId.
            # If a tuple is provided, the first item is moved before the second item.
            
            # To move to top, we need to know the setVideoId of the current FIRST item.
            if not self.original_tracks:
                 return
                 
            first_item = self.original_tracks[0]
            first_set_id = first_item.get('setVideoId')
            
            if first_set_id == set_video_id:
                 print("Item already at top.")
                 return
            
            # Move our item BEFORE the current first item
            self.client.edit_playlist(self.playlist_id, moveItem=(set_video_id, first_set_id))
            
            # Refresh playlist to show new order and new cover
            GLib.idle_add(self.load_playlist, self.playlist_id)
        except Exception as e:
            print(f"Error moving track: {e}")

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
