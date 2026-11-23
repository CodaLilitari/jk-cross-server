import math
import struct
import unittest

from bots.lily import protocol as p


class TestLilyWire(unittest.TestCase):
    def test_command(self):
        body = dict(sample_id=42, revision=8, steps=[dict(duration_ms=100, forward=0.75, strafe=-0.5, buttons=3)])
        self.assertEqual(p.encode_command(p.MOTOR,body,9), struct.pack("<dIIBHbbbbBBB",9,42,8,1,100,75,-50,0,0,3,0,0))
        for field, value in (("forward", math.nan), ("duration_ms", True), ("buttons",32), ("force",3), ("oops",1)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                p.encode_command(p.MOTOR,dict(body, steps=[dict(body["steps"][0], **{field:value})]),9)
        with self.assertRaises(ValueError):
            p.encode_command(p.MOTOR,dict(body, steps=body["steps"]*6),9)
        with self.assertRaises(ValueError):
            p.encode_command(p.MOTOR,body,math.inf)

    def test_events(self):
        record = struct.pack("<IiBB3fff",17,5,1,11,1,2,3,4,9)
        payload = struct.pack("<IIB",8,6,1)+record
        data = p.decode_event(p.OFFERS,payload)
        self.assertEqual(data["choices"][0]["class"],"item")
        self.assertEqual(data["choices"][0]["position"], [1,2,3])
        for bad in (payload[:-1],payload+b"!",payload[:-4]+struct.pack("<f",math.nan),payload*24,4):
            self.assertIsNone(p.decode_event(p.OFFERS,bad))
        progress = struct.pack("<IIIBBBBIi",43,7,9,1,4,0,1,500,17)
        self.assertEqual(p.decode_event(p.PROGRESS,progress)["outcome"],"arrived")

    def test_progress_identity_and_outcomes_agree(self):
        def event(owner, phase, reason, outcome, node):
            return p.decode_event(p.PROGRESS, p.ACTION.pack(1, 8, 9, owner, phase, reason, outcome, 40, node))
        for record in [(2,4,0,1,-1), (1,4,0,2,4), (2,4,0,2,4), (1,3,0,1,5),
                       (2,6,5,0,-1), (1,5,0,0,2), (1,7,1,0,3)]:
            with self.subTest(record=record):
                self.assertIsNone(event(*record))
        self.assertEqual(event(2,4,0,2,-1)["outcome"], "playback")
        self.assertEqual(event(1,5,5,0,3)["phase"], "interrupted")

    def test_sense_ranges_and_owner(self):
        fields = list(p.SENSE_HEADER.unpack(bytes(p.SENSE_HEADER.size)))
        fields[0], fields[4], fields[24] = 1, -1, 33.0
        self.assertIsNotNone(p.decode_event(p.SENSE, p.SENSE_HEADER.pack(*fields)))
        for index, value in [(23,-1), (24,-200), (24,0), (25,7.5), (28,-2), (6,3), (5,2), (1,5)]:
            bad = fields.copy()
            bad[index] = value
            with self.subTest(index=index, value=value):
                self.assertIsNone(p.decode_event(p.SENSE, p.SENSE_HEADER.pack(*bad)))
