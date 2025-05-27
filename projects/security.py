"""
Security utilities for GWAY: node certificate generation and registration via CLI.
Commands:
  gway security generate-node
  gway security register-node --csr-path <path> --node-id <id>
"""
import os
import sys
import hashlib
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timedelta
from gway import gw


def get_node_serial():
    """Retrieve Raspberry Pi serial number from /proc/cpuinfo."""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    return line.strip().split(':')[1].strip()
    except Exception:
        pass
    # Fallback to hostname-based ID
    return hashlib.sha256(os.uname().nodename.encode()).hexdigest()[:16]


def generate_node():
    """
    Generate a new RSA key pair and CSR for this node.
    Outputs key and CSR to gw.resource('temp','security').
    Prints Node ID and the server-side command to register.
    """
    node_id = get_node_serial()
    temp_dir = Path(gw.resource('temp', 'security'))
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Generate RSA key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = temp_dir / f"{node_id}.key.pem"
    with open(key_path, 'wb') as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # Build CSR
    csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, node_id),
    ])).sign(key, hashes.SHA256())
    csr_path = temp_dir / f"{node_id}.csr.pem"
    with open(csr_path, 'wb') as f:
        f.write(csr.public_bytes(serialization.Encoding.PEM))

    print(f"Node ID: {node_id}")
    print(f"Generated key  : {key_path}")
    print(f"Generated CSR  : {csr_path}\n")
    print("To register this node on the server, run:")
    print(
        f"    gway security register-node \
"
        f"--csr-path {csr_path} \
"
        f"--node-id {node_id}"
    )
    return 0


def register_node(csr_path: str = None, node_id: str = None):  # CLI will pass as kwargs
    """
    On server: sign a node CSR with the CA and write out the node certificate.
    Defaults assume CA key and cert at gw.resource('data','security').
    """
    if not csr_path or not node_id:
        print("Error: --csr-path and --node-id are required.", file=sys.stderr)
        return 1

    csr_path = Path(csr_path)
    if not csr_path.exists():
        print(f"Error: CSR file not found: {csr_path}", file=sys.stderr)
        return 1

    data_dir = Path(gw.resource('data', 'security'))
    ca_key_path = data_dir / 'ca.key.pem'
    ca_cert_path = data_dir / 'ca.cert.pem'
    if not ca_key_path.exists() or not ca_cert_path.exists():
        print("Error: CA key or cert not found in data/security/", file=sys.stderr)
        return 1

    # Load CA key and cert
    with open(ca_key_path, 'rb') as f:
        ca_key = serialization.load_pem_private_key(f.read(), password=None)
    with open(ca_cert_path, 'rb') as f:
        ca_cert = x509.load_pem_x509_certificate(f.read())

    # Load CSR
    with open(csr_path, 'rb') as f:
        csr = x509.load_pem_x509_csr(f.read())

    # Build certificate
    cert = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=365*5))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .sign(private_key=ca_key, algorithm=hashes.SHA256())
    )

    # Write node cert
    out_dir = data_dir / 'nodes'
    out_dir.mkdir(parents=True, exist_ok=True)
    cert_path = out_dir / f"{node_id}.cert.pem"
    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Signed certificate for node {node_id}:")
    print(f"  {cert_path}")
    return 0
