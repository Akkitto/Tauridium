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
const updatedCargoLock = cargoLock.replace(
  /(\[\[package\]\]\nname = "tauridium"\nversion = ")[^"]+("\n)/,
  `$1${version}$2`,
);
if (updatedCargoLock === cargoLock && !cargoLock.includes(`name = "tauridium"\nversion = "${version}"`)) {
  throw new Error("unable to update Cargo.lock Tauridium package version");
}
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

console.log(`Tauridium release identity -> ${version}`);
