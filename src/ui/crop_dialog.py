from gi.repository import Gtk, Adw, Gdk, GObject, GdkPixbuf


class ImageCropDialog(Adw.Window):
    def __init__(self, parent, pixbuf):
        super().__init__(title="Edit Playlist Cover", transient_for=parent, modal=True)
        self.set_default_size(540, 680)

        self.original_pixbuf = pixbuf
        self.result_pixbuf = None

        # Scale pixbuf for display if too large
        self.display_scale = 1.0
        max_display_size = 480
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        if w > max_display_size or h > max_display_size:
            self.display_scale = max_display_size / max(w, h)

        self.display_pixbuf = pixbuf.scale_simple(
            int(w * self.display_scale),
            int(h * self.display_scale),
            GdkPixbuf.InterpType.BILINEAR,
        )

        # State
        # Fixed crop size in display space. If image is too small, we reduce crop size.
        img_w = self.display_pixbuf.get_width()
        img_h = self.display_pixbuf.get_height()
        self.crop_size = min(300, img_w, img_h)

        self.offset_x = (img_w - self.crop_size) // 2
        self.offset_y = (img_h - self.crop_size) // 2

        self._is_resizing = False
        self._orig_crop_size = 0

        self._setup_ui()

    def _setup_ui(self):
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # Header
        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title="Crop Playlist Cover")
        header.set_title_widget(title)

        toolbar_view.add_top_bar(header)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.set_valign(Gtk.Align.CENTER)
        toolbar_view.set_content(main_box)

        instructions = Gtk.Label(label="Select the square area you want to use.")
        instructions.add_css_class("title-3")
        main_box.append(instructions)

        # Frame for DrawingArea
        frame = Gtk.Frame()
        frame.set_halign(Gtk.Align.CENTER)
        frame.set_valign(Gtk.Align.CENTER)
        main_box.append(frame)

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_draw_func(self._on_draw)
        self.drawing_area.set_size_request(480, 480)
        frame.set_child(self.drawing_area)

        # Gestures
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        self.drawing_area.add_controller(drag)

        # Footer Action Bar (Bottom bar)
        footer_bar = Gtk.ActionBar()
        toolbar_view.add_bottom_bar(footer_bar)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda b: self.close())
        footer_bar.pack_start(cancel_btn)

        apply_btn = Gtk.Button(label="Save & Use PNG")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply)
        footer_bar.pack_end(apply_btn)

        self._orig_offset_x = 0
        self._orig_offset_y = 0

    def _on_draw(self, area, cr, width, height):
        # Center the image in the drawing area
        img_w = self.display_pixbuf.get_width()
        img_h = self.display_pixbuf.get_height()

        draw_x = (width - img_w) / 2
        draw_y = (height - img_h) / 2

        # Draw Checkerboard Background (for PNGs with transparency)
        cr.save()
        cr.set_source_rgb(0.9, 0.9, 0.9)  # Light gray
        cr.rectangle(draw_x, draw_y, img_w, img_h)
        cr.fill()
        cr.restore()

        # Draw image
        Gdk.cairo_set_source_pixbuf(cr, self.display_pixbuf, draw_x, draw_y)
        cr.paint()

        # Draw dim overlay
        cr.set_source_rgba(0, 0, 0, 0.6)  # Slightly darker for premium feel

        # Left
        cr.rectangle(draw_x, draw_y, self.offset_x, img_h)
        # Right
        cr.rectangle(
            draw_x + self.offset_x + self.crop_size,
            draw_y,
            img_w - self.offset_x - self.crop_size,
            img_h,
        )
        # Top
        cr.rectangle(draw_x + self.offset_x, draw_y, self.crop_size, self.offset_y)
        # Bottom
        cr.rectangle(
            draw_x + self.offset_x,
            draw_y + self.offset_y + self.crop_size,
            self.crop_size,
            img_h - self.offset_y - self.crop_size,
        )

        cr.fill()

        # Draw square border (White with drop shadow effect)
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.set_line_width(2)
        cr.rectangle(
            draw_x + self.offset_x,
            draw_y + self.offset_y,
            self.crop_size,
            self.crop_size,
        )
        cr.stroke()

        # Draw resize handle (Small circle at bottom-right corner)
        handle_x = draw_x + self.offset_x + self.crop_size
        handle_y = draw_y + self.offset_y + self.crop_size

        cr.set_source_rgba(1, 1, 1, 1.0)
        cr.arc(
            handle_x, handle_y, 8, 0, 2 * 3.14159
        )  # GObject doesn't have math.pi easily? I'll use 6.28
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.set_line_width(1)
        cr.arc(handle_x, handle_y, 8, 0, 2 * 3.14159)
        cr.stroke()

    def _on_drag_begin(self, gesture, start_x, start_y):
        # Center coordinates
        width = self.drawing_area.get_width()
        height = self.drawing_area.get_height()
        img_w = self.display_pixbuf.get_width()
        img_h = self.display_pixbuf.get_height()
        draw_x = (width - img_w) / 2
        draw_y = (height - img_h) / 2

        # Check if click is near bottom-right handle
        handle_x = draw_x + self.offset_x + self.crop_size
        handle_y = draw_y + self.offset_y + self.crop_size

        dist = ((start_x - handle_x) ** 2 + (start_y - handle_y) ** 2) ** 0.5

        if dist < 30:  # 30px radius for hit detection
            self._is_resizing = True
            self._orig_crop_size = self.crop_size
        else:
            self._is_resizing = False
            self._orig_offset_x = self.offset_x
            self._orig_offset_y = self.offset_y

    def _on_drag_update(self, gesture, offset_x, offset_y):
        img_w = self.display_pixbuf.get_width()
        img_h = self.display_pixbuf.get_height()

        if self._is_resizing:
            # Resize from bottom-right: new size is based on largest offset
            # (To maintain square aspect ratio)
            move = max(offset_x, offset_y)
            new_size = self._orig_crop_size + move

            # Constraints:
            # 1. Min size
            new_size = max(50, new_size)
            # 2. Stay within image width from current offset_x
            new_size = min(new_size, img_w - self.offset_x)
            # 3. Stay within image height from current offset_y
            new_size = min(new_size, img_h - self.offset_y)

            self.crop_size = new_size
        else:
            # Existing move logic
            new_x = self._orig_offset_x + offset_x
            new_y = self._orig_offset_y + offset_y

            self.offset_x = max(0, min(new_x, img_w - self.crop_size))
            self.offset_y = max(0, min(new_y, img_h - self.crop_size))

        self.drawing_area.queue_draw()

    def _on_apply(self, btn):
        # Calculate real coordinates on the original high-res pixbuf
        real_x = int(self.offset_x / self.display_scale)
        real_y = int(self.offset_y / self.display_scale)
        real_size = int(self.crop_size / self.display_scale)

        # Final safety bounds check
        real_x = max(0, min(real_x, self.original_pixbuf.get_width() - real_size))
        real_y = max(0, min(real_y, self.original_pixbuf.get_height() - real_size))

        if real_size > 0:
            cropped = self.original_pixbuf.new_subpixbuf(
                real_x, real_y, real_size, real_size
            )
            # Rescale to exactly 512x512
            self.result_pixbuf = cropped.scale_simple(
                512, 512, GdkPixbuf.InterpType.BILINEAR
            )

        self.emit("response", Gtk.ResponseType.OK)
        self.close()


GObject.signal_new(
    "response", ImageCropDialog, GObject.SignalFlags.RUN_FIRST, None, (int,)
)
