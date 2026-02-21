# Mixtapes (formerly Muse)

A modern, Linux-first YouTube Music player.

> [!NOTE]
> This software is considered in alpha stage. Expect bugs and a lot of missing features.
> It is also not affiliated with, funded, authorized, endorsed, or in any way associated with YouTube, Google LLC or any of their affiliates and subsidiaries.
> Help is always appreciated, so feel free to open an issue or a pull request.

![Mixtapes](screenshots/1.png)
![Mixtapes](screenshots/2.png)
![Mixtapes](screenshots/3.png)

## Roadmap

This is a list of all the features that are planned for Mixtapes:

[x] means the feature is implemented.
[-] means the feature is partially implemented.
[_] means the feature is not implemented yet, but planned.
[*] means the feature will likely not be implemented.

- [x] **Authentication**: Connect to YouTube Music (Browser cookies).
- [_] **Home Page**: View charts and explore new music.
- [-] **Library**: Access your playlists and liked songs.
  - [-] Playlists
    > Read only, cannot create or edit playlists yet.
  - [x] Liked songs
- [x] **Search**: Search for songs, albums, and artists.
- [-] **Artist Page**: View artist details and discography.
  - [x] Basic artist info.
  - [_] Artist related artists.
  - [-] Artist top tracks.
    > Currently only the first 5 tracks are shown, need to implement a "Show more" button as seen in the Web Player which would let you see the entire discography as well.
  - [-] Artist albums.
    > Only the first 10 albums are shown, need to implement a "Show more" button.
  - [-] Artist singles.
    > Only the first 10 singles are shown, need to implement a "Show more" button.
  - [-] Artist videos.
    > Only the first 10 videos are shown, need to implement a "Show more" button.
  - [-] Artist Play button
    > The button works, but only plays the top 5 tracks.
  - [-] Artist Shuffle button
    > The button works, but only plays the top 5 tracks in a random order.
  - [_] Artist Subscribe/Unsubscribe button
    > This button should subscribe/unsubscribe the artist, not implemented yet.
- [-] **Playlist Page**: View and play playlists.
  - [x] Basic playlist info.
  - [x] Playlist tracks.
  - [x] Playlist Play button
  - [x] Playlist Shuffle button
  - [x] Playlist Order
  - [x] Playlist Cover Change
    > Currently the playlist cover can be changed, however, changing it in the app isn't fully added.
  - [_] Playlist Change Visibility
    > Currently the playlist visibility cannot be changed.
  - [_] Playlist Change Description
    > Currently the playlist description cannot be changed.
  - [_] Playlist Change Name
    > Currently the playlist name cannot be changed.
- [x] **Album Page**: View and play albums.
  - [x] Basic album info.
  - [x] Album tracks.
  - [x] Album Play button
  - [x] Album Shuffle button
- [-] **Player**: Full playback control with queue management.
  - [x] Play/Pause
  - [x] Seeking
  - [-] Queue
    - [x] Previous/Next
    - [x] Change order of song
    - [x] Shuffle
    - [_] Repeat modes (single track, loop queue)
  - [x] Volume control
- [_] **Caching**: Cache data to reduce latency and bandwidth usage
- [-] **Responsive Design**: Mobile-friendly layout with adaptive UI.
  > Desktop needs to use the empty space better.
- [_] **MPRIS Support**: Control playback from system media controls.
- [_] **Discord RPC**: Show your current track on Discord.
- [_] **Lyrics**: View synchronized lyrics, maybe even using BetterLyrics API.
- [_] **Settings**: Configure app preferences (theme, audio quality, etc.).
- [_] **Download Support**: Download tracks for offline playback, even as local files.
- [_] **Radio / Mixes**: Start a radio station from a song or artist.
- [_] **Dedicated Data Directory**: Move all the data like cookies, cache, etc. to a dedicated directory instead of the project root directory.
- [_] **Background Playback**: Play music in the background, even when the main window is closed.
- [-] **Flatpak**: Package Mixtapes as a Flatpak.
  - [x] Flatpak build
  - [-] Flathub release
  - [-] App icon
- [_] **AppImage**: Package Mixtapes as an AppImage.
- [x] **AUR**: Package Mixtapes as an AUR package.

If you got any more ideas or bug reports, feel free to open an issue.

## Prerequisites

- Python 3.10 or higher
- Node.js (needed for yt-dlp-ejs, helps with playback issues)
- GTK4 (including development headers)
- Libadwaita (including development headers)
- GStreamer plugins (base, good, bad, ugly)

## Installation

Currently, there are three options for installing Mixtapes:

- From Source
- Using a Nix flake
- Using flatpak-builder

### AUR

If you are using Arch Linux, you can install Mixtapes from the AUR.
An AUR helper like `yay` or `paru` is recommended.

```bash
yay -S mixtapes-git
```

### From Source

Before you start, make sure to install the dependencies.

Here are install commands for some common package managers:

- Arch Linux: `sudo pacman -S git python-pip nodejs gtk4 libadwaita gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly`

- Debian/Ubuntu: `sudo apt install git python3 python3-pip nodejs libgtk-4-dev libadwaita-1-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly`

> [!NOTE]
> If you are on Debian/Ubuntu, you should probably use Flatpak to avoid outdated packages.

- Fedora: `sudo dnf install git python3 python3-pip nodejs gtk4-devel adwaita-gtk4-devel gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugins-bad gstreamer1-plugins-ugly`

1. Clone the repository:

   ```bash
   git clone https://github.com/m-obeid/Muse.git
   cd Muse
   ```

2. Install Python dependencies within a virtual environment:

   ```bash
   python3 -m venv .venv --system-site-packages
   source .venv/bin/activate
   pip install -r requirements.txt
   chmod +x start.sh
   ```

3. Run the app:
   ```bash
   ./start.sh
   ```

To pull the latest changes:

```bash
git pull
pip install -r requirements.txt
```

### Nix

A Nix flake is available for NixOS or Nix Package Manager users.
See [here](https://github.com/m-obeid/Muse/pull/2#issue-3965386248)

### Flatpak

1. Install Flatpak and required runtimes:

   ```bash
   flatpak install flathub org.gnome.Platform//49 org.gnome.Sdk//49 org.freedesktop.Sdk.Extension.node24//24.08
   ```

2. Clone the repository:

   ```bash
   git clone https://github.com/m-obeid/Muse.git
   cd Muse
   ```

3. Build and install:

   ```bash
   flatpak-builder --user --install --force-clean build-dir com.pocoguy.Muse.yaml
   ```

4. Run:
   ```bash
   flatpak run com.pocoguy.Muse
   ```

**Authentication:** Open your browser, go to YouTube Music, and copy request headers as described [here](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html).
Then run `flatpak run --command=sh com.pocoguy.Muse` and inside the shell run `mkdir -p ~/data/Muse && cd ~/data/Muse && ytmusicapi browser`.
Paste the headers and press Ctrl-D.

## Authentication

This app uses `ytmusicapi` for backend data. Authentication allows access to your library and higher quality streams.

To authenticate, you need to generate a `browser.json` file.

- Run: `ytmusicapi browser`
- Follow instructions to log in via your browser and paste the headers. It is recommended to use a private browser profile for this, so that you don't get logged out of the account from the app.
- The output will be saved as `browser.json` in the project root directory.

If you don't have a `browser.json` file, the app will use the unauthenticated API, which can cause playback issues.

The OAuth flow is currently borked in `ytmusicapi`, don't use it. I removed it from the app, but there might be some leftover code.

## License

GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. See [LICENSE](LICENSE) for details.
