const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const dist = path.join(root, "dist");
const files = ["index.html", "app.js", "styles.css", "server.py", "case_store.py", "requirements.txt", "README.md", ".env.example", "vercel.json"];
const directories = ["api"];

fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist, { recursive: true });

for (const file of files) {
  const source = path.join(root, file);
  if (!fs.existsSync(source)) {
    throw new Error(`Missing required release file: ${file}`);
  }
  fs.copyFileSync(source, path.join(dist, file));
}

for (const directory of directories) {
  const source = path.join(root, directory);
  if (!fs.existsSync(source)) {
    throw new Error(`Missing required release directory: ${directory}`);
  }
  fs.cpSync(source, path.join(dist, directory), { recursive: true });
}

const requiredAssets = ["/styles.css", "/app.js"];
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
for (const asset of requiredAssets) {
  if (!html.includes(asset)) {
    throw new Error(`index.html does not reference ${asset}`);
  }
}
