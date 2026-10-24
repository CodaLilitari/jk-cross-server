// Executes the exact transport function from the published, unmodified bundle.
// This checks browser transport JS under Node's WebSocket API, not gameplay.
import fs from 'node:fs';
import crypto from 'node:crypto';
import vm from 'node:vm';

const [bundle, relayUrl] = process.argv.slice(2);
const bytes = fs.readFileSync(bundle);
const expected = '4ae0de474cc2ae817c6162fe21a6ac4b73c573d311884253cf002aedc6a46bb0';
if (crypto.createHash('sha256').update(bytes).digest('hex') !== expected) {
  throw new Error('The test requires the exact cloudflare-38 bundle');
}
const source = bytes.toString('utf8');
const start = source.indexOf('function wsrelay_js_connect() {');
const end = source.indexOf('\n}\n', start) + 3;
if (start < 0 || end < start) throw new Error('Published transport function missing');
globalThis.Module = { jkRelayUrl: relayUrl, jkUseWebRTC: false };
vm.runInThisContext(source.slice(start, end), {filename: 'published-wsrelay.js'});
wsrelay_js_connect();

async function until(predicate, label) {
  const deadline = Date.now() + 5000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('Timed out: ' + label);
    await new Promise(resolve => setTimeout(resolve, 5));
  }
}
const net = Module.jkNet;
await until(() => net.state === 1, 'WebSocket open');
net.ws.send('hello jk1 ' + btoa('PublishedClient'));
net.ws.send('list jk1');
await until(() => net.queue.some(x => typeof x === 'string' && x.startsWith('list 1 ')), 'room listing');
const list = net.queue.find(x => typeof x === 'string' && x.startsWith('list 1 '));
if (list.split(' ')[3].length !== 480) throw new Error('Wrong session descriptor size');
net.ws.send('join 1');
await until(() => net.queue.some(x => typeof x === 'string' && x.startsWith('welcome ')), 'welcome');
const welcome = net.queue.find(x => typeof x === 'string' && x.startsWith('welcome '));
const id = Number(welcome.split(' ')[1]);
if (net.seat?.id !== id) throw new Error('Published seat parser disagrees with welcome');
const packet = new Uint8Array(20);
const view = new DataView(packet.buffer);
view.setUint32(0, id, true);
view.setUint32(4, 1, true);
view.setUint16(8, 1, true);
packet.set(new TextEncoder().encode('wiredata'), 12);
if (net.sendPacket(packet, 1) !== 1) throw new Error('Published sender rejected packet');
await until(() => net.queue.some(x => x instanceof ArrayBuffer), 'engine reply');
const reply = new Uint8Array(net.queue.find(x => x instanceof ArrayBuffer));
const expectedReply = packet.slice();
new DataView(expectedReply.buffer).setUint32(0, 1, true);
new DataView(expectedReply.buffer).setUint32(4, id, true);
if (!Buffer.from(reply).equals(Buffer.from(expectedReply))) throw new Error('Payload changed');
net.ws.send('leave');
net.ws.close();
console.log(JSON.stringify({passed:true, whole_bundle_sha256:expected, transport_function_changed:false,
  assigned_player:id, descriptor_bytes:240, application_payload_unchanged:true, game_simulated:false}));
process.exit(0);
