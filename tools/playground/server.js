// Tiny playground server: serves the page and compiles llang to WASM via Python.
const http = require('http');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

const ROOT = path.resolve(__dirname, '../..');
const PORT = process.env.PORT || 8080;

http.createServer((req, res) => {
  if (req.method === 'GET' && (req.url === '/' || req.url === '/index.html')) {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8'));
    return;
  }

  if (req.method === 'POST' && req.url === '/compile') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      let source;
      try { source = JSON.parse(body).source; }
      catch (e) { res.writeHead(400); res.end('bad request'); return; }

      const child = execFile(
        'python', [path.join(__dirname, 'compile_helper.py')],
        { cwd: ROOT, env: { ...process.env, PYTHONPATH: path.join(ROOT, 'src') },
          maxBuffer: 5 * 1024 * 1024 },
        (error, stdout, stderr) => {
          if (error) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: stderr || error.message }));
            return;
          }
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(stdout.trim());
        }
      );
      child.stdin.write(source);
      child.stdin.end();
    });
    return;
  }

  res.writeHead(404);
  res.end('not found');
}).listen(PORT, () => {
  console.log(`llang playground: http://localhost:${PORT}`);
});
