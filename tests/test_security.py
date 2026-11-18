import socket
import unittest

from app.security import UnsafeMediaURL, UnsafeRequest, validate_batch, validate_bearer_token, validate_media_url, validate_request_context


def public_dns(host, port, type=socket.SOCK_STREAM):
    return [(socket.AF_INET, type, 6, "", ("8.8.8.8", port))]


def private_dns(host, port, type=socket.SOCK_STREAM):
    return [(socket.AF_INET, type, 6, "", ("127.0.0.1", port))]


class SecurityTests(unittest.TestCase):
    def test_tailnet_request_allows_loopback_or_tailscale_and_requires_same_origin(self):
        validate_request_context("tailnet", "127.0.0.1", "dell-pc.tail187694.ts.net", "https://dell-pc.tail187694.ts.net", "https://dell-pc.tail187694.ts.net")
        validate_request_context("tailnet", "100.64.0.2", "dell-pc.tail187694.ts.net", None, "https://dell-pc.tail187694.ts.net")
        validate_request_context("tailnet", "100.127.255.254", "dell-pc.tail187694.ts.net", None, "https://dell-pc.tail187694.ts.net")
        validate_request_context("tailnet", "fd7a:115c:a1e0::1234", "dell-pc.tail187694.ts.net", None, "https://dell-pc.tail187694.ts.net")
        for address in ("100.128.0.1", "192.168.1.10", "8.8.8.8"):
            with self.subTest(address=address), self.assertRaisesRegex(UnsafeRequest, "Tailscale"):
                validate_request_context("tailnet", address, "dell-pc.tail187694.ts.net", None, "https://dell-pc.tail187694.ts.net")
        with self.assertRaisesRegex(UnsafeRequest, "Origin"):
            validate_request_context("tailnet", "100.64.0.2", "dell-pc.tail187694.ts.net", "https://evil.example", "https://dell-pc.tail187694.ts.net")

    def test_token_mode_requires_exact_bearer_token(self):
        validate_bearer_token("Bearer secret-value", "secret-value")
        with self.assertRaisesRegex(UnsafeRequest, "รหัสเข้าถึง"):
            validate_bearer_token("Bearer wrong", "secret-value")

    def test_allows_supported_https_platform(self):
        self.assertEqual(validate_media_url("https://youtu.be/demo", resolver=public_dns), "https://youtu.be/demo")

    def test_rejects_http_and_custom_port(self):
        with self.assertRaisesRegex(UnsafeMediaURL, "HTTPS"):
            validate_media_url("http://youtube.com/demo", resolver=public_dns)
        with self.assertRaisesRegex(UnsafeMediaURL, "พอร์ต"):
            validate_media_url("https://youtube.com:8443/demo", resolver=public_dns)

    def test_rejects_credentials_and_unknown_platform(self):
        with self.assertRaisesRegex(UnsafeMediaURL, "credentials"):
            validate_media_url("https://user:pass@youtube.com/demo", resolver=public_dns)
        with self.assertRaisesRegex(UnsafeMediaURL, "ยังไม่ได้รับอนุญาต"):
            validate_media_url("https://example.com/demo", resolver=public_dns)

    def test_rejects_private_literal_and_dns_result(self):
        with self.assertRaisesRegex(UnsafeMediaURL, "private"):
            validate_media_url("https://127.0.0.1/demo", direct_hosts={"127.0.0.1"}, resolver=private_dns)
        with self.assertRaisesRegex(UnsafeMediaURL, "DNS ชี้"):
            validate_media_url("https://youtube.com/demo", resolver=private_dns)

    def test_batch_is_atomic_and_deduplicated_before_creation(self):
        urls = validate_batch(["https://youtu.be/a", "https://youtu.be/a", "https://vimeo.com/b"], resolver=public_dns)
        self.assertEqual(urls, ["https://youtu.be/a", "https://vimeo.com/b"])
        with self.assertRaisesRegex(UnsafeMediaURL, "ลำดับที่ 2"):
            validate_batch(["https://youtu.be/a", "http://127.0.0.1/"], resolver=public_dns)
