import fs from "node:fs";
import path from "node:path";

const cwd = process.cwd();
const srcDir = path.join(cwd, "src");

console.log("[verify-src] build cwd:", cwd);

if (!fs.existsSync(srcDir)) {
  console.error("[verify-src] MISSING directory:", srcDir);
  console.error("[verify-src] cwd contents:", fs.readdirSync(cwd));
  process.exit(1);
}

const listing = fs.readdirSync(srcDir);
console.log("[verify-src] src/ contains:", listing.join(", "));

const required = ["router.tsx", "routeTree.gen.ts", "server.ts", "start.ts"];
for (const file of required) {
  const full = path.join(srcDir, file);
  if (!fs.existsSync(full)) {
    console.error("[verify-src] MISSING file:", full);
    process.exit(1);
  }
}

console.log("[verify-src] OK — required entry files found");
