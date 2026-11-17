import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import requests

from bots.shared_social.draft_images import ImageError, SIZES, download_image, render_images
from bots.shared_social.shopify_drafts import make_drafts
from bots.shared_social.test_shopify_drafts import product
from bots.shared_social.test_shopify_catalog import Response


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.draft = make_drafts([product("mug-cat", "Cat Mug")])[0]

    def test_real_renderer_sizes_hashes_rgb_and_no_embedded_metadata(self):
        source = io.BytesIO()
        Image.new("RGBA", (200, 400), (200, 20, 50, 255)).save(source, "PNG")
        with tempfile.TemporaryDirectory() as root:
            first = render_images(self.draft, root, downloader=lambda _: source.getvalue())
            self.assertEqual(first, render_images(self.draft, root, downloader=lambda _: source.getvalue()))
            for platform, asset in first.items():
                path = Path(root) / asset["path"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), asset["sha256"])
                with Image.open(path) as image:
                    self.assertEqual(image.size, SIZES[platform])
                    self.assertEqual(image.mode, "RGB")
                    self.assertEqual(image.format, "JPEG")
                    self.assertFalse(image.getexif())

    def test_invalid_bytes_and_excessive_pixels_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ImageError):
                render_images(self.draft, root, downloader=lambda _: b"not an image")
            source = io.BytesIO()
            Image.new("RGB", (30, 30)).save(source, "PNG")
            with patch("bots.shared_social.draft_images.MAX_PIXELS", 100):
                with self.assertRaises(ImageError):
                    render_images(self.draft, root, downloader=lambda _: source.getvalue())

    def test_unsafe_download_url_never_requests(self):
        session = unittest.mock.Mock()
        with self.assertRaises(ImageError):
            download_image("https://127.0.0.1/secret", session=session)
        session.get.assert_not_called()

    def test_redirect_html_oversized_and_transport_error_rejected(self):
        for response in [Response(raw=b"img", status=302),
                         Response(raw=b"<html>", headers={"Content-Type": "text/html"}),
                         Response(raw=b"x"*11, headers={"Content-Type": "image/png"})]:
            session = unittest.mock.Mock()
            session.get.return_value = response
            with patch("bots.shared_social.draft_images.MAX_BYTES", 10):
                with self.assertRaises(ImageError):
                    download_image(self.draft["image_url"], session=session)
            self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
            self.assertNotIn("headers", session.get.call_args.kwargs)
        session.get.side_effect = requests.RequestException("secret")
        with self.assertRaises(ImageError) as caught:
            download_image(self.draft["image_url"], session=session)
        self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
