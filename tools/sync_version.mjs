import fs from "node:fs";

const raw = process.argv[2] ?? process.env.GITHUB_REF_NAME ?? "";
const version = raw.replace(/^v/, "");
if (!/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error(`invalid release version/tag: ${raw || "<empty>"}`);
}

function writeJson(path, mutate) {
  const value = JSON.parse(fs.readFileSync(path, "utf8"));
  mutate(value);
  fs.writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

writeJson("src-tauri/tauri.conf.json", (tauri) => {
  tauri.version = version;
});

writeJson("package.json", (pkg) => {
  pkg.version = version;
});

writeJson("package-lock.json", (lock) => {
  lock.version = version;
  if (!lock.packages?.[""]) throw new Error("package-lock.json has no root package");
  lock.packages[""].version = version;
});

const cargoPath = "src-tauri/Cargo.toml";
const cargo = fs.readFileSync(cargoPath, "utf8");
const updatedCargo = cargo.replace(/^version = ".*"/m, `version = "${version}"`);
if (updatedCargo === cargo && !cargo.includes(`version = "${version}"`)) {
  throw new Error("unable to update Cargo.toml package version");
}
fs.writeFileSync(cargoPath, updatedCargo);

const cargoLockPath = "src-tauri/Cargo.lock";
const cargoLock = fs.readFileSync(cargoLockPath, "utf8");
// Windows Git checkouts may use CRLF. Match either delimiter and preserve the
// original bytes outside the version, including on already-synchronized runs.
const cargoLockVersion = /(\[\[package\]\]\r?\nname = "tauridium"\r?\nversion = ")[^"]+("\r?\n)/;
if (!cargoLockVersion.test(cargoLock)) {
  throw new Error("unable to update Cargo.lock Tauridium package version");
}
const updatedCargoLock = cargoLock.replace(cargoLockVersion, `$1${version}$2`);
fs.writeFileSync(cargoLockPath, updatedCargoLock);

const initPath = "tools/init.py";
const initSource = fs.readFileSync(initPath, "utf8");
const updatedInit = initSource.replace(/^INIT_VERSION = ".*"/m, `INIT_VERSION = "${version}"`);
if (updatedInit === initSource && !initSource.includes(`INIT_VERSION = "${version}"`)) {
  throw new Error("unable to update initializer version");
}
fs.writeFileSync(initPath, updatedInit);

const initPs1Path = "tools/init.ps1";
const initPs1Source = fs.readFileSync(initPs1Path, "utf8");
const updatedInitPs1 = initPs1Source.replace(/^\$InitVersion = ".*"/m, `$InitVersion = "${version}"`);
if (updatedInitPs1 === initPs1Source && !initPs1Source.includes(`$InitVersion = "${version}"`)) {
  throw new Error("unable to update PowerShell initializer version");
}
fs.writeFileSync(initPs1Path, updatedInitPs1);

const readmePath = "README.md";
const readme = fs.readFileSync(readmePath, "utf8");
// Keep README examples generic where possible. If a target-qualified runtime example
// contains a concrete release version, synchronize it without requiring such an example.
const updatedReadme = readme.replace(
  /tauridium-\d+\.\d+\.\d+-run-/g,
  `tauridium-${version}-run-`,
);
if (updatedReadme !== readme) {
  fs.writeFileSync(readmePath, updatedReadme);
}

// Keep copyable Nix consumption examples on the same immutable release as the app.
for (const path of ["docs/NIX.md", "docs/examples/nix/flake.nix"]) {
  const source = fs.readFileSync(path, "utf8");
  const updated = source
    .replace(/github:Akkitto\/Tauridium\/v\d+\.\d+\.\d+/g, `github:Akkitto/Tauridium/v${version}`)
    .replace(/v\d+\.\d+\.\d+ cannot discover/g, `v${version} cannot discover`);
  if (updated !== source) fs.writeFileSync(path, updated);
}

console.log(`Tauridium release identity -> ${version}`);
