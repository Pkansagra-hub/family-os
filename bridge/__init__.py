# K0-K1 Bridge
# Cross-kernel security gateway
#
# Location: bridge/ (root level - NOT inside K0 or K1)
# Source of Truth: bridge/README.md
#
# Purpose:
# 1. Kernel Transport: K0 <-> K1 memory/storage communication
# 2. Connector Security: Tool -> External device security gateway
# 3. Device Sync: Multi-device family sync via K0 P07 pipeline
#
# This module is the ONLY authorized path for:
# - K1 components to access K0 storage (SessionState COLD tier)
# - K1 tools to call external devices (Philips Hue, Nest, etc.)
# - Device-to-device sync (LAN mDNS, P2P internet)

__version__ = "0.1.0"
__status__ = "alpha"
