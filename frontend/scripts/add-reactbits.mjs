// Pull React Bits components (TS + Tailwind variant) from the public registry
// into src/components/reactbits/. Same files the shadcn / jsrepo CLIs would add.
//   node scripts/add-reactbits.mjs Aurora SplitText ...
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const names = process.argv.slice(2);
const outRoot = path.resolve("src/components/reactbits");
for (const name of names) {
  const url = `https://reactbits.dev/r/${name}-TS-TW.json`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const item = await res.json();
  for (const f of item.files) {
    const dst = path.join(outRoot, f.path);
    await mkdir(path.dirname(dst), { recursive: true });
    await writeFile(dst, `// React Bits (${url})\n` + f.content);
    console.log(`${name}: ${path.relative(process.cwd(), dst)}  deps=${JSON.stringify(item.dependencies ?? [])}`);
  }
}
