{
  description = "Python development setup with Nix for Muse project";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, utils }:
    utils.lib.eachDefaultSystem (system:
      let pkgs = import nixpkgs { inherit system; }; in {
      devShell = with pkgs;
         mkShell {
            packages = [ 
              # UI
              gtk4
              libadwaita
              # GStreamer
              gst_all_1.gstreamer
              gst_all_1.gst-plugins-base
              gst_all_1.gst-plugins-good
              gst_all_1.gst-plugins-bad
              gst_all_1.gst-plugins-ugly
              # Python dependencies
              python311
              python311Packages.pygobject3
              python311Packages.ytmusicapi
              python311Packages.yt-dlp
              python311Packages.requests
              nodejs
            ];
          shellHook = ''
            python --version
          '';
         };
      }
   );
}
