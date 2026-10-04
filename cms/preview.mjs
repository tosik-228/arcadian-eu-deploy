import {createServer} from 'node:http';
import {readFile, stat} from 'node:fs/promises';
import {resolve, extname, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(fileURLToPath(new URL('../static-site/', import.meta.url)));
const port = Number(process.env.SITE_PORT || 8173);
const cms = process.env.CMS_URL || 'http://127.0.0.1:8057';
const types = {'.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2'};
createServer(async (req, res) => {
  if (!['GET', 'HEAD'].includes(req.method)) {res.writeHead(405); return res.end();}
  try {
    const path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    if (path === '/assets/js/content-config.js') {
      res.writeHead(200, {'Content-Type': 'text/javascript', 'Cache-Control': 'no-store'});
      return res.end(`window.ARCADIAN_CMS_URL = ${JSON.stringify(cms)};\n`);
    }
    if (path === '/admin/' || path === '/admin') {res.writeHead(302, {Location: `${cms}/admin/`}); return res.end();}
    let file = resolve(root, `.${path}`);
    if (!file.startsWith(root + sep) || path.includes('/.')) throw new Error('Invalid path');
    if ((await stat(file)).isDirectory()) file = resolve(file, 'index.html');
    const body = await readFile(file);
    res.writeHead(200, {'Content-Type': types[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store'});
    res.end(req.method === 'HEAD' ? undefined : body);
  } catch (_) {res.writeHead(404); res.end('Not found');}
}).listen(port, '127.0.0.1', () => console.log(`Arcadian preview: http://127.0.0.1:${port}`));
