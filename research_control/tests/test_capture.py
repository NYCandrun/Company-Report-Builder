from __future__ import annotations

import unittest

from research_control.capture import TextExtractor


class TextExtractionTests(unittest.TestCase):
    def test_inline_elements_join_as_rendered(self) -> None:
        extractor = TextExtractor()
        extractor.feed(
            "<p>Hello <b>big</b> world</p>"
            "<div><span>M</span><span>o</span><span>s</span><span>t</span> teams</div>"
            "<ul><li>one</li><li>two</li></ul><script>ignored()</script>"
        )
        self.assertEqual("Hello big world\nMost teams\none\ntwo\n", extractor.text())


if __name__ == "__main__":
    unittest.main()
