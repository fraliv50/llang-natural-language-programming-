// Helper for tests: instantiate a compiled .wasm module and call an export.
const fs = require('fs');
const bytes = fs.readFileSync(process.argv[2]);
const mod = new WebAssembly.Module(bytes);
const instance = new WebAssembly.Instance(mod, {});
const fn = instance.exports[process.argv[3]];
if (typeof fn !== 'function') {
  console.error('missing export: ' + process.argv[3]);
  process.exit(2);
}
const args = process.argv.slice(4).map(Number);
console.log(fn(...args));
