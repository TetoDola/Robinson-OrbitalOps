import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(
  path.join(__dirname, "../docs/research/source.html"),
  "utf8",
);

const urlRe = /https:\/\/[^\s"'<>]+\.(webp|png|jpg|jpeg|svg|mp4|woff2?)/gi;
const urls = [...new Set([...html.matchAll(urlRe)].map((m) => m[0]))];
console.log("URLs found:", urls.length);
urls.slice(0, 100).forEach((u) => console.log(u));

const fontRe = /--font-[a-z-]+:[^;]+/g;
const fonts = [...new Set([...html.matchAll(fontRe)].map((m) => m[0]))];
console.log("\nFonts:");
fonts.forEach((f) => console.log(f));
