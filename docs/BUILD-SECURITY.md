# Build security

## JavaScript installation

Implicit dependency lifecycle scripts are disabled, including on npm 10. The
project .npmrc protects ordinary manual npm ci; both native initializers and the
Flatpak build also pass --ignore-scripts explicitly. Nix sets the corresponding
build environment policy and includes .npmrc in its source fileset. A caller's
unsafe npm_config_ignore_scripts=false cannot override the bootstrap CLI flag.

Unsupported allowScripts metadata is not used as a security boundary. The shared
tools/npm_policy.py validator rejects root installation hooks and unexpected
dependency hook metadata before installation. The locked esbuild and optional
macOS fsevents install hooks are recognized in the lockfile but never executed.
esbuild uses the native executable in its locked optional platform package; the
initializer verifies it with npm exec --offline -- esbuild --version. Missing or
unsupported platform binaries fail visibly rather than triggering a downloader.

Explicit reviewed npm run build/check/test commands still work. This policy is
not a claim that a compiler or directly invoked build dependency is harmless:
source review, integrity-locked dependencies, current advisory gates and protected
signing custody remain separate requirements. Never put release credentials in a
generic build environment or upload an entire ignored output directory.

The real npm regression has a harmless, authored positive control proving a hook
would run when enabled, then verifies that both the explicit bootstrap flag and
the project default prevent execution. It does not execute untrusted third-party
code to perform the security scan.
