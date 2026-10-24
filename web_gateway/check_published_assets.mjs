// Exact published modules, exercised under Node; this is not a rendered game.
import fs from 'node:fs';
import crypto from 'node:crypto';
import vm from 'node:vm';

const [bundle, relayUrl, fixturePath] = process.argv.slice(2);
const bytes = fs.readFileSync(bundle);
const expected = '4ae0de474cc2ae817c6162fe21a6ac4b73c573d311884253cf002aedc6a46bb0';
if (crypto.createHash('sha256').update(bytes).digest('hex') !== expected)
  throw new Error('The exact cloudflare-38 JavaScript bundle is required');
const source = bytes.toString('utf8');
const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
globalThis.Module = {jkRelayUrl: relayUrl, jkUseWebRTC: false, arguments: []};

for (const name of ['maps.js', 'mods.js']) {
  const start = source.indexOf('// include: /home/user/openjkdf2/packaging/wasm/' + name);
  const end = source.indexOf('// end include: /home/user/openjkdf2/packaging/wasm/' + name, start);
  if (start < 0 || end < start) throw new Error('Published asset module missing: ' + name);
  vm.runInThisContext(source.slice(start, end), {filename: 'published-' + name});
}
const start = source.indexOf('function wsrelay_js_connect() {');
const end = source.indexOf('\n}\n', start) + 3;
if (start < 0 || end < start) throw new Error('Published transport missing');
vm.runInThisContext(source.slice(start, end), {filename: 'published-wsrelay.js'});
wsrelay_js_connect();

async function until(predicate, label, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('Timed out: ' + label);
    await new Promise(resolve => setTimeout(resolve, 5));
  }
}
const net = Module.jkNet;
await until(() => net.state === 1, 'relay open');
net.ws.send('hello jk1 ' + btoa('PublishedAssetClient'));
net.ws.send('join 1');
await until(() => net.queue.some(x => typeof x === 'string' && x.startsWith('welcome ')), 'welcome');
const welcome = net.queue.find(x => typeof x === 'string' && x.startsWith('welcome ')).split(' ');
const tail = Module.jkMods.lib.parseTail(welcome[2].slice(480));
if (!tail || tail.bad || tail.fp !== fixture.mod_sha256) throw new Error('Published JKMD parser disagrees');

const lib = Module.jkMaps.lib, core = Module.jkMaps.core;
const retail = new Uint8Array(Buffer.from(fixture.retail, 'base64'));
const read = (offset, length) => retail.subarray(offset, offset + length);
const entries = lib.parseGob(read, retail.length).entries;
const retailSources = [{read, entries: entries.concat([{offset:0, size:retail.length, name:''}])}];
const files = fixture.mod_files.map(f => ({rel:f.rel, data:new Uint8Array(Buffer.from(f.data, 'base64'))}));
files.forEach(f => f.size = f.data.length);
const packed = Module.jkMods.lib.packFiles(files, f => f.data);
if (await lib.sha256(packed.bytes) !== fixture.mod_sha256)
  throw new Error('Python mod pack differs from exact published packFiles');

const results = [];
for (const kind of [0, 1]) {
  let result = null;
  core.startJob(kind, {label:'owned fixture', name:'Custom', ext:'gob'}, async j => {
    const info = await core.askInfo(j);
    if (info.status !== 'ok') throw core.fail(info.status);
    core.checkInfo(info, kind ? 263504016 : 104857600);
    const stream = await core.download(j, info, core.CHUNK_RELAY);
    const rebuilt = await lib.rebuild(info, stream, retailSources);
    if (!rebuilt.ok) throw core.fail(rebuilt.reason);
    const wanted = kind ? fixture.mod_sha256 : fixture.episode_sha256;
    const sha = await lib.sha256(rebuilt.bytes);
    if (sha !== wanted) throw core.fail('mismatch');
    if (kind && !Buffer.from(rebuilt.bytes).equals(Buffer.from(packed.bytes)))
      throw new Error('Reconstructed mod differs from published deterministic pack');
    result = {kind, sha256:sha, size:rebuilt.bytes.length, stream_size:stream.length,
              references:new DataView(stream.buffer, stream.byteOffset).getUint32(0, true)};
  });
  await until(() => core.state(kind) !== core.STATE_BUSY, 'published download/rebuild');
  if (core.state(kind) !== core.STATE_READY || !result) throw new Error('Published transfer failed');
  results.push(result);
}
net.ws.send('leave');
net.ws.close();
console.log(JSON.stringify({passed:true, whole_bundle_sha256:expected, published_code_modified:false,
  full_game:false, transport:'published WebSocket fallback', deterministic_mod_pack_matches:true,
  tail_fingerprint_matches:true, results}));
process.exit(0);
