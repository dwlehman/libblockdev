import unittest
import os
import re
import time
from contextlib import contextmanager

from utils import create_sparse_tempfile
from gi.repository import BlockDev, GLib

def print_msg(level, msg):
    print msg

if not BlockDev.is_initialized():
    BlockDev.init(None, None)

@contextmanager
def wait_for_resync():
    yield
    time.sleep(5)
    resync = True
    while resync:
        with open("/proc/mdstat", "r") as f:
            resync = "resync" in f
        if resync:
            print("Sleeping")
            time.sleep(1)

class MDNoDevTestCase(unittest.TestCase):
    def test_get_superblock_size(self):
        """Verify that superblock size si calculated properly"""

        # 2 MiB for versions <= 1.0
        self.assertEqual(BlockDev.md_get_superblock_size(2 * 1024**3, "0.9"), 2 * 1024**2)
        self.assertEqual(BlockDev.md_get_superblock_size(2 * 1024**3, "1.0"), 2 * 1024**2)

        # no version, "default" or > 1.0
        self.assertEqual(BlockDev.md_get_superblock_size(256 * 1024**3, None), 128 * 1024**2)
        self.assertEqual(BlockDev.md_get_superblock_size(128 * 1024**3, None), 128 * 1024**2)
        self.assertEqual(BlockDev.md_get_superblock_size(64 * 1024**3, "default"), 64 * 1024**2)
        self.assertEqual(BlockDev.md_get_superblock_size(63 * 1024**3, "default"), 32 * 1024**2)
        self.assertEqual(BlockDev.md_get_superblock_size(10 * 1024**3, "1.1"), 8 * 1024**2)
        self.assertEqual(BlockDev.md_get_superblock_size(1 * 1024**3, "1.1"), 1 * 1024**2)
        self.assertEqual(BlockDev.md_get_superblock_size(1023 * 1024**2, "1.2"), 1 * 1024**2)
        self.assertEqual(BlockDev.md_get_superblock_size(512 * 1024**2, "1.2"), 1 * 1024**2)

        # unsupported version -> default superblock size
        self.assertEqual(BlockDev.md_get_superblock_size(257 * 1024**2, version="unknown version"),
                         2 * 1024**2)

    def test_canonicalize_uuid(self):
        """Verify that UUID canonicalization works as expected"""

        self.assertEqual(BlockDev.md_canonicalize_uuid("3386ff85:f5012621:4a435f06:1eb47236"),
                         "3386ff85-f501-2621-4a43-5f061eb47236")

        with self.assertRaisesRegexp(GLib.GError, r'malformed or invalid'):
            BlockDev.md_canonicalize_uuid("malformed-uuid-example")

    def test_get_md_uuid(self):
        """Verify that getting UUID in MD RAID format works as expected"""

        self.assertEqual(BlockDev.md_get_md_uuid("3386ff85-f501-2621-4a43-5f061eb47236"),
                         "3386ff85:f5012621:4a435f06:1eb47236")

        with self.assertRaisesRegexp(GLib.GError, r'malformed or invalid'):
            BlockDev.md_get_md_uuid("malformed-uuid-example")

class MDTestCase(unittest.TestCase):
    def setUp(self):
        self.dev_file = create_sparse_tempfile("md_test", 10 * 1024**2)
        self.dev_file2 = create_sparse_tempfile("md_test", 10 * 1024**2)
        self.dev_file3 = create_sparse_tempfile("md_test", 10 * 1024**2)

        succ, loop = BlockDev.loop_setup(self.dev_file)
        if  not succ:
            raise RuntimeError("Failed to setup loop device for testing")
        self.loop_dev = "/dev/%s" % loop
        succ, loop = BlockDev.loop_setup(self.dev_file2)
        if  not succ:
            raise RuntimeError("Failed to setup loop device for testing")
        self.loop_dev2 = "/dev/%s" % loop
        succ, loop = BlockDev.loop_setup(self.dev_file3)
        if  not succ:
            raise RuntimeError("Failed to setup loop device for testing")
        self.loop_dev3 = "/dev/%s" % loop

    def tearDown(self):
        try:
            BlockDev.md_deactivate("bd_test_md")
        except:
            pass
        try:
            BlockDev.md_destroy(self.loop_dev)
        except:
            pass
        try:
            BlockDev.md_destroy(self.loop_dev2)
        except:
            pass
        try:
            BlockDev.md_destroy(self.loop_dev3)
        except:
            pass

        succ = BlockDev.loop_teardown(self.loop_dev)
        if  not succ:
            os.unlink(self.dev_file)
            raise RuntimeError("Failed to tear down loop device used for testing")

        os.unlink(self.dev_file)
        succ = BlockDev.loop_teardown(self.loop_dev2)
        if  not succ:
            os.unlink(self.dev_file2)
            raise RuntimeError("Failed to tear down loop device used for testing")

        os.unlink(self.dev_file2)
        succ = BlockDev.loop_teardown(self.loop_dev3)
        if  not succ:
            os.unlink(self.dev_file3)
            raise RuntimeError("Failed to tear down loop device used for testing")

        os.unlink(self.dev_file3)

