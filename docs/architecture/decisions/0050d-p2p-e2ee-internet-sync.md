---
adr_number: 0050d
title: P2P E2EE Internet Sync (Phase 2)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- observability
- performance
- privacy
- scalability
- security
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0001a
- ADR-0036
- ADR-0050
- ADR-0050a
- ADR-0050b
- ADR-0050c
- ADR-0050d
implementation_status: REJECTED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  affected_adrs:
  - ADR-0001a
  - ADR-0036
  - ADR-0050
  - ADR-0050a
  - ADR-0050b
  - ADR-0050c
  - ADR-0050d
  affected_contracts:
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests: []
---


# ADR-0050d: P2P E2EE Internet Sync (Phase 2)

**Status:** ✅ Accepted (Future Implementation)

**Date:** 2025-10-16

**Deciders:** K1 Architecture Team, Security Lead

**Technical Story:** Multi-Device Family Sync - Phase 2 Internet E2EE

**Parent ADR:** ADR-0050 (Multi-Device Family Sync Strategy)

**Sibling ADRs:** ADR-0050a (SessionState Coherence), ADR-0050b (CRDT Merge), ADR-0050c (LAN Sync)

**Related:** ADR-0036 (E2EE for RED band), ADR-0001a (K0 Bridge Communication)

---

## Context

### Problem Statement

**Phase 2 Implementation:** When family devices are on different networks (office, school, travel), how should they sync memories via internet while maintaining **E2EE privacy** (no cloud intermediary)?

### Current Situation (Phase 1)

- Devices sync over LAN (<1ms)
- Remote devices use manual "Sync Now" button (temporary MVP)
- No internet sync protocol yet

### Constraints (Phase 2)

| Constraint | Target | Why |
|-----------|--------|-----|
| **Encryption** | E2E, no intermediary | Privacy (zero-knowledge) |
| **Latency** | <500ms P95 | Acceptable for internet |
| **Connectivity** | Works behind firewalls/NAT | Most networks have firewall |
| **Fallback** | Automatic LAN when home | Prefer LAN (<1ms) over internet |
| **Battery** | <5% per hour active use | Remote sync intensive |
| **Cross-device** | iOS, Android, macOS, Windows | Protocol agnostic |
| **Privacy** | No metadata leakage | IP addresses, timestamps private |

---

## Decision

### **Phase 2: P2P E2EE Internet Tunnel + Automatic Network Detection**

**Three components:**

#### 1. Device Certificate Infrastructure

**Each device gets unique E2EE certificate:**

```python
class DeviceCertificate:
    """
    Ed25519 signing key + X25519 encryption key per device
    Rotated quarterly, revocation support
    """

    def __init__(self, device_id):
        self.device_id = device_id
        # Signing keypair (Ed25519)
        self.signing_key = nacl.signing.SigningKey.generate()
        self.verify_key = self.signing_key.verify_key

        # Encryption keypair (X25519)
        self.box = nacl.public.PrivateKey.generate()
        self.public_key = self.box.public_key

        # Certificate metadata
        self.issued_at = time.time()
        self.expires_at = self.issued_at + (90 * 24 * 3600)  # 90 days
        self.revoked = False

    def sign_message(self, message):
        """Sign message for authentication"""
        return self.signing_key.sign(message).signature

    def verify_message(self, message, signature, sender_verify_key):
        """Verify peer's signed message"""
        try:
            sender_verify_key.verify(message, signature)
            return True
        except nacl.exceptions.BadSignatureError:
            return False

    def encrypt_to(self, plaintext, peer_public_key):
        """Encrypt message to peer"""
        peer_box = nacl.public.PublicKey(peer_public_key)
        box = nacl.public.Box(self.box, peer_box)
        nonce = nacl.utils.random(nacl.public.Box.NONCE_SIZE)
        ciphertext = box.encrypt(plaintext, nonce).ciphertext
        return nonce + ciphertext

    def decrypt_from(self, nonce_and_ciphertext, peer_public_key):
        """Decrypt message from peer"""
        nonce = nonce_and_ciphertext[:24]
        ciphertext = nonce_and_ciphertext[24:]
        peer_box = nacl.public.PublicKey(peer_public_key)
        box = nacl.public.Box(self.box, peer_box)
        plaintext = box.decrypt(ciphertext, nonce)
        return plaintext
```

#### 2. P2P Connection Establishment

**Device-to-device internet tunnel (no cloud relay):**

