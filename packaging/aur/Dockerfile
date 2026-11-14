# Rolling Arch dependency validation, isolated from host profiles and credentials.
FROM archlinux:base-devel@sha256:fa2d4ce3310ddd90a4208e5168be8ad367da5129af1245f38fd2d803bcbe3239
RUN pacman -Syu --noconfirm --needed rust nodejs npm python gtk3 webkit2gtk-4.1 \
      libayatana-appindicator xdotool xdg-utils glib-networking gst-plugins-base \
      gst-plugins-good gst-plugins-bad gst-libav namcap desktop-file-utils appstream \
      unzip dbus xorg-server-xvfb xorg-xauth imagemagick tesseract tesseract-data-eng \
    && useradd --create-home builder
