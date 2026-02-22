import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GObject
from yt_dlp import YoutubeDL
import threading
import random
import os

from mpris_server.server import Server
from player.mpris import MuseMprisAdapter, MuseEventAdapter

from api.client import MusicClient


class Player(GObject.Object):
    __gsignals__ = {
        "state-changed": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (str,),
        ),  # playing, paused, stopped
        "progression": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (float, float),
        ),  # position, duration (seconds) -> Changed to float
        "metadata-changed": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (str, str, str, str, str),
        ),  # title, artist, thumbnail_url, video_id, like_status
        "volume-changed": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (float, bool),
        ),  # volume, muted
    }

    def __init__(self):
        super().__init__()
        Gst.init(None)
        self.client = MusicClient()
        self.player = Gst.ElementFactory.make("playbin", "player")
        self.ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "noplaylist": True,
            "extract_flat": False,
            "js_runtimes": {"node": {}},
            "remote_components": ["ejs:github"],
        }

        self.bus = self.player.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)

        self.current_video_id = None

        # Queue State
        self.queue = []  # List of dicts: {id, title, artist, thumb, ...}
        self.current_queue_index = -1
        self.shuffle_mode = False
        self.original_queue = []  # Backup for un-shuffle
        self.load_generation = 0  # To handle race conditions in loading
        self.current_url = None
        self.last_seek_time = 0.0
        self.duration = -1
        self._is_loading = False
        self._current_logical_state = "stopped"

        # New modes
        self.repeat_mode = "none"  # none, track, all
        self.queue_source_id = None
        self.queue_is_infinite = False
        self._is_fetching_infinite = False

        # Timer for progress
        GObject.timeout_add(100, self.update_position)

        # MPRIS Setup
        self.mpris_adapter = MuseMprisAdapter(self)
        self.mpris_server = Server("Mixtapes", adapter=self.mpris_adapter)
        self.mpris_events = MuseEventAdapter(
            self.mpris_server.root, self.mpris_server.player
        )
        self.mpris_server.set_event_adapter(self.mpris_events)
        self.mpris_server.loop(background=True)

        # Connect signals for MPRIS updates
        self.connect("state-changed", self._on_mpris_state_changed)
        self.connect("metadata-changed", self._on_mpris_metadata_changed)
        self.connect("progression", self._on_mpris_progression)
        self.connect("volume-changed", self._on_mpris_volume_changed)

    def _on_mpris_state_changed(self, obj, state):
        if hasattr(self, "mpris_events"):
            # Explicitly tell the server the PlaybackStatus changed
            self.mpris_events.on_playpause()
            # Update metadata because length or 'CanGoNext' might have changed
            self.mpris_events.on_player_all()

    def _on_mpris_metadata_changed(
        self, obj, title, artist, thumb, video_id, like_status
    ):
        if hasattr(self, "mpris_events"):
            # Trigger the 'Metadata' property update
            self.mpris_events.on_title()
            # Update UI-related flags like CanGoNext/Previous
            self.mpris_events.on_player_all()

    def _on_mpris_progression(self, obj, pos, dur):
        # We don't usually emit D-Bus signals for every progression tick
        # as it's too frequent, but mpris-server handles position queries.
        pass

    def _on_mpris_volume_changed(self, obj, volume, muted):
        self.mpris_events.on_volume()

    def load_video(
        self, video_id, title="Loading...", artist="Unknown", thumbnail_url=None
    ):
        """Legacy/Single-track load. Clears queue and plays this one."""
        track = {
            "videoId": video_id,
            "title": title,
            "artist": artist,  # String or list, normalized later
            "thumb": thumbnail_url,
        }
        self.set_queue([track])

    def set_queue(
        self, tracks, start_index=0, shuffle=False, source_id=None, is_infinite=False
    ):
        """
        Sets the global queue and plays the track at start_index.
        tracks: list of dicts with videoId, title, artist, thumb
        """
        self.stop()
        self.queue = list(tracks)  # Copy for playing
        self.original_queue = list(tracks)  # Backup for un-shuffle
        self.shuffle_mode = shuffle  # Set mode based on request
        self.queue_source_id = source_id
        self.queue_is_infinite = is_infinite
        self._is_fetching_infinite = False

        target_track = (
            self.queue[start_index] if 0 <= start_index < len(self.queue) else None
        )

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
        self.emit("state-changed", "queue-updated")

    def add_to_queue(self, track, next=False):
        """Adds a track to the queue. if next=True, inserts after current."""
        if next and self.current_queue_index >= 0:
            self.queue.insert(self.current_queue_index + 1, track)
            self.original_queue.insert(
                self.current_queue_index + 1, track
            )  # Keep sync roughly
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

            print(
                f"DEBUG: Moved item from {old_index} to {insert_index} (target {new_index}). New Queue Order (titles): {[t.get('title') for t in self.queue[:5]]}..."
            )

            # Notify UI
            self.emit("state-changed", "queue-updated")
            return True
        return False

    def clear_queue(self):
        self.stop()
        self.queue = []
        self.original_queue = []
        self.current_queue_index = -1
        self.emit("state-changed", "stopped")
        self.emit("metadata-changed", "", "", "", "", "INDIFFERENT")

    def play_queue_index(self, index):
        if 0 <= index < len(self.queue):
            self.stop()
            self.current_queue_index = index
            self._play_current_index()

            # Check for infinite auto-append on manual skip
            print(
                f"\033[93m[DEBUG-INFINITE] play_queue_index({index}). queue_is_infinite={self.queue_is_infinite}, queue_source_id='{self.queue_source_id}', _is_fetching={self._is_fetching_infinite}, queue_len={len(self.queue)}, target_video={self.queue[index].get('videoId')} target_title={self.queue[index].get('title')}\033[0m"
            )
            if self.queue_is_infinite and self.queue_source_id and self.client:
                if (
                    not self._is_fetching_infinite
                    and self.current_queue_index >= len(self.queue) // 2
                ):
                    print(
                        f"\033[92m[DEBUG-INFINITE] Conditions met! Triggering _start_infinite_fetch() from play_queue_index\033[0m"
                    )
                    self._start_infinite_fetch()
                else:
                    print(
                        f"\033[91m[DEBUG-INFINITE] Conditions NOT met (is_fetching={self._is_fetching_infinite}, index={self.current_queue_index}, halfway={len(self.queue) // 2})\033[0m"
                    )
            else:
                print(
                    f"\033[91m[DEBUG-INFINITE] queue_is_infinite check failed (infinite={self.queue_is_infinite}, source={self.queue_source_id}, client={self.client != None})\033[0m"
                )

            self.emit("state-changed", "queue-updated")

    def next(self):
        if self.current_queue_index + 1 < len(self.queue):
            self.current_queue_index += 1
            self._play_current_index()

            # Check for infinite auto-append
            print(
                f"\033[93m[DEBUG-INFINITE] next(). queue_is_infinite={self.queue_is_infinite}, queue_source_id='{self.queue_source_id}', _is_fetching={self._is_fetching_infinite}, queue_len={len(self.queue)}\033[0m"
            )
            if self.queue_is_infinite and self.queue_source_id and self.client:
                if (
                    not self._is_fetching_infinite
                    and self.current_queue_index >= len(self.queue) // 2
                ):
                    print(
                        f"\033[92m[DEBUG-INFINITE] Conditions met! Triggering _start_infinite_fetch() from next()\033[0m"
                    )
                    self._start_infinite_fetch()
                else:
                    print(
                        f"\033[91m[DEBUG-INFINITE] Conditions NOT met (is_fetching={self._is_fetching_infinite}, index={self.current_queue_index}, halfway={len(self.queue) // 2})\033[0m"
                    )
            else:
                print(
                    f"\033[91m[DEBUG-INFINITE] queue_is_infinite check failed (infinite={self.queue_is_infinite}, source={self.queue_source_id}, client={self.client != None})\033[0m"
                )
        else:
            if self.repeat_mode == "all" and self.queue:
                self.current_queue_index = 0
                self._play_current_index()
            else:
                self.stop()  # End of queue
                self.current_queue_index = -1

        self.emit("state-changed", "queue-updated")

    def previous(self):
        # If > 5 seconds in, restart song
        try:
            pos = self.player.query_position(Gst.Format.TIME)[1]
            if pos > 5 * Gst.SECOND:
                self.player.seek_simple(
                    Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0
                )
                return
        except:
            pass

        if self.current_queue_index > 0:
            self.current_queue_index -= 1
            self._play_current_index()
        else:
            # Restart current if at 0
            self.player.seek_simple(
                Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0
            )

    def shuffle_queue(self):
        if not self.shuffle_mode:
            # Enable Shuffle
            self.shuffle_mode = True
            if self.queue:
                current = (
                    self.queue[self.current_queue_index]
                    if self.current_queue_index >= 0
                    else None
                )

                # Shuffle the list
                remaining = [
                    t for i, t in enumerate(self.queue) if i != self.current_queue_index
                ]
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
            if self.current_queue_index >= 0 and self.current_queue_index < len(
                self.queue
            ):
                current = self.queue[self.current_queue_index]
                self.queue = list(self.original_queue)
                # Restore index
                try:
                    self.current_queue_index = self.queue.index(current)
                except ValueError:
                    self.current_queue_index = 0  # Fallback
            else:
                self.queue = list(self.original_queue)

        # Emit signal to update UI
        self.emit("state-changed", "queue-updated")

    def set_repeat_mode(self, mode):
        if mode in ["none", "track", "all"]:
            self.repeat_mode = mode
            self.emit("state-changed", "repeat-updated")
            if hasattr(self, "mpris_events"):
                self.mpris_events.on_options()

    def _play_current_index(self):
        if 0 <= self.current_queue_index < len(self.queue):
            track = self.queue[self.current_queue_index]
            video_id = track.get("videoId")
            title = track.get("title", "Unknown")
            artist = track.get("artist", "")
            thumb = track.get("thumb")
            like_status = track.get("likeStatus", "INDIFFERENT")

            # Metadata Normalization (Handle raw ytmusicapi data)
            if not artist and "artists" in track:
                artist = ", ".join(
                    [a.get("name", "") for a in track.get("artists", [])]
                )

            if not artist:
                artist = "Unknown"

            if not thumb and "thumbnails" in track:
                thumbs = track.get("thumbnails", [])
                if thumbs:
                    thumb = thumbs[-1]["url"]

            # Handle artist list if needed (legacy check)
            if isinstance(artist, list):
                artist = ", ".join([a.get("name", "") for a in artist])

            print(
                f"\033[96m[DEBUG-PLAYER] _play_current_index({self.current_queue_index}). video_id={video_id} title='{title}'\033[0m"
            )
            self._load_internal(video_id, title, artist, thumb, like_status)

    def _load_internal(
        self, video_id, title, artist, thumbnail_url, like_status="INDIFFERENT"
    ):
        self.current_video_id = video_id

        # Set loading FIRST, then stop pipeline — prevents a "stopped" flash
        self._is_loading = True
        self.player.set_state(Gst.State.NULL)
        # Don't call _update_logical_state here — we'll emit once after metadata

        self.current_video_id = video_id

        # Reset state
        self.duration = -1
        self.emit("progression", 0.0, 0.0)

        # Increment generation to invalidate previous threads
        self.load_generation += 1
        current_gen = self.load_generation

        # Emit metadata immediately for UI responsiveness
        self.emit(
            "metadata-changed",
            title,
            artist,
            thumbnail_url if thumbnail_url else "",
            video_id,
            like_status,
        )
        # Now emit the loading state (only transition: whatever -> loading)
        self._update_logical_state()
        if hasattr(self, "mpris_events"):
            self.mpris_events.on_player_all()

        # Run yt-dlp in a thread
        thread = threading.Thread(
            target=self._fetch_and_play,
            args=(video_id, title, artist, thumbnail_url, like_status, current_gen),
        )
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
                history_and_current = self.queue[: current_idx + 1]
                upcoming = self.queue[current_idx + 1 :]

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

        print(
            f"DEBUG: Extended queue with {len(tracks)} tracks. Total: {len(self.queue)}"
        )
        self.emit("state-changed", "queue-updated")

    def _start_infinite_fetch(self):
        self._is_fetching_infinite = True
        limit = 50
        print(
            f"Queue halfway point reached. Fetching more for infinite playlist {self.queue_source_id}..."
        )

        last_video_id = None
        if self.queue:
            last_video_id = self.queue[-1].get("videoId")

        def fetch_job():
            try:
                data = self.client.get_watch_playlist(
                    video_id=last_video_id,
                    playlist_id=self.queue_source_id,
                    limit=limit,
                    radio=True,
                )
                tracks = data.get("tracks", [])

                # Filter out tracks already in our queue
                existing_ids = {
                    t.get("videoId") for t in self.queue if t.get("videoId")
                }
                new_tracks = [t for t in tracks if t.get("videoId") not in existing_ids]

                if new_tracks:
                    GObject.idle_add(self._on_infinite_fetch_complete, new_tracks)
                else:
                    self._is_fetching_infinite = False
            except Exception as e:
                print(f"Error fetching infinite queue: {e}")
                self._is_fetching_infinite = False

        thread = threading.Thread(target=fetch_job)
        thread.daemon = True
        thread.start()

    def _on_infinite_fetch_complete(self, new_tracks):
        self.extend_queue(new_tracks)
        self._is_fetching_infinite = False

    def _create_cookie_file(self, headers):
        """Creates a temporary Netscape format cookie file from headers."""
        import tempfile
        import time

        cookie_str = headers.get("Cookie", "")
        if not cookie_str:
            return None

        fd, path = tempfile.mkstemp(suffix=".txt", text=True)
        with os.fdopen(fd, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# This file is generated by Mixtapes\n\n")

            now = int(time.time()) + 3600 * 24 * 365  # 1 year validity

            # Simple parsing of "key=value; key2=value2"
            parts = cookie_str.split(";")
            for part in parts:
                if "=" in part:
                    key, value = part.strip().split("=", 1)
                    # domain flag path secure expiration name value
                    f.write(f".youtube.com\tTRUE\t/\tTRUE\t{now}\t{key}\t{value}\n")
                    f.write(f".google.com\tTRUE\t/\tTRUE\t{now}\t{key}\t{value}\n")

        return path

    def _fetch_and_play(
        self,
        video_id,
        title_hint,
        artist_hint,
        thumb_hint,
        like_status_hint,
        generation,
    ):
        if generation != self.load_generation:
            print(
                f"DEBUG: Stale load generation {generation} (current {self.load_generation}). Aborting."
            )
            return
        import os

        url = f"https://www.youtube.com/watch?v={video_id}"

        # Use a local copy of options to prevent race conditions
        opts = self.ydl_opts.copy()
        cookie_file = None
        try:
            # Inject headers/cookies if authenticated
            if self.client.is_authenticated() and self.client.api:
                print(
                    f"DEBUG: Client is authenticated. Headers keys: {list(self.client.api.headers.keys())}"
                )
                # Create Netscape cookie file
                cookie_file = self._create_cookie_file(self.client.api.headers)
                if cookie_file:
                    print(f"DEBUG: Generated cookie file at {cookie_file}")
                    opts["cookiefile"] = cookie_file
                else:
                    print("DEBUG: No cookie file generated (Cookie header missing?)")

                # Still pass User-Agent and Authorization if available
                http_headers = {}
                if "User-Agent" in self.client.api.headers:
                    http_headers["User-Agent"] = self.client.api.headers["User-Agent"]
                if "Authorization" in self.client.api.headers:
                    print("DEBUG: Passing Authorization header to yt-dlp")
                    http_headers["Authorization"] = self.client.api.headers[
                        "Authorization"
                    ]

                if http_headers:
                    opts["http_headers"] = http_headers
            else:
                print("DEBUG: Client NOT authenticated")

            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info["url"]

                # Extract only what we need, then drop the large info dict
                fetched_title = info.get("title", "Unknown")
                fetched_artist = info.get("uploader", "Unknown")
                fetched_thumb = info.get("thumbnail")
                del info  # Free 100KB+ of format/subtitle data

                # If hints are placeholders, try to get better metadata from ytmusicapi
                if (not title_hint or title_hint == "Loading...") or (
                    not artist_hint or artist_hint == "Unknown"
                ):
                    try:
                        song_details = self.client.get_song(video_id)
                        if song_details:
                            v_details = song_details.get("videoDetails", {})
                            if "title" in v_details:
                                fetched_title = v_details["title"]
                            if "author" in v_details:
                                fetched_artist = v_details["author"]

                            # Use high-res thumbnail from get_song if available
                            if (
                                not thumb_hint
                                and "thumbnail" in v_details
                                and "thumbnails" in v_details["thumbnail"]
                            ):
                                thumbs = v_details["thumbnail"]["thumbnails"]
                                if thumbs:
                                    fetched_thumb = thumbs[-1]["url"]

                    except Exception as e:
                        print(f"Error fetching metadata from ytmusicapi: {e}")

                final_title = (
                    title_hint
                    if title_hint and title_hint != "Loading..."
                    else fetched_title
                )
                final_artist = (
                    artist_hint
                    if artist_hint and artist_hint != "Unknown"
                    else fetched_artist
                )

                print(f"Playing: {final_title} by {final_artist}")

                final_thumb = thumb_hint or fetched_thumb or ""

                # Check generation again before playing
                if generation != self.load_generation:
                    print(
                        f"DEBUG: Stale load generation {generation} before playbin set. Aborting."
                    )
                    if cookie_file and os.path.exists(cookie_file):
                        os.remove(cookie_file)
                    return

                GObject.idle_add(self._start_playback, stream_url)

                GObject.idle_add(
                    self.emit,
                    "metadata-changed",
                    final_title,
                    final_artist,
                    final_thumb,
                    video_id,
                    like_status_hint,
                )
        except Exception as e:
            print(f"Error fetching URL: {e}")
        finally:
            if cookie_file and os.path.exists(cookie_file):
                try:
                    os.remove(cookie_file)
                    print(f"DEBUG: Cleaned up cookie file {cookie_file}")
                except:
                    pass

    def _start_playback(self, uri, cookie_file=None):
        self.player.set_state(Gst.State.NULL)
        self.player.set_property("uri", uri)
        self.player.set_state(Gst.State.PLAYING)

        # Direct URLs typically work without explicit cookies. Stale URLs are handled in _load_internal.
        return False

    def play(self):
        self.player.set_state(Gst.State.PLAYING)
        self._update_logical_state()

    def pause(self):
        self.player.set_state(Gst.State.PAUSED)
        self._update_logical_state()

    def stop(self):
        self.player.set_state(Gst.State.NULL)
        self._is_loading = False
        # Force stopped state immediately
        if self._current_logical_state != "stopped":
            self._current_logical_state = "stopped"
            self.emit("state-changed", "stopped")

    def _update_logical_state(self):
        """Evaluates internal flags and GStreamer state to emit a stable logical state.

        We only track loading (waiting for yt-dlp) and GStreamer pipeline states.
        GStreamer's playbin handles stream buffering internally — we don't need to
        show a spinner for mid-stream buffer refills.
        """
        ret, gst_state, pending = self.player.get_state(0)

        new_state = "stopped"

        if self._is_loading:
            new_state = "loading"
        elif gst_state == Gst.State.PLAYING:
            new_state = "playing"
        elif gst_state == Gst.State.PAUSED:
            # Only show paused if we're not loading (loading uses NULL->PAUSED->PLAYING)
            if not self._is_loading:
                new_state = "paused"

        if new_state != self._current_logical_state:
            self._current_logical_state = new_state
            self.emit("state-changed", new_state)

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("EOS Reached. Advancing to next track.")
            self.stop()
            if self.repeat_mode == "track":
                GObject.idle_add(self._play_current_index)
            else:
                GObject.idle_add(self.next)
        elif t == Gst.MessageType.ASYNC_DONE:
            # The stream is actually loaded and ready
            if hasattr(self, "mpris_events"):
                self.mpris_events.on_player_all()  # Refresh duration and status
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, {debug}")
            self.player.set_state(Gst.State.NULL)
            self._is_loading = False
            self._update_logical_state()
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.player:
                old, new, pending = message.parse_state_changed()
                if new == Gst.State.PLAYING:
                    self._is_loading = False
                self._update_logical_state()
        # BUFFERING messages are intentionally ignored — playbin manages
        # stream buffering internally and briefly pauses the pipeline,
        # which would cause the spinner to flash unnecessarily.

    def get_state_string(self):
        """Returns the current logical player state."""
        return self._current_logical_state

    def update_position(self):
        import time

        now = time.time()

        # 1. Protection during seek/load
        # If we are loading or just sought, don't trust GStreamer yet
        if self._is_loading or (now - self.last_seek_time < 0.8):
            return True

        ret, state, pending = self.player.get_state(0)
        if state in [Gst.State.PLAYING, Gst.State.PAUSED]:
            # 2. Update Duration if it changed (vital for MPRIS progress bar scale)
            success_dur, dur_nanos = self.player.query_duration(Gst.Format.TIME)
            if success_dur:
                new_dur = dur_nanos / Gst.SECOND
                if (
                    abs(new_dur - self.duration) > 0.1
                ):  # Threshold to avoid float jitter
                    self.duration = new_dur
                    if hasattr(self, "mpris_events"):
                        self.mpris_events.on_title()  # Syncs 'mpris:length'

            # 3. Update Position
            success_pos, pos_nanos = self.player.query_position(Gst.Format.TIME)
            if success_pos:
                current_time = pos_nanos / Gst.SECOND

                # Update the Adapter's cache immediately
                if hasattr(self, "mpris_adapter"):
                    self.mpris_adapter._last_pos = pos_nanos // 1000

                # 4. Emit progression for local UI
                # We use float(d) to ensure the UI progress bar has a max value
                d = self.duration if self.duration > 0 else 0
                self.emit("progression", float(current_time), float(d))

        return True

    def seek(self, position, flush=True):
        """Seek to position in seconds"""
        if self.player.get_state(0)[1] == Gst.State.NULL:
            return

        import time

        self.last_seek_time = time.time()

        flags = Gst.SeekFlags.ACCURATE
        if flush:
            flags |= Gst.SeekFlags.FLUSH

        self.player.seek_simple(
            Gst.Format.TIME,
            flags,
            int(position * Gst.SECOND),
        )

        if hasattr(self, "mpris_events"):
            self.mpris_events.on_seek(int(position * 1_000_000))

    def get_volume(self):
        return self.player.get_property("volume")

    def set_volume(self, value):
        # value 0.0 to 1.0
        self.player.set_property("volume", float(value))
        self.emit("volume-changed", float(value), self.get_mute())

    def get_mute(self):
        return self.player.get_property("mute")

    def set_mute(self, is_muted):
        self.player.set_property("mute", is_muted)
        self.emit("volume-changed", self.get_volume(), is_muted)