class MDTestCreateDeactivateDestroy(MDTestCase):
    @unittest.skipIf("SKIP_SLOW" in os.environ, "skipping slow tests")
    def test_create_deactivate_destroy(self):
        """Verify that it is possible to create, deactivate and destroy an MD RAID"""

        with self.assertRaises(GLib.GError):
            BlockDev.md_create("bd_test_md2", "raid1",
                               ["/non/existing/device", self.loop_dev2],
                               1, None, True)

        with wait_for_resync():
            succ = BlockDev.md_create("bd_test_md", "raid1",
                                      [self.loop_dev, self.loop_dev2, self.loop_dev3],
                                      1, None, True)
            self.assertTrue(succ)

        succ = BlockDev.md_deactivate("bd_test_md")
        self.assertTrue(succ)

        succ = BlockDev.md_destroy(self.loop_dev)
        self.assertTrue(succ)
        succ = BlockDev.md_destroy(self.loop_dev2)
        self.assertTrue(succ)
        succ = BlockDev.md_destroy(self.loop_dev3)
        self.assertTrue(succ)

class MDTestActivateDeactivate(MDTestCase):
    @unittest.skipIf("SKIP_SLOW" in os.environ, "skipping slow tests")
    def test_activate_deactivate(self):
        """Verify that it is possible to activate and deactivate an MD RAID"""

        with wait_for_resync():
            succ = BlockDev.md_create("bd_test_md", "raid1",
                                      [self.loop_dev, self.loop_dev2, self.loop_dev3],
                                      1, None, True)
            self.assertTrue(succ)

        with self.assertRaises(GLib.GError):
            BlockDev.md_deactivate("non_existing_md")

        with wait_for_resync():
            succ = BlockDev.md_deactivate("bd_test_md")
            self.assertTrue(succ)

        with self.assertRaises(GLib.GError):
            BlockDev.md_activate("bd_test_md",
                                 ["/non/existing/device", self.loop_dev2, self.loop_dev3], None)

        with wait_for_resync():
            succ = BlockDev.md_activate("bd_test_md",
                                        [self.loop_dev, self.loop_dev2, self.loop_dev3], None)
            self.assertTrue(succ)

class MDTestNominateDenominate(MDTestCase):
    @unittest.skipIf("SKIP_SLOW" in os.environ, "skipping slow tests")
    def test_nominate_denominate(self):
        """Verify that it is possible to nominate and denominate an MD RAID device"""

        with wait_for_resync():
            succ = BlockDev.md_create("bd_test_md", "raid1",
                                      [self.loop_dev, self.loop_dev2, self.loop_dev3],
                                      1, None, False)
            self.assertTrue(succ)

        with wait_for_resync():
            succ = BlockDev.md_denominate(self.loop_dev)
            self.assertTrue(succ)

        with wait_for_resync():
            succ = BlockDev.md_nominate(self.loop_dev)
            self.assertTrue(succ)

        with wait_for_resync():
            succ = BlockDev.md_denominate(self.loop_dev)
            self.assertTrue(succ)

        with wait_for_resync():
            succ = BlockDev.md_nominate(self.loop_dev)
            self.assertTrue(succ)

class MDTestNominateDenominateActive(MDTestCase):
    @unittest.skipIf("SKIP_SLOW" in os.environ, "skipping slow tests")
    def test_nominate_denominate_active(self):
        """Verify that nominate and denominate deivice works as expected on (de)activated MD RAID"""

        with wait_for_resync():
            succ = BlockDev.md_create("bd_test_md", "raid1",
                                      [self.loop_dev, self.loop_dev2, self.loop_dev3],
                                      1, None, False)
            self.assertTrue(succ)

        # can not re-add in incremental mode because the array is active
        with self.assertRaises(GLib.GError):
            BlockDev.md_nominate(self.loop_dev3)

        succ = BlockDev.md_deactivate("bd_test_md");
        self.assertTrue(succ)

        # once the array is deactivated, can add in incremental mode
        succ = BlockDev.md_nominate(self.loop_dev3)
        self.assertTrue(succ)

        # cannot re-add twice
        with self.assertRaises(GLib.GError):
            succ = BlockDev.md_nominate(self.loop_dev3)
            self.assertTrue(succ)

