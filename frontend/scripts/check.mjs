import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(join(root, "index.html"), "utf8");
const failures = [];

function collectJavaScript(directory) {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) {
            return collectJavaScript(path);
        }
        return entry.name.endsWith(".js") || entry.name.endsWith(".mjs") ? [path] : [];
    });
}

for (const required of ["lang=\"ru\"", "Content-Security-Policy", "type=\"module\""]) {
    if (!html.includes(required)) {
        failures.push(`index.html is missing ${required}`);
    }
}

const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1]);
const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
if (duplicates.length) {
    failures.push(`duplicate HTML ids: ${[...new Set(duplicates)].join(", ")}`);
}

if (/\son[a-z]+\s*=/i.test(html)) {
    failures.push("inline event handlers are forbidden");
}

for (const match of html.matchAll(/<(?:script|link)[^>]+(?:src|href)="(\.\/[^"?#]+)"/g)) {
    const target = resolve(root, match[1]);
    if (!existsSync(target)) {
        failures.push(`referenced asset does not exist: ${match[1]}`);
    }
}

for (const path of collectJavaScript(join(root, "src"))) {
    const source = readFileSync(path, "utf8");
    for (const forbidden of ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("]) {
        if (source.includes(forbidden)) {
            failures.push(`${relative(root, path)} uses forbidden DOM API ${forbidden}`);
        }
    }
    const syntax = spawnSync(process.execPath, ["--check", path], { encoding: "utf8" });
    if (syntax.status !== 0) {
        failures.push(`${relative(root, path)} failed syntax check:\n${syntax.stderr}`);
    }
    for (const match of source.matchAll(/from\s+["'](\.[^"']+)["']/g)) {
        const imported = resolve(dirname(path), match[1]);
        if (!existsSync(imported)) {
            failures.push(`${relative(root, path)} imports missing module ${match[1]}`);
        }
    }
}

if (failures.length) {
    console.error(failures.join("\n"));
    process.exit(1);
}

console.log("Frontend static and security checks passed.");
