"""Official raster identity must never be replaced by a reconstructed symbol."""
import base64
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / 'static/brand'


class VisualIdentityTests(unittest.TestCase):
    def test_svg_embeds_original_pixels_without_reconstructed_paths(self):
        svg = ET.parse(BRAND / 'dashboardos-symbol.svg').getroot()
        images = list(svg)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].tag, '{http://www.w3.org/2000/svg}image')
        uri = images[0].attrib['href']
        self.assertTrue(uri.startswith('data:image/png;base64,'))
        self.assertEqual(base64.b64decode(uri.split(',', 1)[1]),
                         (BRAND / 'dashboardos-official-original.png').read_bytes())
        self.assertNotIn('transform', images[0].attrib)

    def test_png_fallback_preserves_original_and_manifest_dimensions_are_true(self):
        original = BRAND / 'dashboardos-official-original.png'
        self.assertEqual(original.read_bytes(), (BRAND / 'dashboardos-icon.png').read_bytes())
        manifest = json.loads((BRAND / 'manifest.webmanifest').read_text(encoding='utf-8'))
        with Image.open(original) as image:
            image.verify()
            expected = f'{image.width}x{image.height}'
        for icon in manifest['icons']:
            path = ROOT / urlsplit(icon['src']).path.lstrip('/')
            self.assertTrue(path.is_file())
            if icon['type'] == 'image/png':
                self.assertEqual(icon['sizes'], expected)

    def test_presentation_crop_is_square_inside_the_unmodified_raster(self):
        svg = ET.parse(BRAND / 'dashboardos-symbol.svg').getroot()
        x, y, width, height = map(float, svg.attrib['viewBox'].split())
        with Image.open(BRAND / 'dashboardos-official-original.png') as image:
            self.assertEqual(width, height)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + width, image.width)
            self.assertLessEqual(y + height, image.height)