class MDTestAddRemove(MDTestCase):
    @unittest.skipIf("SKIP_SLOW" in os.environ, "skipping slow tests")
    def test_add_remove(self):
        """Verify that it is possible to add a device to and remove from an MD RAID"""

        # the MD array doesn't exist yet
        with self.assertRaises(GLib.GError):
            BlockDev.md_add("bd_test_md", self.loop_dev3, 0)

        with wait_for_resync():
            succ = BlockDev.md_create("bd_test_md", "raid1",
                                      [self.loop_dev, self.loop_dev2],
                                      0, None, False)
            self.assertTrue(succ)

        with self.assertRaises(GLib.GError):
            BlockDev.md_add("bd_test_md", "/non/existing/device", 0)

        succ = BlockDev.md_add("bd_test_md", self.loop_dev3, 0)
        self.assertTrue(succ)

        with self.assertRaises(GLib.GError):
            BlockDev.md_add("bd_test_md", self.loop_dev3, 0)

        with wait_for_resync():
            succ = BlockDev.md_remove("bd_test_md", self.loop_dev3, True)
            self.assertTrue(succ)

        # XXX: cannnot remove device added as a spare device nor a different
        # device?
        succ = BlockDev.md_add("bd_test_md", self.loop_dev3, 2)
        self.assertTrue(succ)

class MDTestExamineDetail(MDTestCase):
    # sleeps to let MD RAID sync things
    @unittest.skipIf("SKIP_SLOW" in os.environ, "skipping slow tests")
    def test_examine_detail(self):
        """Verify that it is possible to get info about an MD RAID"""

        with wait_for_resync():
            succ = BlockDev.md_create("bd_test_md", "raid1",
                                      [self.loop_dev, self.loop_dev2, self.loop_dev3],
                                      1, None, True)
            self.assertTrue(succ)

        ex_data = BlockDev.md_examine(self.loop_dev)
        # test that we got something
        self.assertTrue(ex_data)

        # verify some known data
        self.assertEqual(ex_data.device, "/dev/md/bd_test_md")
        self.assertEqual(ex_data.level, "raid1")
        self.assertEqual(ex_data.num_devices, 2)
        self.assertTrue(ex_data.name.endswith("bd_test_md"))
        self.assertEqual(len(ex_data.metadata), 3)
        self.assertTrue(ex_data.size < (10 * 1024**2))
        self.assertTrue(re.match(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', ex_data.uuid))

        de_data = BlockDev.md_detail("bd_test_md")
        # test that we got something
        self.assertTrue(de_data)

        # verify some known data
        self.assertEqual(de_data.device, "/dev/md/bd_test_md")
        self.assertTrue(de_data.name.endswith("bd_test_md"))
        self.assertEqual(len(de_data.metadata), 3)
        self.assertEqual(de_data.level, "raid1")
        self.assertEqual(de_data.raid_devices, 2)
        self.assertEqual(de_data.total_devices, 3)
        self.assertEqual(de_data.spare_devices, 1)
        self.assertTrue(de_data.array_size < (10 * 1024**2))
        self.assertTrue(de_data.use_dev_size < (10 * 1024**2))
        if "JENKINS_HOME" not in os.environ:
            # XXX: for some reason the RAID is in "active sync" when tests run in
            # Jenkins
            self.assertTrue(de_data.clean)
        self.assertTrue(re.match(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', de_data.uuid))

        self.assertEqual(ex_data.uuid, de_data.uuid)

class MDTestNameNodeBijection(MDTestCase):
    @unittest.skipIf("SKIP_SLOW" in os.environ, "skipping slow tests")
    def test_name_node_bijection(self):
        """Verify that MD RAID node and name match each other"""

        with wait_for_resync():
            succ = BlockDev.md_create("bd_test_md", "raid1",
                                      [self.loop_dev, self.loop_dev2, self.loop_dev3],
                                      1, None, True)
            self.assertTrue(succ)

        node = BlockDev.md_node_from_name("bd_test_md")
        self.assertEqual(BlockDev.md_name_from_node(node), "bd_test_md")

        with self.assertRaises(GLib.GError):
            node = BlockDev.md_node_from_name("made_up_md")

        with self.assertRaisesRegexp(GLib.GError, r'No name'):
            BlockDev.md_name_from_node("no_such_node")

        succ = BlockDev.md_deactivate("bd_test_md");
        self.assertTrue(succ)

        succ = BlockDev.md_destroy(self.loop_dev)
        self.assertTrue(succ)
        succ = BlockDev.md_destroy(self.loop_dev2)
        self.assertTrue(succ)
        succ = BlockDev.md_destroy(self.loop_dev3)
        self.assertTrue(succ)
