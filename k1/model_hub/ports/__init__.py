"""Model Hub ports package [F09].

Re-exports all 7 port Protocols for single-import convenience.
"""

from k1.model_hub.ports.config_port import ConfigSubscription, IConfigPort
from k1.model_hub.ports.credential_port import ICredentialPort
from k1.model_hub.ports.event_port import IEventPort, Subscription
from k1.model_hub.ports.health_port import HealthReport, IHealthPort
from k1.model_hub.ports.hub_port import IModelHubPort
from k1.model_hub.ports.metrics_port import IMetricsPort
from k1.model_hub.ports.state_read_port import IStateReadPort, StateSnapshot

__all__ = [
    # Ports
    "IModelHubPort",
    "IEventPort",
    "IStateReadPort",
    "IMetricsPort",
    "IConfigPort",
    "ICredentialPort",
    "IHealthPort",
    # Supporting types
    "Subscription",
    "StateSnapshot",
    "ConfigSubscription",
    "HealthReport",
]