```python
class P2PInternetTunnel:
    """
    P2P connection between two devices.
    Uses STUN (for NAT traversal) or relay fallback.
    """

    async def establish_connection(self, peer_device_id, peer_cert):
        """
        Establish E2EE tunnel to peer.

        1. Handshake: exchange certs + verify signatures
        2. Key agreement: establish shared secret
        3. Open tunnel: bidirectional encrypted channel
        """

        # Step 1: Exchange certificates
        my_cert = await self.get_my_certificate()

        handshake = {
            "device_id": self.device_id,
            "cert": my_cert.export(),
            "timestamp": time.time_ms(),
            "capabilities": ["sync", "e2ee", "crdt"]
        }

        # Sign handshake (prove device ID ownership)
        signature = my_cert.sign_message(json.dumps(handshake))
        handshake["signature"] = signature.hex()

        # Send handshake (or receive, depending on who initiates)
        await self.send_handshake(peer_device_id, handshake)
        peer_handshake = await self.receive_handshake(timeout=30)

        # Step 2: Verify peer certificate
        if not await self.verify_peer_cert(peer_handshake):
            raise SecurityError("Peer certificate verification failed")

        # Step 3: Establish encryption
        peer_public_key = peer_handshake["cert"]["public_key"]
        self.peer_public_key = peer_public_key

        # Step 4: Open encrypted tunnel
        self.tunnel_established = True
```

#### 3. Network Detection & Fallback

**Automatic preference: LAN > Internet**

```python
class NetworkDetector:
    """
    Detects available networks and chooses sync path.
    """

    async def detect_networks(self):
        """Find what networks are available"""

        # Check 1: Can we find peers on LAN?
        lan_peers = await self.mdns_discover()  # Phase 1 discovery

        if lan_peers:
            return {
                "type": "LAN",
                "peers": lan_peers,
                "latency": "<1ms",
                "prefer": True
            }

        # Check 2: Do we have internet?
        has_internet = await self.check_internet_connectivity()

        if not has_internet:
            return {"type": "OFFLINE", "status": "No connectivity"}

        # Check 3: Can we reach peer registry (lightweight)?
        # (Devices register their current IP, not their data)
        peer_ip_list = await self.query_peer_registry()

        if peer_ip_list:
            return {
                "type": "INTERNET",
                "peers": peer_ip_list,
                "latency": "100-500ms",
                "prefer": False
            }

        return {"type": "OFFLINE", "status": "No peers found"}


async def sync_with_fallback(self):
    """
    Sync with automatic fallback:
    1. Try LAN first
    2. If no LAN, try internet P2P
    3. If P2P fails, queue for later
    """

    networks = await self.detect_networks()

    if networks["type"] == "LAN":
        # Use Phase 1 LAN sync (TCP)
        await self.sync_via_lan(networks["peers"])

    elif networks["type"] == "INTERNET":
        # Use Phase 2 internet sync (P2P E2EE)
        await self.sync_via_p2p(networks["peers"])

    else:
        # Offline: queue changes, retry later
        logger.info("No connectivity, will sync when online")
        self.queue_outgoing_changes()
```

#### 4. Encrypted Sync Message Format

**K0 Bridge P07 with E2EE wrapper:**

```flatbuffers
namespace FamilyOS.P2PSync;

table P2PSyncMessage {
  version: ubyte = 1;
  sender_device_id: string;
  sender_cert_id: string;
  timestamp: ulong;

  // P07 payload (changes, vector clocks, CRDT)
  payload: [ubyte];  // Encrypted K0 Bridge P07
  payload_nonce: [ubyte];  // AEAD nonce

  // Authentication
  signature: [ubyte];  # Ed25519 signature over whole message

  // Metadata (not encrypted - for routing)
  message_id: string;  # Unique ID (for dedup)
  is_encrypted: bool = true;
}

# On wire:
# 1. Construct P07 message (changes, CRDT deltas)
# 2. Encrypt P07 with peer's public key (X25519 + ChaCha20-Poly1305)
# 3. Sign whole message with my signing key (Ed25519)
# 4. Send over internet
# 5. Peer decrypts + verifies signature + applies changes
```

#### 5. Sync Loop with Internet

