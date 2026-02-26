import threading
import urllib.request
from collections import OrderedDict
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

# Bounded LRU Cache to prevent memory leaks (max 100 images)
IMG_CACHE = OrderedDict()
MAX_CACHE_SIZE = 100


def cache_pixbuf(url, pixbuf):
    if not url or not pixbuf:
        return
    if url in IMG_CACHE:
        IMG_CACHE.move_to_end(url)
        return

    # Scale down very large images before caching to save massive amounts of RAM
    # 800px is more than enough for any UI element in this app
    w = pixbuf.get_width()
    h = pixbuf.get_height()
    max_dim = 800
    if w > max_dim or h > max_dim:
        scale = max_dim / max(w, h)
        pixbuf = pixbuf.scale_simple(
            int(w * scale), int(h * scale), GdkPixbuf.InterpType.BILINEAR
        )

    IMG_CACHE[url] = pixbuf
    if len(IMG_CACHE) > MAX_CACHE_SIZE:
        IMG_CACHE.popitem(last=False)


class AsyncImage(Gtk.Image):
    def __init__(
        self, url=None, size=None, width=None, height=None, circular=False, **kwargs
    ):
        super().__init__(**kwargs)

        # Determine target dimensions
        self.target_w = width if width else size
        self.target_h = height if height else size

        if not self.target_w:
            self.target_w = 48
        if not self.target_h:
            self.target_h = 48

        # Set pixel size if provided (limits size for icons).
        if size:
            self.set_pixel_size(size)
        else:
            # Rely on pixbuf scaling for explicit width/height.
            pass

        self.set_from_icon_name("image-missing-symbolic")  # Placeholder
        self.url = url
        self.circular = circular

        if url:
            self.load_url(url)

    # ... (load_url, _fetch_image same) ...

    def load_url(self, url, **kwargs):
        self.url = url
        if not url:
            self.set_from_icon_name("image-missing-symbolic")
            return

        cached_pixbuf = IMG_CACHE.get(url)
        if cached_pixbuf:
            IMG_CACHE.move_to_end(url)

        thread = threading.Thread(
            target=self._fetch_image, args=(url, kwargs.get("fallbacks"), cached_pixbuf)
        )
        thread.daemon = True
        thread.start()

    def _fetch_image(self, url, fallbacks=None, cached_pixbuf=None):
        try:
            pixbuf = cached_pixbuf
            if not pixbuf:
                # Download image data
                with urllib.request.urlopen(url) as response:
                    data = response.read()

                loader = GdkPixbuf.PixbufLoader()
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()

            if pixbuf:
                # Cache the original full-res (scaled to max 800) pixbuf
                cache_pixbuf(url, pixbuf)

                # Now perform the widget-specific scaling and cropping in the background thread
                tw = self.target_w
                th = self.target_h

                w = pixbuf.get_width()
                h = pixbuf.get_height()

                # Calculate scale to fill the target size (cover)
                scale = max(tw / w, th / h)
                new_w = int(w * scale)
                new_h = int(h * scale)

                # Scale properly
                scaled = pixbuf.scale_simple(
                    new_w, new_h, GdkPixbuf.InterpType.BILINEAR
                )

                # Center crop to target dimensions
                final_pixbuf = scaled
                if new_w > tw or new_h > th:
                    offset_x = max(0, (new_w - tw) // 2)
                    offset_y = max(0, (new_h - th) // 2)
                    cw = min(tw, new_w - offset_x)
                    ch = min(th, new_h - offset_y)
                    if cw > 0 and ch > 0:
                        try:
                            final_pixbuf = scaled.new_subpixbuf(
                                offset_x, offset_y, cw, ch
                            )
                        except Exception as e:
                            print(f"Pixbuf crop error: {e}")

                # Apply on main thread
                GLib.idle_add(self._apply_pixbuf, final_pixbuf, url)

        except Exception as e:
            print(f"Failed to load image {url}: {e}")
            if fallbacks and self.url == url:
                next_url = fallbacks.pop(0)
                self.url = next_url  # Update current URL to match the fallback
                print(f"Trying fallback: {next_url}")
                self._fetch_image(next_url, fallbacks)

    def _apply_pixbuf(self, pixbuf, url=None):
        # Race condition check: only apply if the URL hasn't changed since request
        if url and self.url != url:
            return

        if self.circular:
            self.add_css_class("circular")

        self.set_from_pixbuf(pixbuf)

    def set_from_file(self, file):
        """Optimistically set image from a local file object (GFile)"""
        try:
            # We must load into a pixbuf first to handle scaling correctly
            path = file.get_path()
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, self.target_w, self.target_h, True
            )
            self.set_from_pixbuf(pixbuf)
            # Nullify URL so subsequent async loads don't overwrite this immediately
            self.url = f"file://{path}"
        except Exception as e:
            print(f"Error setting from file: {e}")


def subprocess_pixbuf(pixbuf, x, y, w, h):
    # bindings helper
    return pixbuf.new_subpixbuf(x, y, w, h)


class AsyncPicture(Gtk.Picture):
    # Added crop_to_square parameter
    def __init__(self, url=None, crop_to_square=False, **kwargs):
        super().__init__(**kwargs)
        self.set_content_fit(Gtk.ContentFit.COVER)
        self.crop_to_square = crop_to_square
        self.url = url
        if url:
            self.load_url(url)

    def load_url(self, url, **kwargs):
        self.url = url
        if not url:
            self.set_paintable(None)
            return

        cached_pixbuf = IMG_CACHE.get(url)
        if cached_pixbuf:
            IMG_CACHE.move_to_end(url)

        thread = threading.Thread(
            target=self._fetch_image, args=(url, kwargs.get("fallbacks"), cached_pixbuf)
        )
        thread.daemon = True
        thread.start()

    def _fetch_image(self, url, fallbacks=None, cached_pixbuf=None):
        try:
            pixbuf = cached_pixbuf
            if not pixbuf:
                with urllib.request.urlopen(url) as response:
                    data = response.read()

                loader = GdkPixbuf.PixbufLoader()
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()

            if pixbuf:
                # Force center-crop to a 1:1 square in the worker thread
                if self.crop_to_square:
                    w = pixbuf.get_width()
                    h = pixbuf.get_height()
                    if w != h:
                        size = min(w, h)
                        offset_x = (w - size) // 2
                        offset_y = (h - size) // 2
                        pixbuf = pixbuf.new_subpixbuf(offset_x, offset_y, size, size)

                # Scale down if still too large
                w = pixbuf.get_width()
                h = pixbuf.get_height()
                max_dim = 800
                if w > max_dim or h > max_dim:
                    scale = max_dim / max(w, h)
                    pixbuf = pixbuf.scale_simple(
                        int(w * scale), int(h * scale), GdkPixbuf.InterpType.BILINEAR
                    )

                cache_pixbuf(url, pixbuf)
                GLib.idle_add(self._apply_pixbuf, pixbuf, url)

        except Exception as e:
            print(f"AsyncPicture error {url}: {e}")
            if fallbacks and self.url == url:
                next_url = fallbacks.pop(0)
                self.url = next_url
                print(f"Trying fallback: {next_url}")
                self._fetch_image(next_url, fallbacks)

    def _apply_pixbuf(self, pixbuf, url=None):
        # Race condition check
        if url and self.url != url:
            return

        # Convert to Texture and paint
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        self.set_paintable(texture)


class MarqueeLabel(Gtk.ScrolledWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # EXTERNAL means the content can overflow, but no scrollbars are drawn
        self.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)

        self.label = Gtk.Label()
        self.label.set_halign(Gtk.Align.START)
        self.label.set_valign(Gtk.Align.CENTER)
        self.set_child(self.label)

        # Animation variables
        self._tick_id = 0
        self._pause_frames = 60  # Pause for ~1 second at the edges
        self._current_pause = self._pause_frames
        self._direction = 1  # 1 = scrolling right, -1 = scrolling left

        # Only animate when actually visible on screen
        self.connect("map", self._start_marquee)
        self.connect("unmap", self._stop_marquee)

    def add_css_class(self, class_name):
        # Apply CSS to the actual text label, not the scrolled window container
        self.label.add_css_class(class_name)

    def _start_marquee(self, *args):
        if self._tick_id == 0:
            # Sync to the monitor's frame clock for buttery smooth movement
            self._tick_id = self.add_tick_callback(self._on_tick)

    def _stop_marquee(self, *args):
        if self._tick_id != 0:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = 0

    def _on_tick(self, widget, frame_clock):
        adj = self.get_hadjustment()
        max_val = adj.get_upper() - adj.get_page_size()

        # If the text fits perfectly, don't scroll at all!
        if max_val <= 0:
            adj.set_value(0)
            return True

        # Handle the pause at the edges
        if self._current_pause > 0:
            self._current_pause -= 1
            return True

        # Constant speed of ~50 pixels per second
        # GTK frame clock provides frame time in microseconds
        frame_time = frame_clock.get_frame_time()
        if not hasattr(self, "_last_frame_time"):
            self._last_frame_time = frame_time
            return True

        delta = (frame_time - self._last_frame_time) / 1_000_000.0  # seconds
        self._last_frame_time = frame_time

        # Move text by speed * delta
        speed = 40.0  # px/s
        new_val = adj.get_value() + (speed * delta * self._direction)

        # Reverse direction if we hit an edge
        if new_val >= max_val:
            new_val = max_val
            self._direction = -1
            self._current_pause = self._pause_frames
        elif new_val <= 0:
            new_val = 0
            self._direction = 1
            self._current_pause = self._pause_frames

        adj.set_value(new_val)
        return True

    def set_label(self, text):
        self.label.set_label(text)
        # Reset position and animation state when text changes
        self.get_hadjustment().set_value(0)
        self._current_pause = self._pause_frames
        self._direction = 1
        if hasattr(self, "_last_frame_time"):
            delattr(self, "_last_frame_time")


class LikeButton(Gtk.Button):
    def __init__(self, client, video_id, initial_status="INDIFFERENT", **kwargs):
        super().__init__(**kwargs)
        self.client = client
        self.video_id = video_id
        self.status = initial_status

        self.add_css_class("flat")
        self.add_css_class("circular")
        self.set_valign(Gtk.Align.CENTER)

        self.update_icon()
        self.connect("clicked", self.on_clicked)

    def update_icon(self):
        if self.status == "LIKE":
            self.set_icon_name("starred-symbolic")
            self.add_css_class("liked-button")  # For potential CSS styling
            self.set_tooltip_text("Unlike")
        elif self.status == "DISLIKE":
            self.set_icon_name(
                "view-restore-symbolic"
            )  # Placeholder or specific icon if found
            self.set_tooltip_text("Disliked")
        else:
            self.set_icon_name("non-starred-symbolic")
            self.remove_css_class("liked-button")
            self.set_tooltip_text("Like")

    def on_clicked(self, btn):
        # Toggle: LIKE -> INDIFFERENT, others -> LIKE
        new_status = "INDIFFERENT" if self.status == "LIKE" else "LIKE"

        # Optimistic update
        old_status = self.status
        self.status = new_status
        self.update_icon()

        def do_rate():
            success = self.client.rate_song(self.video_id, new_status)
            if not success:
                # Revert on failure
                GLib.idle_add(self.revert, old_status)

        thread = threading.Thread(target=do_rate)
        thread.daemon = True
        thread.start()

    def revert(self, status):
        self.status = status
        self.update_icon()

    def set_data(self, video_id, status):
        self.video_id = video_id
        self.status = status
        self.update_icon()
        self.set_visible(bool(video_id))
