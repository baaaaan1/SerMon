import unittest

from line_endings import (
    DEFAULT_LINE_ENDING,
    LINE_ENDING_BY_KEY,
    LINE_ENDING_MODES,
    ParsedFragment,
    SerialTextParser,
)


class LineEndingModeTests(unittest.TestCase):
    def test_mode_mappings(self):
        self.assertEqual(
            [mode.key for mode in LINE_ENDING_MODES],
            ["none", "lf", "cr", "crlf"],
        )
        self.assertEqual(LINE_ENDING_BY_KEY["none"].tx_suffix, b"")
        self.assertEqual(LINE_ENDING_BY_KEY["lf"].tx_suffix, b"\n")
        self.assertEqual(LINE_ENDING_BY_KEY["cr"].tx_suffix, b"\r")
        self.assertEqual(LINE_ENDING_BY_KEY["crlf"].tx_suffix, b"\r\n")
        self.assertEqual(LINE_ENDING_BY_KEY["none"].rx_delimiter, None)
        self.assertEqual(LINE_ENDING_BY_KEY["lf"].rx_delimiter, "\n")
        self.assertEqual(LINE_ENDING_BY_KEY["cr"].rx_delimiter, "\r")
        self.assertEqual(LINE_ENDING_BY_KEY["crlf"].rx_delimiter, "\r\n")
        self.assertEqual(DEFAULT_LINE_ENDING, "crlf")

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            SerialTextParser("unknown")


class SerialTextParserTests(unittest.TestCase):
    def test_no_line_ending_streams_decoded_text_immediately(self):
        parser = SerialTextParser("none")

        self.assertEqual(parser.feed(b"hello"), [ParsedFragment("hello", False)])
        self.assertEqual(
            parser.feed(b" world"), [ParsedFragment(" world", False)])
        self.assertEqual(parser.flush(), "")

    def test_lf_parses_multiple_empty_and_partial_records(self):
        parser = SerialTextParser("lf")

        self.assertEqual(
            parser.feed(b"one\ntwo\n\npartial"),
            [
                ParsedFragment("one\n", True),
                ParsedFragment("two\n", True),
                ParsedFragment("\n", True),
            ],
        )
        self.assertEqual(parser.flush(), "partial")

    def test_cr_parses_records(self):
        parser = SerialTextParser("cr")

        self.assertEqual(
            parser.feed(b"one\rtwo\r"),
            [ParsedFragment("one\n", True), ParsedFragment("two\n", True)],
        )

    def test_crlf_is_exact_and_can_span_chunks(self):
        parser = SerialTextParser("crlf")

        self.assertEqual(parser.feed(b"one\ninside\r"), [])
        self.assertEqual(
            parser.feed(b"\ntwo\r\n"),
            [
                ParsedFragment("one\ninside\n", True),
                ParsedFragment("two\n", True),
            ],
        )

    def test_utf8_character_can_span_chunks(self):
        parser = SerialTextParser("lf")
        encoded = "A\u20acB\n".encode("utf-8")

        self.assertEqual(parser.feed(encoded[:2]), [])
        self.assertEqual(parser.feed(encoded[2:3]), [])
        self.assertEqual(
            parser.feed(encoded[3:]), [ParsedFragment("A\u20acB\n", True)])

    def test_invalid_bytes_are_replaced(self):
        parser = SerialTextParser("lf")

        self.assertEqual(
            parser.feed(b"bad:\xff\n"), [ParsedFragment("bad:\ufffd\n", True)])

    def test_flush_finalizes_incomplete_utf8(self):
        parser = SerialTextParser("lf")

        self.assertEqual(parser.feed(b"partial:\xe2"), [])
        self.assertEqual(parser.flush(), "partial:\ufffd")
        self.assertEqual(
            parser.feed(b"clean\n"), [ParsedFragment("clean\n", True)])

    def test_reset_discards_pending_data(self):
        parser = SerialTextParser("lf")
        parser.feed(b"discard me")

        parser.reset()

        self.assertEqual(parser.feed(b"kept\n"), [ParsedFragment("kept\n", True)])

    def test_mode_change_discards_old_state(self):
        parser = SerialTextParser("lf")
        parser.feed(b"old")

        parser.set_mode("cr")

        self.assertEqual(parser.mode.key, "cr")
        self.assertEqual(parser.feed(b"new\r"), [ParsedFragment("new\n", True)])

    def test_pending_buffer_is_bounded(self):
        parser = SerialTextParser("lf", max_pending_chars=4)

        self.assertEqual(parser.feed(b"abcde"), [ParsedFragment("abcde", False)])
        self.assertEqual(
            parser.feed(b"tail\n"), [ParsedFragment("tail\n", True)])

    def test_buffer_cap_preserves_partial_crlf_delimiter(self):
        parser = SerialTextParser("crlf", max_pending_chars=4)

        self.assertEqual(
            parser.feed(b"abcde\r"), [ParsedFragment("abcde", False)])
        self.assertEqual(parser.feed(b"\n"), [ParsedFragment("\n", True)])

    def test_pending_limit_must_be_positive(self):
        with self.assertRaises(ValueError):
            SerialTextParser(max_pending_chars=0)


if __name__ == "__main__":
    unittest.main()
