import json
import tempfile
import unittest
from pathlib import Path

from music_downloader.app import DownloadHistory, clean_filename, run_from_config


class CleanFilenameTests(unittest.TestCase):
    def test_replaces_invalid_characters_and_trims(self) -> None:
        self.assertEqual(clean_filename('  my:/song*name?.mp3  '), "my__song_name.mp3")


class DownloadHistoryTests(unittest.TestCase):
    def test_records_downloads_and_processed_posts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            history = DownloadHistory(db_path)

            history.record_download(
                "site",
                "https://example.com/post-1",
                "https://example.com/song.mp3",
                Path("/tmp/song.mp3"),
                "20260707_000000",
            )
            history.mark_post_processed("site", "https://example.com/post-1", "20260707_000000")

            self.assertTrue(history.has_downloaded("https://example.com/song.mp3"))
            self.assertTrue(history.has_processed_post("https://example.com/post-1"))
            self.assertEqual(history.download_count(), 1)


class DownloaderIntegrationTests(unittest.TestCase):
    def test_downloads_audio_and_video_into_timestamped_folders_and_skips_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            output_root = root / "downloads"
            db_path = root / "history.sqlite3"

            (source / "song name?.mp3").write_bytes(b"audio-bytes")
            (source / "clip:name.mp4").write_bytes(b"video-bytes")

            post = source / "post1.html"
            post.write_text(
                """
                <html>
                  <body>
                    <a href="song%20name%3F.mp3">song</a>
                    <a href="clip%3Aname.mp4">clip</a>
                    <a href="song%20name%3F.mp3">song duplicate</a>
                  </body>
                </html>
                """,
                encoding="utf-8",
            )
            index = source / "index.html"
            index.write_text(
                '<html><body><a href="post1.html">new post</a></body></html>',
                encoding="utf-8",
            )

            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "output_root": str(output_root),
                        "database_path": str(db_path),
                        "sites": [
                            {
                                "name": "local",
                                "url": index.as_uri(),
                                "post_patterns": ["post1.html"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            first_summary = run_from_config(config_path)
            self.assertEqual(first_summary["posts_checked"], 1)
            self.assertEqual(first_summary["files_downloaded"], 2)
            self.assertEqual(first_summary["files_skipped"], 1)

            run_directories = [path for path in output_root.iterdir() if path.is_dir()]
            self.assertEqual(len(run_directories), 1)
            run_directory = run_directories[0]
            self.assertTrue((run_directory / "Audio" / "song name.mp3").exists())
            self.assertTrue((run_directory / "Video" / "clip_name.mp4").exists())

            second_summary = run_from_config(config_path)
            self.assertEqual(second_summary["posts_checked"], 0)
            self.assertGreaterEqual(second_summary["files_skipped"], 1)
            self.assertEqual(len([path for path in output_root.iterdir() if path.is_dir()]), 1)


if __name__ == "__main__":
    unittest.main()
