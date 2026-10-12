"""A test-only RFC 3161 time-stamp authority, for the anchor vectors (SPEC-SDK-0.2.0 A4).

TEST ONLY. Its keys are generated when a test runs and never written to the repository; no
certificate it makes is trusted by anything but these tests. It builds real DER: a root CA, a TSA
certificate (extendedKeyUsage timeStamping, critical) signed by it, and TimeStampResp tokens whose
SignedData carries a TSTInfo over the message imprint asked for, with the signed attributes a
TSA sets (contentType, messageDigest, signingCertificateV2). Switches make the bad tokens the
vectors need: another imprint, another signer, a certificate set in a different order.
Needs the [crypto] extra's packages (cryptography, asn1crypto).
"""
import datetime
import hashlib

import asn1crypto
from asn1crypto import algos, cms, tsp, x509 as ax509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

POLICY = "1.3.6.1.4.1.99999.1"       # a test policy OID
UTC = datetime.timezone.utc


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "onetrace TEST ONLY")])


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class TestTSA:
    """A root CA and a TSA certificate under it. `pem()` gives what a reader would pin."""

    __test__ = False      # a helper the anchor tests import, not a test class for pytest to collect

    def __init__(self, cn="onetrace test TSA", root=None):
        now = datetime.datetime(2026, 1, 1, tzinfo=UTC)
        if root is None:
            self.root_key = _key()
            self.root = (x509.CertificateBuilder()
                         .subject_name(_name("onetrace test root CA")).issuer_name(_name("onetrace test root CA"))
                         .public_key(self.root_key.public_key()).serial_number(x509.random_serial_number())
                         .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=3650))
                         .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                         .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
                         .add_extension(x509.SubjectKeyIdentifier.from_public_key(self.root_key.public_key()), critical=False)
                         .sign(self.root_key, hashes.SHA256()))
        else:
            self.root_key, self.root = root.root_key, root.root
        self.key = _key()
        self.cert = (x509.CertificateBuilder()
                     .subject_name(_name(cn)).issuer_name(self.root.subject)
                     .public_key(self.key.public_key()).serial_number(x509.random_serial_number())
                     .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=3650))
                     .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                     .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
                     .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
                     .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.root_key.public_key()), critical=False)
                     .sign(self.root_key, hashes.SHA256()))

    def cert_der(self):
        return self.cert.public_bytes(serialization.Encoding.DER)

    def root_der(self):
        return self.root.public_bytes(serialization.Encoding.DER)

    def cert_sha256(self):
        return hashlib.sha256(self.cert_der()).hexdigest()

    def response(self, message: bytes, gen_time=None, *, imprint=None, signer=None, certs="tsa-then-root",
                 serial=1, nonce=None, status="granted"):
        """A granted TimeStampResp over sha256(`message`) (or over the raw `imprint` given)."""
        signer = signer or self
        gen_time = gen_time or datetime.datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)
        fields = {
            "version": "v1",
            "policy": POLICY,
            "message_imprint": {"hash_algorithm": {"algorithm": "sha256"},
                                "hashed_message": imprint if imprint is not None else hashlib.sha256(message).digest()},
            "serial_number": serial,
            "gen_time": gen_time,
        }
        if nonce is not None:
            fields["nonce"] = nonce
        if status != "granted":
            # A refusal carries no token, which asn1crypto's schema won't build: the DER by hand,
            # TimeStampResp { PKIStatusInfo { status } }.
            code = {"rejection": 2, "waiting": 3}[status]
            return bytes([0x30, 0x05, 0x30, 0x03, 0x02, 0x01, code])
        tst = tsp.TSTInfo(fields)
        econtent = tst.dump()
        a_cert = ax509.Certificate.load(signer.cert_der())
        ess = tsp.SigningCertificateV2({"certs": [{"hash_algorithm": {"algorithm": "sha256"},
                                                    "cert_hash": hashlib.sha256(signer.cert_der()).digest()}]})
        signed_attrs = cms.CMSAttributes([
            {"type": "content_type", "values": ["tst_info"]},
            {"type": "message_digest", "values": [hashlib.sha256(econtent).digest()]},
            {"type": "signing_certificate_v2", "values": [ess]},
        ])
        signature = signer.key.sign(signed_attrs.dump(), padding.PKCS1v15(), hashes.SHA256())
        order = {"tsa-then-root": [signer.cert_der(), self.root_der()],
                 "root-then-tsa": [self.root_der(), signer.cert_der()],
                 "tsa-only": [signer.cert_der()], "none": []}[certs]
        sd = cms.SignedData({
            "version": "v3",
            "digest_algorithms": [algos.DigestAlgorithm({"algorithm": "sha256"})],
            "encap_content_info": {"content_type": "tst_info", "content": asn1crypto.core.ParsableOctetString(econtent)},
            "certificates": [ax509.Certificate.load(c) for c in order] or None,
            "signer_infos": [{
                "version": "v1",
                "sid": cms.SignerIdentifier({"issuer_and_serial_number": {
                    "issuer": a_cert.issuer, "serial_number": a_cert.serial_number}}),
                "digest_algorithm": {"algorithm": "sha256"},
                "signed_attrs": signed_attrs,
                "signature_algorithm": {"algorithm": "rsassa_pkcs1v15"},
                "signature": signature,
            }],
        })
        if sd["certificates"].native is None:
            del sd["certificates"]
        resp = tsp.TimeStampResp({"status": {"status": "granted"},
                                  "time_stamp_token": {"content_type": "signed_data", "content": sd}})
        return resp.dump()
