import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject
from yt_dlp import YoutubeDL
import threading
import random
import os

from api.client import MusicClient

class Player(GObject.Object):
    __gsignals__ = {
        'state-changed': (GObject.SignalFlags.RUN_FIRST, None, (str,)), # playing, paused, stopped
        'progression': (GObject.SignalFlags.RUN_FIRST, None, (float, float)), # position, duration (seconds) -> Changed to float
        'metadata-changed': (GObject.SignalFlags.RUN_FIRST, None, (str, str, str)) # title, artist, thumbnail_url
    }

    def __init__(self):
        super().__init__()
        Gst.init(None)
        self.client = MusicClient()
        self.player = Gst.ElementFactory.make("playbin", "player")
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,
            'extract_flat': False,
            'js_runtimes': {'node': {}},
            'remote_components': ['ejs:github']
        }
        
        self.bus = self.player.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)
        
        self.duration = -1
        self.current_url = None
        self.last_seek_time = 0.0
        
        # Timer for progress
        GObject.timeout_add(100, self.update_position)
        
        self.current_video_id = None
        
        # Queue State
        self.queue = [] # List of dicts: {id, title, artist, thumb, ...}
        self.current_queue_index = -1
        self.shuffle_mode = False
        self.original_queue = [] # Backup for un-shuffle
        self.load_generation = 0 # To handle race conditions in loading

    def load_video(self, video_id, title="Loading...", artist="Unknown", thumbnail_url=None):
        """Legacy/Single-track load. Clears queue and plays this one."""
        track = {
            'videoId': video_id,
            'title': title,
            'artist': artist, # String or list, normalized later
            'thumb': thumbnail_url
        }
        self.set_queue([track])

    def set_queue(self, tracks, start_index=0, shuffle=False):
        """
        Sets the global queue and plays the track at start_index.
        tracks: list of dicts with videoId, title, artist, thumb
        """
        self.stop()
        self.queue = list(tracks) # Copy for playing
        self.original_queue = list(tracks) # Backup for un-shuffle
        self.shuffle_mode = shuffle # Set mode based on request
        
        target_track = self.queue[start_index] if 0 <= start_index < len(self.queue) else None
        
        if shuffle:
             import random
             # If start_index is valid, we want to play that track FIRST, then shuffle the rest.
             if target_track:
                 # Remove target
                 self.queue.remove(target_track)
                 # Shuffle rest
                 random.shuffle(self.queue)
                 # Insert target at 0
                 self.queue.insert(0, target_track)
                 self.current_queue_index = 0
             else:
                 random.shuffle(self.queue)
                 self.current_queue_index = 0
             # Note: original_queue remains ordered as passed
        else:
             self.current_queue_index = start_index

        print(f"Queue set with {len(tracks)} tracks. Shuffle={shuffle}.")
        if self.current_queue_index >= 0 and self.current_queue_index < len(self.queue):
             self._play_current_index()
        else:
             self.stop()
        self.emit('state-changed', "queue-updated")

    def add_to_queue(self, track, next=False):
        """Adds a track to the queue. if next=True, inserts after current."""
        if next and self.current_queue_index >= 0:
             self.queue.insert(self.current_queue_index + 1, track)
             self.original_queue.insert(self.current_queue_index + 1, track) # Keep sync roughly
        else:
             self.queue.append(track)
             self.original_queue.append(track)
        
        # If nothing is playing, play this
        if self.current_queue_index == -1:
             self.current_queue_index = 0
             self._play_current_index()

    def remove_from_queue(self, index):
        if 0 <= index < len(self.queue):
            pop = self.queue.pop(index)
            # Adjust current index
            if index < self.current_queue_index:
                self.current_queue_index -= 1
            elif index == self.current_queue_index:
                # We removed the playing track. Play next?
                if self.current_queue_index < len(self.queue):
                     self._play_current_index()
                else:
                     self.stop()
                     self.current_queue_index = -1
            
            # Remove from original if present (simplified)
            if pop in self.original_queue:
                self.original_queue.remove(pop)

    def move_queue_item(self, old_index, new_index):
        if 0 <= old_index < len(self.queue) and 0 <= new_index < len(self.queue):
            # Adjust index when moving down to insert before target, accounting for the list shift from popping.
            
            insert_index = new_index
            if old_index < new_index:
                insert_index -= 1
                
            item = self.queue.pop(old_index)
            self.queue.insert(insert_index, item)
            
            # Update current_queue_index
            # This is tricky. Let's just re-find the playing track if possible, or simple math.
            # The Simple math in question:
            if self.current_queue_index == old_index:
                self.current_queue_index = insert_index
            elif old_index < self.current_queue_index <= insert_index:
                 self.current_queue_index -= 1
            elif insert_index <= self.current_queue_index < old_index:
                 self.current_queue_index += 1
                
            print(f"DEBUG: Moved item from {old_index} to {insert_index} (target {new_index}). New Queue Order (titles): {[t.get('title') for t in self.queue[:5]]}...")
            
            # Notify UI
            self.emit('state-changed', "queue-updated")
            return True
        return False

    def clear_queue(self):
        self.stop()
        self.queue = []
        self.original_queue = []
        self.current_queue_index = -1
        self.emit('state-changed', "stopped")
        self.emit('metadata-changed', "Not Playing", "", "")

    def next(self):
        if self.current_queue_index + 1 < len(self.queue):
            self.current_queue_index += 1
            self._play_current_index()
        else:
            self.stop() # End of queue
            self.current_queue_index = -1

        self.emit('state-changed', "queue-updated")

    def previous(self):
        # If > 5 seconds in, restart song
        try:
             pos = self.player.query_position(Gst.Format.TIME)[1]
             if pos > 5 * Gst.SECOND:
                 self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0)
                 return
        except:
             pass
             
        if self.current_queue_index > 0:
            self.current_queue_index -= 1
            self._play_current_index()
        else:
            # Restart current if at 0
            self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0)
        
        

    def shuffle_queue(self):
        if not self.shuffle_mode:
            # Enable Shuffle
            self.shuffle_mode = True
            if self.queue:
                current = self.queue[self.current_queue_index] if self.current_queue_index >= 0 else None
                
                # Shuffle the list
                remaining = [t for i, t in enumerate(self.queue) if i != self.current_queue_index]
                random.shuffle(remaining)
                
                if current:
                    self.queue = [current] + remaining
                    self.current_queue_index = 0
                else:
                    self.queue = remaining
                    self.current_queue_index = -1
        else:
            # Disable Shuffle (Restore original order)
            self.shuffle_mode = False
            # Try to find current track in original queue
            if self.current_queue_index >= 0 and self.current_queue_index < len(self.queue):
                current = self.queue[self.current_queue_index]
                self.queue = list(self.original_queue)
                # Restore index
                try:
                    self.current_queue_index = self.queue.index(current)
                except ValueError:
                    self.current_queue_index = 0 # Fallback
            else:
                 self.queue = list(self.original_queue)

        # Emit signal to update UI
        self.emit('state-changed', "queue-updated")


    def _play_current_index(self):
        if 0 <= self.current_queue_index < len(self.queue):
            track = self.queue[self.current_queue_index]
            video_id = track.get('videoId')
            title = track.get('title', 'Unknown')
            artist = track.get('artist', '')
            thumb = track.get('thumb')
            
            # Metadata Normalization (Handle raw ytmusicapi data)
            if not artist and 'artists' in track:
                 artist = ", ".join([a.get('name', '') for a in track.get('artists', [])])
                 
            if not artist:
                artist = "Unknown"
            
            if not thumb and 'thumbnails' in track:
                 thumbs = track.get('thumbnails', [])
                 if thumbs:
                     thumb = thumbs[-1]['url']
            
            # Handle artist list if needed (legacy check)
            if isinstance(artist, list):
                 artist = ", ".join([a.get('name', '') for a in artist])
            
            self._load_internal(video_id, title, artist, thumb)

    def _load_internal(self, video_id, title, artist, thumbnail_url):
        # Stop previous playback immediately
        self.stop()
        
        self.current_video_id = video_id
        
        # Reset state
        self.duration = -1
        self.emit('progression', 0.0, 0.0)
        
        # Increment generation to invalidate previous threads
        self.load_generation += 1
        current_gen = self.load_generation
        
        # Emit metadata immediately for UI responsiveness
        print(f"DEBUG: _load_internal emitting metadata (Gen {current_gen}). Thumb: {thumbnail_url}")
        self.emit('metadata-changed', title, artist, thumbnail_url if thumbnail_url else "")
        self.emit('state-changed', "loading")

        # Run yt-dlp in a thread
        thread = threading.Thread(target=self._fetch_and_play, args=(video_id, title, artist, thumbnail_url, current_gen))
        thread.daemon = True
        thread.start()

    def extend_queue(self, tracks):
        """Appends new tracks to the queue (and original_queue)."""
        if not tracks:
            return
            
        # Append to original queue always
        self.original_queue.extend(tracks)
        
        if self.shuffle_mode:
            # Smart Shuffle: Mix new tracks with UPCOMING tracks
            # We don't want to touch history or current song.
            
            current_idx = self.current_queue_index
            
            # Assume valid index; fallback handling can be added if needed.
            if 0 <= current_idx < len(self.queue):
                history_and_current = self.queue[:current_idx+1]
                upcoming = self.queue[current_idx+1:]
                
                combined = upcoming + tracks
                import random
                random.shuffle(combined)
                
                self.queue = history_and_current + combined
                # current_queue_index stays same
            else:
                # Queue empty or invalid index, just shuffle all
                self.queue.extend(tracks)
                import random
                random.shuffle(self.queue)
                # If we were playing, index might be -1.
                # If we were stopped, index -1.
                
                if self.current_queue_index == -1 and self.queue:
                     self.current_queue_index = 0
                     
        else:
            self.queue.extend(tracks)
            
        print(f"DEBUG: Extended queue with {len(tracks)} tracks. Total: {len(self.queue)}")
        self.emit('state-changed', "queue-updated")

    def _create_cookie_file(self, headers):
        """Creates a temporary Netscape format cookie file from headers."""
        import tempfile
        import time
        
        cookie_str = headers.get('Cookie', '')
        if not cookie_str:
            return None
            
        fd, path = tempfile.mkstemp(suffix=".txt", text=True)
        with os.fdopen(fd, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This file is generated by Muse\n\n")
            
            now = int(time.time()) + 3600 * 24 * 365 # 1 year validity
            
            # Simple parsing of "key=value; key2=value2"
            parts = cookie_str.split(';')
            for part in parts:
                if '=' in part:
                    key, value = part.strip().split('=', 1)
                    # domain flag path secure expiration name value
                    f.write(f".youtube.com\tTRUE\t/\tTRUE\t{now}\t{key}\t{value}\n")
                    f.write(f".google.com\tTRUE\t/\tTRUE\t{now}\t{key}\t{value}\n")
                    
        return path

    def _fetch_and_play(self, video_id, title_hint, artist_hint, thumb_hint, generation):
        if generation != self.load_generation:
            print(f"DEBUG: Stale load generation {generation} (current {self.load_generation}). Aborting.")
            return
        import os
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        cookie_file = None
        
        # Inject headers/cookies if authenticated
        if self.client.is_authenticated() and self.client.api:
            print(f"DEBUG: Client is authenticated. Headers keys: {list(self.client.api.headers.keys())}")
            # Create Netscape cookie file
            cookie_file = self._create_cookie_file(self.client.api.headers)
            if cookie_file:
                print(f"DEBUG: Generated cookie file at {cookie_file}")
                self.ydl_opts['cookiefile'] = cookie_file
            else:
                 print("DEBUG: No cookie file generated (Cookie header missing?)")
            
            # Still pass User-Agent and Authorization if available
            http_headers = {}
            if 'User-Agent' in self.client.api.headers:
                http_headers['User-Agent'] = self.client.api.headers['User-Agent']
            if 'Authorization' in self.client.api.headers:
                print("DEBUG: Passing Authorization header to yt-dlp")
                http_headers['Authorization'] = self.client.api.headers['Authorization']
            
            if http_headers:
                self.ydl_opts['http_headers'] = http_headers
        else:
            print("DEBUG: Client NOT authenticated")
            
        try:
            with YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info['url']
                
                # Metadata Logic: Prefer hints if provided and not placeholders
                fetched_title = info.get('title', 'Unknown')
                fetched_artist = info.get('uploader', 'Unknown')
                
                # If hints are placeholders, try to get better metadata from ytmusicapi
                if (not title_hint or title_hint == "Loading...") or (not artist_hint or artist_hint == "Unknown"):
                    try:
                        song_details = self.client.get_song(video_id)
                        if song_details:
                            v_details = song_details.get('videoDetails', {})
                            if 'title' in v_details:
                                fetched_title = v_details['title']
                            if 'author' in v_details:
                                fetched_artist = v_details['author']
                            
                            # Use high-res thumbnail from get_song if available and we don't have a hint
                            if not thumb_hint and 'thumbnail' in v_details and 'thumbnails' in v_details['thumbnail']:
                                thumbs = v_details['thumbnail']['thumbnails']
                                if thumbs:
                                    # Get largest
                                    info['thumbnail'] = thumbs[-1]['url'] 

                    except Exception as e:
                        print(f"Error fetching metadata from ytmusicapi: {e}")

                final_title = title_hint if title_hint and title_hint != "Loading..." else fetched_title
                final_artist = artist_hint if artist_hint and artist_hint != "Unknown" else fetched_artist
                
                print(f"Playing: {final_title} by {final_artist}")
                
                # Check for thumbnails in info
                final_thumb = thumb_hint
                if not final_thumb and 'thumbnail' in info:
                    final_thumb = info['thumbnail']

                # Update GStreamer on main thread
                # Check generation again before playing
                if generation != self.load_generation:
                    print(f"DEBUG: Stale load generation {generation} before playbin set. Aborting.")
                    if cookie_file and os.path.exists(cookie_file):
                        os.remove(cookie_file)
                    return

                GObject.idle_add(self._start_playback, stream_url, cookie_file)
                
                # Only emit if we actually fell back to fetched data, or just emit final ensuring consistency
                # Emitting again is fine, as long as it's the *correct* data (the hint)
                GObject.idle_add(self.emit, 'metadata-changed', final_title, final_artist, final_thumb if final_thumb else "")
        except Exception as e:
            print(f"Error fetching URL: {e}")

    def _start_playback(self, uri, cookie_file=None):
        self.player.set_state(Gst.State.NULL)
        self.player.set_property("uri", uri)
        self.player.set_state(Gst.State.PLAYING)
        self.emit('state-changed', "playing")
        
        # Direct URLs typically work without explicit cookies. Stale URLs are handled in _load_internal.
        return False

    def play(self):
        self.player.set_state(Gst.State.PLAYING)
        self.emit('state-changed', "playing")

    def pause(self):
        self.player.set_state(Gst.State.PAUSED)
        self.emit('state-changed', "paused")

    def stop(self):
        self.player.set_state(Gst.State.NULL)
        self.emit('state-changed', "stopped")

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("EOS Reached. Advancing to next track.")
            self.emit('state-changed', "stopped") # Optional, next() will trigger loading
            GObject.idle_add(self.next)
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, {debug}")
            self.player.set_state(Gst.State.NULL)
            self.emit('state-changed', "error")

    def update_position(self):
        # Prevent race condition with seek
        import time
        if time.time() - self.last_seek_time < 1.0:
            return True

        # get_state returns (success, current_state, pending_state)
        ret, state, pending = self.player.get_state(0)
        if state == Gst.State.PLAYING or state == Gst.State.PAUSED:
            # Query duration always to ensure accuracy or at least retry
            ret, dur = self.player.query_duration(Gst.Format.TIME)
            if ret:
                self.duration = dur / Gst.SECOND
            
            # Query position
            ret, pos = self.player.query_position(Gst.Format.TIME)
            if ret:
                current_time = pos / Gst.SECOND
                # If duration is still unknown or invalid, use current_time + ? or just don't crash
                d = self.duration if self.duration > 0 else 0
                self.emit('progression', float(current_time), float(d))
        return True

    def seek(self, position):
        """Seek to position in seconds"""
        import time
        self.last_seek_time = time.time()
        # Use ACCURATE to avoid snapping to distant keyframes (which causes the "jumping back" issue)
        self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE, int(position * Gst.SECOND))
