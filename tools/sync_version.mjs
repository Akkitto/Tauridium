import fs from "node:fs";

const raw = process.argv[2] ?? process.env.GITHUB_REF_NAME ?? "";
const version = raw.replace(/^v/, "");
if (!/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error(`invalid release version/tag: ${raw || "<empty>"}`);
}

const tauriPath = "src-tauri/tauri.conf.json";
const tauri = JSON.parse(fs.readFileSync(tauriPath, "utf8"));
tauri.version = version;
fs.writeFileSync(tauriPath, `${JSON.stringify(tauri, null, 2)}\n`);

const cargoPath = "src-tauri/Cargo.toml";
const cargo = fs.readFileSync(cargoPath, "utf8");
const updated = cargo.replace(/^version = ".*"/m, `version = "${version}"`);
if (updated === cargo && !cargo.includes(`version = "${version}"`)) {
  throw new Error("unable to update Cargo.toml package version");
}
fs.writeFileSync(cargoPath, updated);

console.log(`App version -> ${version}`);
