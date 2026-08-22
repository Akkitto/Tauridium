set minimum-version := "1.56.0"

[unix]
set shell := ["sh", "-eu", "-c"]

[windows]
set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"]

default:
  @just --list

[unix]
init:
  python3 tools/init.py

[windows]
init:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/init.ps1

[unix]
init-native:
  python3 tools/init.py --native-only

[windows]
init-native:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/init.ps1 -NativeOnly

[windows]
init-self-test:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/init.ps1 -SelfTest

fmt:
  cargo fmt --manifest-path src-tauri/Cargo.toml --all

fmt-check:
  cargo fmt --manifest-path src-tauri/Cargo.toml --all -- --check

lint:
  cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked -- -D warnings

[unix]
check:
  npm run check
  cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked
  python3 tools/validate_release.py

[windows]
check:
  npm run check
  cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features --locked
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/validate_release.py

[unix]
test:
  python3 -m unittest discover -s tools -p 'test_*.py'
  npm test
  cargo test --manifest-path src-tauri/Cargo.toml --all-features --locked

[windows]
test:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 -m unittest discover -s tools -p "test_*.py"
  npm test
  cargo test --manifest-path src-tauri/Cargo.toml --all-features --locked

build:
  cargo tauri build --no-bundle --ci

bundle:
  cargo tauri build --ci

bundle-target target:
  cargo tauri build --ci --target {{target}}

run:
  cargo tauri dev

audit:
  npm audit --audit-level=high
  cargo audit

doc:
  cargo doc --manifest-path src-tauri/Cargo.toml --no-deps --all-features --locked

[unix]
release-clean:
  python3 tools/check_clean.py

[windows]
release-clean:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/check_clean.py

[unix]
package:
  python3 tools/package_release.py

[unix]
package-handoff:
  python3 tools/package_release.py --build-handoff

[windows]
package:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/package_release.py

[windows]
package-handoff:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/package_release.py --build-handoff

quality: fmt-check lint check test

ci: quality build

release: release-clean ci
  just release-clean
  just package

[unix]
package-native target:
  python3 tools/release_assets.py collect-native --target {{target}} --output-dir release/native

[windows]
package-native target:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/release_assets.py collect-native --target {{target}} --output-dir release/native

[unix]
package-native-signed target:
  python3 tools/release_assets.py collect-native --target {{target}} --output-dir release/native --require-signatures

[windows]
package-native-signed target:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/release_assets.py collect-native --target {{target}} --output-dir release/native --require-signatures

[unix]
release-notes output="release/release-notes.md":
  python3 tools/release_assets.py release-notes --output {{output}}

[windows]
release-notes output="release/release-notes.md":
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/release_assets.py release-notes --output {{output}}

[unix]
updater-manifest assets_dir="release/published-assets":
  python3 tools/release_assets.py updater-manifest --assets-dir {{assets_dir}} --require-all

[windows]
updater-manifest assets_dir="release/published-assets":
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/release_assets.py updater-manifest --assets-dir {{assets_dir}} --require-all

[unix]
release-checksums assets_dir="release/published-assets":
  python3 tools/release_assets.py checksums --assets-dir {{assets_dir}}

[windows]
release-checksums assets_dir="release/published-assets":
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/release_assets.py checksums --assets-dir {{assets_dir}}

[unix]
clean:
  rm -rf dist release src-tauri/target

[windows]
clean:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/clean.ps1
