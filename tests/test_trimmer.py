"""Tests for realms_trimmer using a small synthetic world (no Minecraft needed)."""
import gzip
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import realms_trimmer as rt  # noqa: E402


def chunk_payload(inhabited):
    nbt = b'\x0a\x00\x00' + rt.INHABITED_TAG + struct.pack('>q', inhabited) + b'\x00'
    comp = zlib.compress(nbt)
    return (len(comp) + 1).to_bytes(4, 'big') + b'\x02' + comp


def make_world(root, inhabited_by_index, new_layout=True):
    """Creates a world with one region file r.0.0.mca in overworld."""
    os.makedirs(root)
    nbt = b'\x0a\x00\x00\x0a\x00\x04Data\x08\x00\x09LevelName\x00\x03Old\x00\x00'
    with open(os.path.join(root, 'level.dat'), 'wb') as f:
        f.write(gzip.compress(nbt))
    dim = os.path.join(root, 'dimensions', 'minecraft', 'overworld') if new_layout else root
    chunks = {i: (chunk_payload(t), b'\x00\x00\x00\x01') for i, t in inhabited_by_index.items()}
    for sub in ('region', 'entities', 'poi'):
        os.makedirs(os.path.join(dim, sub), exist_ok=True)
        rt.write_region(os.path.join(dim, sub, 'r.0.0.mca'), chunks)
    return dim


class TrimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def quiet(self, *_):
        pass

    def test_region_roundtrip(self):
        path = os.path.join(self.tmp.name, 'r.0.0.mca')
        chunks = {0: (chunk_payload(5), b'abcd'), 1023: (chunk_payload(0), b'efgh')}
        rt.write_region(path, chunks)
        self.assertEqual(rt.read_region(path), chunks)

    def test_inhabited_ticks(self):
        self.assertEqual(rt.inhabited_ticks(chunk_payload(1234)), 1234)

    def test_keeps_visited_plus_margin(self):
        # Chunk (0,0) visited; (1,0) is in margin 1; (10,10) is far and unvisited.
        world = os.path.join(self.tmp.name, 'w')
        make_world(world, {0: 100, 1: 0, 10 * 32 + 10: 0})
        out = os.path.join(self.tmp.name, 'out')
        rt.trim(world, out, 1, 'Trimmed', self.quiet)

        for sub in ('region', 'entities', 'poi'):
            kept = rt.read_region(os.path.join(out, 'dimensions', 'minecraft', 'overworld', sub, 'r.0.0.mca'))
            self.assertEqual(sorted(kept), [0, 1], sub)

        # Original untouched
        orig = rt.read_region(os.path.join(world, 'dimensions', 'minecraft', 'overworld', 'region', 'r.0.0.mca'))
        self.assertEqual(len(orig), 3)

    def test_empty_region_files_removed(self):
        world = os.path.join(self.tmp.name, 'w')
        make_world(world, {5: 0})
        out = os.path.join(self.tmp.name, 'out')
        rt.trim(world, out, 3, 'Trimmed', self.quiet)
        self.assertFalse(os.path.exists(os.path.join(out, 'dimensions', 'minecraft', 'overworld', 'region', 'r.0.0.mca')))

    def test_classic_layout(self):
        world = os.path.join(self.tmp.name, 'w')
        make_world(world, {0: 50, 500: 0}, new_layout=False)
        self.assertIn('minecraft:overworld', rt.find_dimensions(world))
        out = os.path.join(self.tmp.name, 'out')
        rt.trim(world, out, 0, 'Trimmed', self.quiet)
        self.assertEqual(sorted(rt.read_region(os.path.join(out, 'region', 'r.0.0.mca'))), [0])

    def test_level_name_renamed(self):
        world = os.path.join(self.tmp.name, 'w')
        make_world(world, {0: 1})
        out = os.path.join(self.tmp.name, 'out')
        rt.trim(world, out, 0, 'Mundo (Realms)', self.quiet)
        with open(os.path.join(out, 'level.dat'), 'rb') as f:
            data = gzip.decompress(f.read())
        self.assertIn('Mundo (Realms)'.encode(), data)
        self.assertNotIn(b'Old', data)

    def test_validate(self):
        world = os.path.join(self.tmp.name, 'w')
        make_world(world, {0: 1})
        self.assertIsNone(rt.validate(world, os.path.join(self.tmp.name, 'new')))
        self.assertIsNotNone(rt.validate(os.path.join(self.tmp.name, 'missing')))
        self.assertIsNotNone(rt.validate(world, world))
        self.assertIsNotNone(rt.validate(world, os.path.join(world, 'inside')))


if __name__ == '__main__':
    unittest.main()
