import asyncio
import struct
import tempfile
import unittest
from pathlib import Path
from manager.config import validate, registry, save, load, ConfigError
from manager.content import catalog, archive_index, preflight
from manager.broker import AdapterBroker, encode, receive

class ConfigurationTests(unittest.TestCase):
 def test_original_install_resource_aliases(self):
  for mode,names,suffix in [('jk',['Res1low.gob','Res2.gob'],'gob'),('mots',['Jkmres.goo','JKMsndLO.goo'],'goo')]:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
    root=Path(d);(root/'Episode').mkdir();(root/'Resource').mkdir()
    for n in [*names,'jk_.cd']:(root/'Resource'/n).write_bytes(b'')
    blobs=[('episode.jk',b'"Alias fixture"\nTYPE 2\n'),('jkl/test.jkl',b'fixture')]
    start=12;data=b'';rows=b''
    for n,b in blobs:
     rows+=struct.pack('<II128s',start,len(b),n.encode());data+=b;start+=len(b)
    (root/'Episode'/f'custom.{suffix}').write_bytes(b'GOB '+struct.pack('<II',20,start)+data+struct.pack('<I',len(blobs))+rows)
    cfg=validate({'game':mode,'game_data':str(root),'episode':'custom','map':'test.jkl'})
    self.assertEqual(preflight(cfg)['episode'],f'custom.{suffix}')
    (root/'Resource'/names[-1]).unlink()
    with self.assertRaises(ConfigError):preflight(cfg)
 def test_retail_and_mode_constraints(self):
  self.assertTrue(validate({})['web_asset_downloads'])
  self.assertFalse(validate({'web_asset_downloads':False})['web_asset_downloads'])
  self.assertEqual(validate({'game':'mots'})['rank'],7)
  with self.assertRaises(ConfigError):validate({'game':'mots','rank':0})
  self.assertEqual(validate({'game':'mots','rank':0,'game_flags':4096})['rank'],0)
  for c in ({'game':'jk2'},{'retail_enabled':True,'tick_ms':50},{'retail_enabled':True,'max_players':16},{'max_players':True},{'map':'../secret.jkl'},{'game_flags':65536},{'ipc_port':46001},{'web_asset_downloads':'yes'},{'web_ice_servers':[{'urls':[]}]},{'web_ice_servers':[{'urls':'https://example.test'}]}):
   with self.subTest(c=c),self.assertRaises(ConfigError):validate(c)
 def test_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.json'; c=save(p,{'max_players':7,'score_limit':20,'web_ice_servers':[{'urls':'turn:relay.example.test:3478','username':'test','credential':'fixture-only'}]})
   self.assertEqual(load(p),c); r=registry(c)
   self.assertEqual(r['maxPlayers'],7);self.assertTrue(r['bIsDedicated']);self.assertTrue(r['bUseScoreLimit'])
 def test_archive_and_catalog(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'Episode').mkdir();(root/'Resource').mkdir()
   for name,t in [('multiplayer',2),('campaign',1)]:
    blobs=[('episode.jk',f'"Title"\nTYPE {t}\n'.encode()),('jkl/test.jkl',b'test')];cur=288;idx=b'';data=b''
    for n,b in blobs:idx+=struct.pack('<II128s',cur,len(b),n.encode());data+=b;cur+=len(b)
    (root/'Episode'/f'{name}.GOB').write_bytes(b'GOB '+struct.pack('<III',20,12,2)+idx+data)
   result=catalog(root);self.assertEqual([e['episode'] for e in result['episodes']],['multiplayer'])
   p=root/'Episode'/'multiplayer.GOB';raw=bytearray(p.read_bytes());struct.pack_into('<I',raw,12,999999);p.write_bytes(raw)
   with self.assertRaises(ConfigError):archive_index(p)

class Engine:
 def __init__(self):self.peers=set();self.sent=[]
 def subscribe_data(self,c):self.data=c
 def subscribe_state(self,c):self.state=c
 def subscribe_info(self,c):self.info_cb=c
 async def info(self):return 0,bytes(240)
 async def add_peer(self,i=0):self.peers.add(i or 500);return i or 500
 async def remove_peer(self,i):self.peers.discard(i)
 async def send(self,s,d,p):self.sent.append((s,d,p))
 async def set_id_pool(self,ids):self.pool=ids

class BrokerTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.e=Engine();self.b=AdapterBroker(self.e,'long-unit-test-token',port=0);await self.b.start();self.w=[]
 async def asyncTearDown(self):
  for w in self.w:w.close()
  await self.b.close()
 async def connect(self,token=b'long-unit-test-token'):
  r,w=await asyncio.open_connection('127.0.0.1',self.b.server.sockets[0].getsockname()[1]);self.w.append(w)
  w.write(encode(1,payload=token));await w.drain();return r,w,await receive(r)
 async def call(self,r,w,k,s=0,d=0,p=b''):
  w.write(encode(k,s,d,p));await w.drain();return await asyncio.wait_for(receive(r),2)
 async def test_auth_first(self):
  r,w,result=await self.connect(b'wrong');self.assertEqual(result[0],199);self.assertFalse(self.e.peers);self.assertEqual(await r.read(),b'')
 async def test_ownership_routing_cleanup(self):
  r,w,hello=await self.connect();self.assertEqual(hello[0],101)
  self.assertEqual((await self.call(r,w,3,500,71))[:3],(103,500,71))
  r2,w2,_=await self.connect();self.assertEqual((await self.call(r2,w2,5,500,1,b'1234'))[0],199)
  w.write(encode(5,500,1,b'5678'));await w.drain();await self.call(r,w,7)
  self.assertEqual(self.e.sent,[(500,1,b'5678')]);await self.b.on_data(1,500,b'abcd')
  self.assertEqual(await receive(r),(105,1,500,b'abcd'));await self.call(r,w,4,500);self.assertFalse(self.e.peers)
 async def test_stop_with_live_adapter(self):
  r,w,_=await self.connect();await self.call(r,w,3,500)
  await asyncio.wait_for(self.b.close(),2)
  self.assertEqual(await r.read(),b'');self.assertFalse(self.e.peers)
 async def test_pool_metadata(self):
  r,w,_=await self.connect();self.assertEqual(len((await self.call(r,w,2))[3]),244)
  self.assertEqual((await self.call(r,w,8,p=struct.pack('<III',101,102,103)))[0],108)
  self.assertTrue(self.b.pool_ready.is_set());self.assertEqual(self.e.pool,[101,102,103])
 async def test_host_kick_retires_one_peer_and_keeps_adapter_alive(self):
  r,w,_=await self.connect();await self.call(r,w,3,500,71)
  await self.call(r,w,3,501,72)
  await self.b.on_removed(500)
  self.assertEqual((await receive(r))[:2],(104,500))
  w.write(encode(5,500,1,b'late'));await w.drain()
  self.assertEqual((await self.call(r,w,7))[0],107)
  self.assertFalse(self.e.sent);self.assertNotIn(500,self.b.owners)
  self.assertEqual((await self.call(r,w,4,500))[0],104)
  w.write(encode(5,500,1,b'late'));await w.drain()
  self.assertEqual((await self.call(r,w,4,500))[0],104)
  self.assertEqual((await self.call(r,w,7))[0],107)
  self.assertFalse(self.e.sent)
  w.write(encode(5,501,1,b'live'));await w.drain()
  self.assertEqual((await self.call(r,w,7))[0],107)
  self.assertEqual(self.e.sent,[(501,1,b'live')])
  self.assertIn(501,self.b.owners)

if __name__=='__main__':unittest.main()
