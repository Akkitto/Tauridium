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

lint:
  cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features -- -D warnings

[unix]
check:
  npm run check
  cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features
  python3 tools/validate_release.py

[windows]
check:
  npm run check
  cargo check --manifest-path src-tauri/Cargo.toml --all-targets --all-features
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/validate_release.py

[unix]
test:
  python3 -m unittest discover -s tools -p 'test_*.py'
  npm test
  cargo test --manifest-path src-tauri/Cargo.toml --all-features

[windows]
test:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 -m unittest discover -s tools -p "test_*.py"
  npm test
  cargo test --manifest-path src-tauri/Cargo.toml --all-features

build:
  npm run build
  cargo build --manifest-path src-tauri/Cargo.toml --release --all-features

bundle:
  cargo tauri build

run:
  cargo tauri dev

audit:
  npm audit --audit-level=high
  cargo audit

doc:
  cargo doc --manifest-path src-tauri/Cargo.toml --no-deps --all-features

[unix]
package:
  python3 tools/package_release.py

[windows]
package:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/package_release.py

release: fmt lint check test build package

[unix]
clean:
  rm -rf dist release src-tauri/target

[windows]
clean:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/clean.ps1
