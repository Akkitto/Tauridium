fn main() {
    let is_dev = tauri_build::is_dev();
    let build_mode = if is_dev { "development" } else { "production" };
    println!("cargo:rustc-env=TAURIDIUM_BUILD_MODE={build_mode}");
    let target = std::env::var("TARGET").expect("Cargo TARGET is required");
    println!("cargo:rustc-env=TAURIDIUM_TARGET={target}");
    println!("cargo:rerun-if-env-changed=TAURIDIUM_MAINTAINER");
    let maintainer =
        std::env::var("TAURIDIUM_MAINTAINER").unwrap_or_else(|_| "Mathieu Vedie".into());
    println!("cargo:rustc-env=TAURIDIUM_MAINTAINER={maintainer}");

    // A release-profile Tauri binary built without the production custom protocol loads build.devUrl.
    // Fail fast so a raw cargo release build can never be mistaken for a distributable runtime.
    if std::env::var("PROFILE").as_deref() == Ok("release") && is_dev {
        panic!(
            "Refusing a development-mode release binary. Build distributable Tauridium runtimes with cargo tauri build --no-bundle --ci."
        );
    }

    tauri_build::build();
}
