import subprocess
import unittest

from scripts.test_no_avx import check_tls_result


class NoAvxTests(unittest.TestCase):
    def result(self, code=1, error="Error: invalid peer certificate: UnknownIssuer"):
        return subprocess.CompletedProcess([], code, stdout="", stderr=error)

    def test_certificate_verification_is_the_expected_failure(self):
        check_tls_result(self.result())
        check_tls_result(self.result(error="Error: certificate verify failed"))

    def test_illegal_instruction_is_not_accepted(self):
        with self.assertRaisesRegex(RuntimeError, "exit 132"):
            check_tls_result(self.result(code=132, error="Illegal instruction"))

    def test_other_signals_are_not_accepted(self):
        for code in (-4, 137, 139):
            with self.subTest(code=code), self.assertRaises(RuntimeError):
                check_tls_result(self.result(code=code))

    def test_network_or_argument_errors_do_not_pass_as_tls_coverage(self):
        for error in ("Connection refused", "Error: unrecognized argument", ""):
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                check_tls_result(self.result(error=error))

    def test_success_without_certificate_verification_is_not_accepted(self):
        with self.assertRaises(RuntimeError):
            check_tls_result(self.result(code=0))


if __name__ == "__main__":
    unittest.main()
