"""Tests for translator.office.text_utils.should_translate()."""

from translator.office.text_utils import should_translate
from translator.office.text_utils import split_preserving_whitespace


class TestShouldTranslate:
    def test_empty_string_is_false(self):
        assert should_translate("") is False

    def test_whitespace_only_is_false(self):
        assert should_translate("   \t\n") is False

    def test_normal_english_sentence_is_true(self):
        assert should_translate("Hello, world!") is True

    def test_single_char_is_false(self):
        assert should_translate("a") is False
        assert should_translate(" I ") is False

    def test_pure_integer_is_false(self):
        assert should_translate("123") is False
        assert should_translate("1234567") is False

    def test_pure_decimal_is_false(self):
        assert should_translate("3.14") is False
        assert should_translate("1,234.56") is False

    def test_pure_symbols_is_false(self):
        assert should_translate("***") is False
        assert should_translate("---") is False
        assert should_translate("—") is False
        assert should_translate("...") is False

    def test_mixed_alpha_and_digits_is_true(self):
        assert should_translate("V2.0") is True
        assert should_translate("iPhone 15") is True

    def test_chinese_is_true(self):
        assert should_translate("中文测试") is True


class TestSplitPreservingWhitespace:
    def test_no_whitespace(self):
        assert split_preserving_whitespace("hello") == ("", "hello", "")

    def test_leading_whitespace(self):
        assert split_preserving_whitespace("  hello") == ("  ", "hello", "")

    def test_trailing_whitespace(self):
        assert split_preserving_whitespace("hello\n") == ("", "hello", "\n")

    def test_both(self):
        assert split_preserving_whitespace("  hello  ") == ("  ", "hello", "  ")

    def test_only_whitespace(self):
        lead, core, trail = split_preserving_whitespace("   ")
        assert lead + core + trail == "   "
        assert core == ""