```python
class InternetSyncManager:
    """Background sync over internet (Phase 2)"""

    async def continuous_internet_sync(self):
        """
        Background: sync with peers over internet
        Runs every 30 seconds (or on change)
        """

        while True:
            try:
                # Detect available networks
                networks = await self.detect_networks()

                if networks["type"] == "OFFLINE":
                    # No connectivity - wait
                    await asyncio.sleep(60)
                    continue

                # Get peer list (with E2EE certs)
                peers = networks["peers"]

                for peer_id, peer_info in peers.items():
                    # Ensure tunnel is established
                    tunnel = await self.get_or_establish_tunnel(peer_id)

                    # Get delta (changes since last sync)
                    delta = k0.get_delta(since=self.synced_until)

                    if delta:
                        # Wrap in P07 message
                        p07_msg = K0BridgeP07Message(
                            changes=delta,
                            vector_clock=self.get_vector_clock()
                        )

                        # Encrypt + sign
                        encrypted_msg = P2PSyncMessage(
                            payload=FlatBuffersEncode(p07_msg),
                            sender_device_id=self.device_id,
                            timestamp=time.time_ms()
                        )
                        encrypted_msg.payload = self.device_cert.encrypt_to(
                            encrypted_msg.payload,
                            peer_info["public_key"]
                        )
                        encrypted_msg.signature = self.device_cert.sign_message(
                            FlatBuffersEncode(encrypted_msg)
                        )

                        # Send over internet
                        await tunnel.send_message(encrypted_msg)

                    # Receive peer's changes
                    peer_msg = await tunnel.receive_message(timeout=5)
                    if peer_msg:
                        # Verify signature + decrypt
                        plaintext = self.device_cert.decrypt_from(
                            peer_msg.payload,
                            peer_info["public_key"]
                        )
                        peer_p07 = FlatBuffersDecode(plaintext)

                        # Merge changes (CRDT)
                        for change in peer_p07.changes:
                            k0.merge_crdt(change)

                # Update watermark
                self.synced_until = time.time_ms()

                # Wait for next sync
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Internet sync error: {e}")
                await asyncio.sleep(60)  # Backoff
```

---

## Security Considerations

### Threat Model

| Threat | Mitigation |
|--------|-----------|
| **MITM (Man-in-the-Middle)** | Certificate pinning + signature verification |
| **Replay attacks** | Timestamp + message_id deduplication |
| **IP tracking** | Use STUN, don't reveal device IPs in metadata |
| **Certificate compromise** | 90-day rotation, revocation list |
| **Eavesdropping** | ChaCha20-Poly1305 AEAD encryption |

### Privacy Properties

- ✅ **Zero-knowledge:** Server never sees plaintext
- ✅ **No metadata leakage:** Only message_id (opaque), timestamp (sync timing OK)
- ✅ **End-to-end:** Device-to-device encryption
- ✅ **Signature verification:** Authentication (peer is who they claim)

---

## Implementation Plan (M4-M5, parallel Phase 1)

| Week | Task | Owner | Details |
|------|------|-------|---------|
| **M3-W3** (plan) | Cert infrastructure design | Security | Ed25519, X25519, AEAD |
| **M4-W1** | Device certificate generation | Backend | Per-device key generation |
| **M4-W2** | Handshake protocol | Backend | Cert exchange + verification |
| **M4-W3** | STUN + NAT traversal | Infrastructure | NAT hole punching for P2P |
| **M4-W4** | Encrypted tunnel (QUIC) | Backend | Transport layer encryption |
| **M5-W1** | Network detection | Backend | LAN vs internet preference |
| **M5-W2** | P2P E2EE sync loop | Backend | Combine all above |
| **M5-W3** | Testing + chaos | QA | International latency, network failures |
| **M5-W4** | GA rollout | Ops | Feature flag → general availability |

---

## Testing Strategy

### WARD Tests (Phase 2)

