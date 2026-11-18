#define _POSIX_C_SOURCE 200809L
#include <wayland-client.h>

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* This private test client implements version 1 of wlroots' virtual-pointer
 * protocol. Keep the device alive across requests: immediately disconnecting a
 * virtual pointer can remove GTK's seat capability before WebKit sees a click. */
static const struct wl_interface pointer_interface;
static const struct wl_interface *create_types[] = {
    &wl_seat_interface, &pointer_interface,
};
static const struct wl_message manager_requests[] = {
    {"create_virtual_pointer", "?on", create_types},
    {"destroy", "", NULL},
};
static const struct wl_interface manager_interface = {
    "zwlr_virtual_pointer_manager_v1", 1, 2, manager_requests, 0, NULL,
};
static const struct wl_message pointer_requests[] = {
    {"motion", "uff", NULL},
    {"motion_absolute", "uuuuu", NULL},
    {"button", "uuu", NULL},
    {"axis", "uuf", NULL},
    {"frame", "", NULL},
    {"axis_source", "u", NULL},
    {"axis_stop", "uu", NULL},
    {"axis_discrete", "uufi", NULL},
    {"destroy", "", NULL},
};
static const struct wl_interface pointer_interface = {
    "zwlr_virtual_pointer_v1", 1, 9, pointer_requests, 0, NULL,
};
static struct wl_proxy *manager;

static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version) {
    (void)data;
    (void)version;
    if (!strcmp(interface, manager_interface.name)) {
        manager = wl_registry_bind(registry, name, &manager_interface, 1);
    }
}

static void global_remove(void *data, struct wl_registry *registry, uint32_t name) {
    (void)data;
    (void)registry;
    (void)name;
}

static uint32_t timestamp(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
        perror("clock_gettime");
        exit(1);
    }
    return (uint32_t)((uint64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000);
}

int main(int argc, char **argv) {
    unsigned width, height;
    char extra;
    if (argc != 3 || sscanf(argv[1], "%u%c", &width, &extra) != 1 ||
        sscanf(argv[2], "%u%c", &height, &extra) != 1 ||
        !width || !height || width > 16384 || height > 16384) {
        fprintf(stderr, "Usage: tauridium-wayland-input WIDTH HEIGHT\n");
        return 2;
    }
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) {
        perror("connect private Wayland display");
        return 1;
    }
    struct wl_registry *registry = wl_display_get_registry(display);
    const struct wl_registry_listener listener = {global, global_remove};
    wl_registry_add_listener(registry, &listener, NULL);
    if (wl_display_roundtrip(display) < 0 || !manager) {
        fprintf(stderr, "Private compositor has no virtual-pointer protocol\n");
        wl_display_disconnect(display);
        return 1;
    }
    struct wl_proxy *pointer = wl_proxy_marshal_flags(
        manager, 0, &pointer_interface, 1, 0, NULL, NULL);
    if (!pointer || wl_display_roundtrip(display) < 0) {
        fprintf(stderr, "Cannot initialize virtual pointer\n");
        wl_display_disconnect(display);
        return 1;
    }
    setvbuf(stdout, NULL, _IONBF, 0);
    puts("READY");
    char line[128];
    int result = 0;
    while (fgets(line, sizeof(line), stdin)) {
        unsigned first, second;
        if (sscanf(line, "move %u %u %c", &first, &second, &extra) == 2 &&
            first < width && second < height) {
            wl_proxy_marshal_flags(pointer, 1, NULL, 1, 0, timestamp(),
                                   first, second, width, height);
        } else if (sscanf(line, "button %u %u %c", &first, &second, &extra) == 2 &&
                   first >= 272 && first <= 279 && second <= 1) {
            wl_proxy_marshal_flags(pointer, 2, NULL, 1, 0,
                                   timestamp(), first, second);
        } else if (!strcmp(line, "quit\n")) {
            break;
        } else {
            fprintf(stderr, "Invalid pointer command: %s", line);
            result = 2;
            break;
        }
        wl_proxy_marshal_flags(pointer, 4, NULL, 1, 0);
        if (wl_display_roundtrip(display) < 0) {
            fprintf(stderr, "Private compositor disconnected\n");
            result = 1;
            break;
        }
        puts("DONE");
    }
    wl_proxy_marshal_flags(pointer, 8, NULL, 1, WL_MARSHAL_FLAG_DESTROY);
    wl_proxy_marshal_flags(manager, 1, NULL, 1, WL_MARSHAL_FLAG_DESTROY);
    wl_registry_destroy(registry);
    wl_display_flush(display);
    wl_display_disconnect(display);
    return result;
}
