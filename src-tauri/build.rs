fn main() {
    // A release-profile Tauri binary built without the production custom protocol loads build.devUrl.
    // Fail fast so a raw cargo release build can never be mistaken for a distributable runtime.
    if std::env::var("PROFILE").as_deref() == Ok("release") && tauri_build::is_dev() {
        panic!(
            "Refusing a development-mode release binary. Build distributable Tauridium runtimes with cargo tauri build --no-bundle --ci."
        );
    }

    tauri_build::build();
}