```python
@test("Device certificates verify correctly")
async def _():
    device_a = create_test_device("iphone-mom")
    device_b = create_test_device("laptop-dad")

    # Handshake
    cert_a = device_a.device_cert.export()
    signature_a = device_a.device_cert.sign_message(cert_a)

    # Verify on device B
    verified = await device_b.device_cert.verify_message(
        cert_a,
        signature_a,
        device_a.device_cert.verify_key
    )
    assert verified


@test("E2EE encryption/decryption round-trip")
async def _():
    device_a = create_test_device("iphone-mom")
    device_b = create_test_device("laptop-dad")

    message = b"Hello from Mom"

    # Device A encrypts to Device B
    encrypted = device_a.device_cert.encrypt_to(
        message,
        device_b.device_cert.public_key
    )

    # Device B decrypts
    decrypted = device_b.device_cert.decrypt_from(
        encrypted,
        device_a.device_cert.public_key
    )

    assert decrypted == message


@test("Internet P2P sync <500ms latency")
async def _():
    device_a = create_test_device("iphone-mom")
    device_b = create_test_device("laptop-dad")

    # Simulate internet (no LAN)
    await device_a.disconnect_lan()
    await device_b.disconnect_lan()

    # Establish P2P tunnel
    tunnel = await device_a.establish_p2p_tunnel(device_b)

    # Write on device A
    start = time.time()
    await device_a.k0.write(MemoryItem(id="1", value="Test"))

    # Wait for sync to device B
    await wait_for_sync(device_b, timeout=1)
    latency_ms = (time.time() - start) * 1000

    assert latency_ms < 500
    assert await device_b.k0.read("1") != None


@test("Automatic LAN preference over internet")
async def _():
    device_a = create_test_device("iphone-mom")
    device_b = create_test_device("laptop-dad")
    device_c = create_test_device("tablet-kid")

    # Set up: device_b and _c on LAN, device_a on internet
    await device_a.disconnect_lan()
    await device_b.connect_lan()
    await device_c.connect_lan()

    # Write on device A
    await device_a.k0.write(MemoryItem(id="1"))

    # Sync should prefer: A → LAN tunnel to B/C (not internet tunnel)
    sync_paths = await capture_sync_paths()

    assert any(p == "LAN" for p in sync_paths)
    assert latency < 100  # LAN is fast


@test("Certificate revocation prevents sync")
async def _():
    device_a = create_test_device("iphone-mom")
    device_b = create_test_device("laptop-dad")

    # Establish tunnel
    tunnel = await device_a.establish_p2p_tunnel(device_b)
    assert tunnel.established

    # Revoke device A's certificate
    await device_a.device_cert.revoke()

    # Next sync should fail
    try:
        await device_a.send_sync_message(device_b)
        assert False, "Should have rejected revoked cert"
    except SecurityError:
        pass  # Expected
```

---

## Comparison: Phase 1 vs Phase 2

| Aspect | Phase 1 (LAN) | Phase 2 (Internet) |
|--------|---------------|-------------------|
| **Discovery** | mDNS on LAN | Certificate registry + manual pairing |
| **Transport** | TCP LAN | P2P internet (STUN/QUIC) |
| **Encryption** | None (LAN private) | E2EE (ChaCha20-Poly1305) |
| **Authentication** | Device ID verification | Certificate signing |
| **Latency** | <1ms | 100-500ms |
| **Remote devices** | Manual sync button | Automatic sync |
| **Battery** | Low | Moderate |
| **Use case** | Family at home | Family scattered |

---

## Observability Metrics (Phase 2)

```yaml
metrics:
  - name: "p2p_tunnel_establishment_latency"
    type: "histogram"
    buckets: [50, 100, 200, 500, 1000]  # ms

  - name: "e2ee_encryption_latency"
    type: "histogram"
    buckets: [1, 5, 10, 20]  # ms

  - name: "internet_sync_latency"
    type: "histogram"
    buckets: [100, 200, 300, 500, 1000]  # ms
    labels: ["peer_network"]

  - name: "network_type_preference"
    type: "counter"
    labels: ["type"]  # "LAN", "INTERNET", "OFFLINE"

  - name: "certificate_validations"
    type: "counter"
    labels: ["result"]  # "success", "failed", "revoked"

  - name: "p2p_message_delivery"
    type: "gauge"
    labels: ["device_pair"]  # % success rate
```

---

## Timeline & Roadmap

- **M3 (parallel):** Design + planning, don't block Phase 1
- **M4-W1 to M5-W4:** Full implementation + testing
- **M5-W4:** GA rollout (feature flag)
- **M6+:** Optimize battery, add relay (if needed)

---

## References

- **NaCl/libsodium:** Cryptography library (ChaCha20, Ed25519, X25519)
- **STUN:** RFC 5389 (NAT traversal)
- **QUIC:** RFC 9000 (transport layer)
- **Signal Protocol:** Reference for E2EE architecture
- **ADR-0001a:** K0 Bridge (P07 format)
- **ADR-0050b:** CRDT merge (same logic for internet sync)

---

**Last Updated:** 2025-10-16
**Version:** 1.0 (Future Implementation)
**Status:** Design Ready (Implementation starts M4)