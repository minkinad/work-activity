import { cpSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = join(root, "dist");

rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });
cpSync(join(root, "index.html"), join(output, "index.html"));
cpSync(join(root, "styles.css"), join(output, "styles.css"));
cpSync(join(root, "src"), join(output, "src"), { recursive: true });

console.log(`Built static dashboard in ${output}`);
