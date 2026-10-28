#!/usr/bin/python3.8
# python3.8 explicite : le binding gi du système est compilé pour 3.8, python3 pointe sur 3.9 ici.
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.0")
from gi.repository import Gdk, GLib, Gtk, WebKit2

# rotate=180 : le speeder-pad est posé tête en bas pour que ses ports soient côté imprimante.
URL = "http://127.0.0.1:8090/?rotate=180"
RETRY_SECONDS = 3


def retry_load(view, *_args):
    # Le serveur local démarre en même temps que le navigateur : premier chargement souvent trop tôt.
    GLib.timeout_add_seconds(RETRY_SECONDS, lambda: view.load_uri(URL) or False)
    return True


def hide_cursor(window):
    gdk_window = window.get_window()
    if gdk_window is not None:
        blank = Gdk.Cursor.new_for_display(gdk_window.get_display(), Gdk.CursorType.BLANK_CURSOR)
        gdk_window.set_cursor(blank)


def main():
    window = Gtk.Window()
    # Aucun gestionnaire de fenêtres sous xinit : fullscreen() seul est ignoré, la fenêtre garde sa taille par défaut.
    screen = Gdk.Screen.get_default()
    window.set_decorated(False)
    window.set_default_size(screen.get_width(), screen.get_height())
    window.move(0, 0)
    window.fullscreen()
    window.connect("destroy", Gtk.main_quit)
    window.connect("realize", hide_cursor)

    view = WebKit2.WebView()
    settings = view.get_settings()
    settings.set_enable_developer_extras(False)
    # Pas de GL fiable sur ce SoC : le rendu logiciel évite les écrans noirs.
    settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
    view.connect("context-menu", lambda *_: True)
    view.connect("load-failed", retry_load)
    view.load_uri(URL)

    window.add(view)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
