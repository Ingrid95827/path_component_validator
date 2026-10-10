# SPDX-License-Identifier: MIT
"""Tests for path_component_validator.core."""

import unittest

from path_component_validator import (
    Os,
    Violation,
    ValidationReport,
    WindowsValidator,
    PosixValidator,
    VALIDATORS,
    validate_path,
)


class TestWindowsValidator(unittest.TestCase):
    def setUp(self):
        self.v = WindowsValidator()

    def test_valid_segments_accepted(self):
        report = self.v.validate(["foo", "bar", "baz"])
        self.assertTrue(report.valid)
        self.assertEqual(report.violations, [])

    def test_illegal_angle_bracket(self):
        report = self.v.validate(["foo<bar"])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "illegal_char")

    def test_all_illegal_chars_caught(self):
        for ch in '<>:"\\\\|?*':
            component = f"a{ch}b"
            report = self.v.validate([component])
            self.assertFalse(
                report.valid, f"expected violation for {ch!r}"
            )
            self.assertEqual(report.violations[0].rule, "illegal_char")

    def test_reserved_name_con(self):
        report = self.v.validate(["CON"])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "reserved_name")

    def test_reserved_name_case_insensitive(self):
        report = self.v.validate(["con"])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "reserved_name")

    def test_reserved_name_with_extension(self):
        report = self.v.validate(["CON.txt"])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "reserved_name")

    def test_reserved_name_with_trailing_dot(self):
        report = self.v.validate(["CON."])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "reserved_name")

    def test_reserved_name_lpt1(self):
        report = self.v.validate(["LPT1"])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "reserved_name")

    def test_segment_too_long(self):
        component = "a" * (self.v.MAX_LENGTH + 1)
        report = self.v.validate([component])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "too_long")
        self.assertIn("256", report.violations[0].reason)

    def test_segment_at_max_length_ok(self):
        component = "a" * self.v.MAX_LENGTH
        report = self.v.validate([component])
        self.assertTrue(report.valid)

    def test_empty_segment_rejected(self):
        report = self.v.validate([""])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "empty")

    def test_multiple_components_ordered(self):
        report = self.v.validate(["good", "CON", "bad<"])
        self.assertEqual(len(report.violations), 2)
        self.assertEqual(report.violations[0].component, "CON")
        self.assertEqual(report.violations[1].component, "bad<")

    def test_non_string_component_raises(self):
        with self.assertRaises(TypeError):
            self.v.validate(["ok", 123])

    def test_case_not_flagged_on_windows(self):
        # Windows is case-insensitive but case-preserving; no case violation.
        report = self.v.validate(["MyFile", "myfile"])
        self.assertTrue(report.valid)


class TestPosixValidator(unittest.TestCase):
    def setUp(self):
        self.v = PosixValidator()

    def test_valid_segments_accepted(self):
        report = self.v.validate(["foo", "bar", "baz"])
        self.assertTrue(report.valid)

    def test_null_byte_rejected(self):
        report = self.v.validate(["foo\x00bar"])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "illegal_char")

    def test_forward_slash_rejected(self):
        report = self.v.validate(["foo/bar"])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "illegal_char")

    def test_dot_directory_rejected(self):
        report = self.v.validate(["."])
        self.assertFalse(report.valid)
        rules = [v.rule for v in report.violations]
        self.assertIn("dot_directory", rules)

    def test_dotdot_directory_rejected(self):
        report = self.v.validate([".."])
        self.assertFalse(report.valid)
        rules = [v.rule for v in report.violations]
        self.assertIn("dot_directory", rules)

    def test_reserved_names_empty(self):
        self.assertEqual(self.v.reserved_names(), frozenset())

    def test_segment_too_long(self):
        component = "a" * (self.v.MAX_LENGTH + 1)
        report = self.v.validate([component])
        self.assertFalse(report.valid)
        self.assertEqual(report.violations[0].rule, "too_long")

    def test_segment_at_max_length_ok(self):
        component = "a" * self.v.MAX_LENGTH
        report = self.v.validate([component])
        self.assertTrue(report.valid)

    def test_case_sensitive_no_violation(self):
        report = self.v.validate(["MyFile", "myfile"])
        self.assertTrue(report.valid)

    def test_special_chars_ok(self):
        # Characters illegal on Windows but fine on POSIX.
        report = self.v.validate(["file<with>brackets"])
        self.assertTrue(report.valid)


class TestValidatePathFunction(unittest.TestCase):
    def test_default_os_is_posix(self):
        report = validate_path(["good", "CON"])
        self.assertTrue(report.valid)

    def test_string_target_os_windows(self):
        report = validate_path(["CON"], target_os="windows")
        self.assertFalse(report.valid)

    def test_enum_target_os_windows(self):
        report = validate_path(["CON"], target_os=Os.WINDOWS)
        self.assertFalse(report.valid)

    def test_unknown_target_os_raises(self):
        with self.assertRaises(ValueError):
            validate_path(["foo"], target_os="plan9")

    def test_returns_validation_report(self):
        report = validate_path(["foo"])
        self.assertIsInstance(report, ValidationReport)

    def test_violation_fields_populated(self):
        report = validate_path(["CON"], target_os=Os.WINDOWS)
        v = report.violations[0]
        self.assertIsInstance(v, Violation)
        self.assertEqual(v.component, "CON")
        self.assertEqual(v.rule, "reserved_name")
        self.assertTrue(v.reason)


class TestValidationReport(unittest.TestCase):
    def test_empty_report_is_valid(self):
        report = ValidationReport(violations=[])
        self.assertTrue(report.valid)

    def test_non_empty_report_is_invalid(self):
        v = Violation(component="x", rule="empty", reason="bad")
        report = ValidationReport(violations=[v])
        self.assertFalse(report.valid)


class TestValidatorsRegistry(unittest.TestCase):
    def test_contains_both_enums_and_strings(self):
        self.assertIn(Os.WINDOWS, VALIDATORS)
        self.assertIn(Os.POSIX, VALIDATORS)
        self.assertIn("windows", VALIDATORS)
        self.assertIn("posix", VALIDATORS)

    def test_returns_validator_instances(self):
        self.assertIsInstance(VALIDATORS[Os.WINDOWS], WindowsValidator)
        self.assertIsInstance(VALIDATORS[Os.POSIX], PosixValidator)


if __name__ == "__main__":
    unittest.main()
