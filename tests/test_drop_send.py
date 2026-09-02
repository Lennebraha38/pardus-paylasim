"""
Sürükle-bırak gönderim karar mantığı (#21) testleri.

`MainWindow._resolve_drop_send` saf bir statik yöntemdir: GTK örneği
gerektirmez, bırakılan ham yolları sınıflandırır. Headless (GTK'siz)
ortamda da koşar; yalnızca `os.path.isfile` gerçek dosya sistemine bakar,
o yüzden testler geçici gerçek dosya/klasör üretir.
"""

import os
import tempfile
import unittest

from pardus_paylasim.window import MainWindow


class TestResolveDropSend(unittest.TestCase):
    def setUp(self):
        # Gerçek dosya + gerçek klasör: os.path.isfile ayrımını sınamak için.
        self._tmp = tempfile.TemporaryDirectory()
        self.file_path = os.path.join(self._tmp.name, "belge.pdf")
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write("içerik")
        self.dir_path = os.path.join(self._tmp.name, "klasor")
        os.mkdir(self.dir_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_device_returns_no_device(self):
        # Hedef cihaz yoksa dosya geçerli olsa da "no_device" döner.
        status, files = MainWindow._resolve_drop_send([self.file_path], has_device=False)
        self.assertEqual(status, "no_device")

    def test_device_but_only_folder_returns_no_files(self):
        # Cihaz var ama yalnızca klasör bırakılmış → gönderilecek dosya yok.
        status, files = MainWindow._resolve_drop_send([self.dir_path], has_device=True)
        self.assertEqual(status, "no_files")
        self.assertEqual(files, [])

    def test_device_and_file_returns_send(self):
        # Cihaz + gerçek dosya → gönderime hazır, yalnız dosya yolu döner.
        status, files = MainWindow._resolve_drop_send(
            [self.file_path, self.dir_path], has_device=True
        )
        self.assertEqual(status, "send")
        self.assertEqual(files, [self.file_path])

    def test_none_and_missing_paths_filtered(self):
        # None ve var olmayan yollar elenmeli; kalan gerçek dosya gönderilir.
        missing = os.path.join(self._tmp.name, "yok.txt")
        status, files = MainWindow._resolve_drop_send(
            [None, missing, self.file_path], has_device=True
        )
        self.assertEqual(status, "send")
        self.assertEqual(files, [self.file_path])

    def test_empty_list_with_device_returns_no_files(self):
        status, files = MainWindow._resolve_drop_send([], has_device=True)
        self.assertEqual(status, "no_files")
        self.assertEqual(files, [])


if __name__ == "__main__":
    unittest.main()
