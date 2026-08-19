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
  cargo tauri build

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

package-handoff:
  python3 tools/package_release.py --build-handoff

[windows]
package:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/package_release.py

[windows]
package-handoff:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/python.ps1 tools/package_release.py --build-handoff

release: release-clean fmt-check lint check test build release-clean package

[unix]
clean:
  rm -rf dist release src-tauri/target

[windows]
clean:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools/clean.ps1
