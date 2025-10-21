"""Telemetry component scaffolding for Pulumi programs."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import _renderer

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TelemetryConfig:
    """Configuration surface for the observability stack."""

    enable_grafana: bool = True
    enable_alertmanager: bool = True
    scrape_interval_seconds: int = 15
    dashboards_path: str = "./generated/dashboards"
    alert_rules_path: str = "./generated/rules"
    network_name: str = "k0-local"
    prometheus_image: str = "prom/prometheus:latest"
    grafana_image: str = "grafana/grafana:latest"
    alertmanager_image: str = "prom/alertmanager:latest"
    prometheus_config: str = "./telemetry/prometheus.yml"
    grafana_provisioning: str = "./telemetry/grafana/provisioning"
    alertmanager_config: str = "./telemetry/alertmanager.yml"
    grafana_admin_password: str = "ChangeMe!"
    prometheus_port: int = 9090
    grafana_port: int = 3000
    alertmanager_port: int = 9093

    @classmethod
    def from_pulumi(
        cls, namespace: str = "k0-telemetry", *, fallback_namespace: str = "k0"
    ) -> "TelemetryConfig":
        defaults = cls()
        configs = _load_pulumi_configs(namespace, fallback_namespace)
        if not configs:
            return defaults

        bool_keys = {
            "enable_grafana": ("enable_grafana", "enableGrafana"),
            "enable_alertmanager": ("enable_alertmanager", "enableAlertmanager"),
        }
        string_keys = {
            "dashboards_path": ("dashboards_path", "dashboardsPath"),
            "alert_rules_path": ("alert_rules_path", "alertRulesPath"),
            "network_name": ("network_name", "networkName"),
            "prometheus_image": ("prometheus_image", "prometheusImage"),
            "grafana_image": ("grafana_image", "grafanaImage"),
            "alertmanager_image": ("alertmanager_image", "alertmanagerImage"),
            "prometheus_config": ("prometheus_config", "prometheusConfig"),
            "grafana_provisioning": ("grafana_provisioning", "grafanaProvisioning"),
            "alertmanager_config": ("alertmanager_config", "alertmanagerConfig"),
            "grafana_admin_password": (
                "grafana_admin_password",
                "grafanaAdminPassword",
            ),
        }

        enable_grafana = _resolve_bool(
            configs, bool_keys["enable_grafana"], defaults.enable_grafana
        )
        enable_alertmanager = _resolve_bool(
            configs, bool_keys["enable_alertmanager"], defaults.enable_alertmanager
        )

        prometheus_port = _resolve_int(
            configs, ("prometheus_port", "prometheusPort"), defaults.prometheus_port
        )
        grafana_port = _resolve_int(
            configs, ("grafana_port", "grafanaPort"), defaults.grafana_port
        )
        alertmanager_port = _resolve_int(
            configs,
            ("alertmanager_port", "alertmanagerPort"),
            defaults.alertmanager_port,
        )
        scrape_interval_seconds = _resolve_int(
            configs,
            ("scrape_interval_seconds", "scrapeIntervalSeconds"),
            defaults.scrape_interval_seconds,
        )

        values: Dict[str, Any] = {}
        for attr, keys in string_keys.items():
            values[attr] = _resolve_str(configs, keys, getattr(defaults, attr))

        path_keys = (
            "dashboards_path",
            "alert_rules_path",
            "grafana_provisioning",
            "prometheus_config",
            "alertmanager_config",
        )
        for key in path_keys:
            values[key] = _normalise_relative_path(values[key])

        return cls(
            enable_grafana=enable_grafana,
            enable_alertmanager=enable_alertmanager,
            scrape_interval_seconds=scrape_interval_seconds,
            dashboards_path=values["dashboards_path"],
            alert_rules_path=values["alert_rules_path"],
            prometheus_image=values["prometheus_image"],
            grafana_image=values["grafana_image"],
            alertmanager_image=values["alertmanager_image"],
            prometheus_config=values["prometheus_config"],
            grafana_provisioning=values["grafana_provisioning"],
            alertmanager_config=values["alertmanager_config"],
            grafana_admin_password=values["grafana_admin_password"],
            prometheus_port=prometheus_port,
            grafana_port=grafana_port,
            alertmanager_port=alertmanager_port,
            network_name=values["network_name"],
        )

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "TelemetryConfig":
        payload = dict(mapping)
        dashboards = str(payload.get("dashboards_path", "./generated/dashboards"))
        grafana_provisioning_raw = payload.get("grafana_provisioning")
        if grafana_provisioning_raw is None:
            grafana_provisioning_raw = payload.get(
                "grafanaProvisioning", "./telemetry/grafana/provisioning"
            )
        grafana_provisioning = str(grafana_provisioning_raw)
        return cls(
            enable_grafana=bool(payload.get("enable_grafana", True)),
            enable_alertmanager=bool(payload.get("enable_alertmanager", True)),
            scrape_interval_seconds=int(payload.get("scrape_interval_seconds", 15)),
            dashboards_path=_normalise_relative_path(dashboards),
            alert_rules_path=_normalise_relative_path(
                str(payload.get("alert_rules_path", "./generated/rules"))
            ),
            prometheus_image=str(
                payload.get("prometheus_image", "prom/prometheus:latest")
            ),
            grafana_image=str(payload.get("grafana_image", "grafana/grafana:latest")),
            alertmanager_image=str(
                payload.get("alertmanager_image", "prom/alertmanager:latest")
            ),
            network_name=str(payload.get("network_name", "k0-local")),
            prometheus_config=str(
                _normalise_relative_path(
                    str(payload.get("prometheus_config", "./telemetry/prometheus.yml"))
                )
            ),
            grafana_provisioning=_normalise_relative_path(grafana_provisioning),
            alertmanager_config=str(
                _normalise_relative_path(
                    str(
                        payload.get(
                            "alertmanager_config", "./telemetry/alertmanager.yml"
                        )
                    )
                )
            ),
            grafana_admin_password=str(
                payload.get("grafana_admin_password", "ChangeMe!")
            ),
            prometheus_port=int(payload.get("prometheus_port", 9090)),
            grafana_port=int(payload.get("grafana_port", 3000)),
            alertmanager_port=int(payload.get("alertmanager_port", 9093)),
        )


@dataclass(slots=True)
class TelemetryComponentResult:
    """Rendered telemetry assets and Pulumi outputs."""

    artifacts: List[_renderer.RenderedArtifact]
    outputs: Dict[str, Any]

    @property
    def compose_fragments(self) -> List[Path]:
        return [artifact.path for artifact in self.artifacts]


def _render_telemetry_compose(
    *, stack_name: str, config: TelemetryConfig
) -> Optional[_renderer.RenderedArtifact]:
    context: Dict[str, Any] = {
        "prometheus_image": config.prometheus_image,
        "prometheus_config": config.prometheus_config,
        "prometheus_port": config.prometheus_port,
        "alert_rules_path": config.alert_rules_path,
        "enable_grafana": config.enable_grafana,
        "grafana_image": config.grafana_image,
        "grafana_provisioning": config.grafana_provisioning,
        "grafana_port": config.grafana_port,
        "grafana_admin_password": config.grafana_admin_password,
        "enable_alertmanager": config.enable_alertmanager,
        "alertmanager_image": config.alertmanager_image,
        "alertmanager_config": config.alertmanager_config,
        "alertmanager_port": config.alertmanager_port,
        "dashboards_path": config.dashboards_path,
        "network_name": config.network_name,
    }

    artifact = _renderer.write_template(
        "telemetry.yml.j2",
        target_name=f"{stack_name}-telemetry.yml",
        context=context,
        subdir=stack_name,
    )

    _sync_telemetry_assets(artifact.path.parent, config)

    logger.info(
        "Wrote telemetry compose fragment to %s (sha256=%s)",
        artifact.path,
        artifact.sha256,
    )

    return artifact


def provision_telemetry(
    *, stack_name: str, config: TelemetryConfig
) -> TelemetryComponentResult:
    """Wire baseline telemetry services for the selected stack."""

    artifacts: List[_renderer.RenderedArtifact] = []

    artifact = _render_telemetry_compose(stack_name=stack_name, config=config)
    if artifact is not None:
        artifacts.append(artifact)

    outputs: Dict[str, Any] = {
        "compose_fragments": [str(item.path) for item in artifacts],
        "compose_artifacts": [item.as_output() for item in artifacts],
        "enable_grafana": config.enable_grafana,
        "enable_alertmanager": config.enable_alertmanager,
        "scrape_interval_seconds": config.scrape_interval_seconds,
        "dashboards_path": config.dashboards_path,
        "alert_rules_path": config.alert_rules_path,
        "prometheus_config": config.prometheus_config,
        "grafana_provisioning": config.grafana_provisioning,
        "alertmanager_config": config.alertmanager_config,
        "ports": {
            "prometheus": config.prometheus_port,
            "grafana": config.grafana_port,
            "alertmanager": config.alertmanager_port,
        },
        "network_name": config.network_name,
    }

    return TelemetryComponentResult(artifacts=artifacts, outputs=outputs)


# Shared helpers -----------------------------------------------------------


def _normalise_relative_path(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    path = Path(text)
    if path.is_absolute() or text.startswith(".") or text.startswith(".."):
        return text
    return f"./{text}"


def _resolve_path(base: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _sync_telemetry_assets(target_dir: Path, config: TelemetryConfig) -> None:
    k0_root = Path(__file__).resolve().parents[3]
    telemetry_root = k0_root / "telemetry"
    generated_root = telemetry_root / "generated"

    dashboards_src = generated_root / "dashboards"
    rules_src = generated_root / "rules"
    dashboards_manifest = generated_root / "checksums_dashboards.json"
    rules_manifest = generated_root / "checksums_rules.json"
    provisioning_src = telemetry_root / "preview" / "grafana" / "provisioning"
    prometheus_src = telemetry_root / "preview" / "prometheus.yml"

    if not dashboards_src.exists():
        raise FileNotFoundError(
            "Grafana dashboards not found; run 'python -m k0.telemetry.render' before provisioning telemetry assets."
        )
    if not rules_src.exists():
        raise FileNotFoundError(
            "Prometheus alert rules not found; run 'python -m k0.telemetry.render' before provisioning telemetry assets."
        )

    dashboards_dest = _resolve_path(target_dir, config.dashboards_path)
    rules_dest = _resolve_path(target_dir, config.alert_rules_path)
    provisioning_dest = _resolve_path(target_dir, config.grafana_provisioning)
    prometheus_dest = _resolve_path(target_dir, config.prometheus_config)

    _copy_tree(dashboards_src, dashboards_dest)
    _copy_tree(rules_src, rules_dest)

    if dashboards_manifest.exists():
        _copy_file(
            dashboards_manifest, dashboards_dest.parent / "checksums_dashboards.json"
        )
    if rules_manifest.exists():
        _copy_file(rules_manifest, rules_dest.parent / "checksums_rules.json")

    if provisioning_src.exists():
        _copy_tree(provisioning_src, provisioning_dest)

    if prometheus_src.exists():
        _copy_file(prometheus_src, prometheus_dest)


def _load_pulumi_configs(*namespaces: str) -> List[Any]:
    try:
        pulumi_mod = __import__("pulumi")
    except ImportError:
        return []

    return [pulumi_mod.Config(namespace) for namespace in namespaces]


def _iter_configs(configs: Sequence[Any]):
    for cfg in configs:
        if cfg is not None:
            yield cfg


def _resolve_bool(configs: Sequence[Any], keys: Tuple[str, ...], default: bool) -> bool:
    for key in keys:
        value = _get_bool(configs, key)
        if value is not None:
            return value
    return default


def _resolve_str(configs: Sequence[Any], keys: Tuple[str, ...], default: str) -> str:
    for key in keys:
        value = _get_str(configs, key)
        if value is not None:
            return value
    return default


def _resolve_int(configs: Sequence[Any], keys: Tuple[str, ...], default: int) -> int:
    for key in keys:
        value = _get_int(configs, key)
        if value is not None:
            return value
    return default


def _get_bool(configs: Sequence[Any], key: str) -> Optional[bool]:
    for cfg in _iter_configs(configs):
        getter = getattr(cfg, "get_bool", None)
        if callable(getter):
            value = getter(key)
            if value is not None:
                return bool(value)

        raw_getter = getattr(cfg, "get", None)
        if callable(raw_getter):
            raw_value = raw_getter(key)
            if raw_value is not None:
                lowered = str(raw_value).strip().lower()
                if lowered in {"true", "1", "yes", "on"}:
                    return True
                if lowered in {"false", "0", "no", "off"}:
                    return False
    return None


def _get_str(configs: Sequence[Any], key: str) -> Optional[str]:
    for cfg in _iter_configs(configs):
        getter = getattr(cfg, "get", None)
        if callable(getter):
            value = getter(key)
            if value is not None:
                return str(value)
    return None


def _get_int(configs: Sequence[Any], key: str) -> Optional[int]:
    for cfg in _iter_configs(configs):
        getter = getattr(cfg, "get_int", None)
        if callable(getter):
            value = getter(key)
            if value is not None:
                return _coerce_int(value, key)

        raw_getter = getattr(cfg, "get", None)
        if callable(raw_getter):
            raw_value = raw_getter(key)
            if raw_value is not None:
                return _coerce_int(raw_value, key)
    return None


def _coerce_int(value: Any, key: str) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"Config key '{key}' must be an integer, received boolean value instead"
        )

    try:
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            raise ValueError(f"Config key '{key}' cannot be blank")
        return int(text, 10)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer for config key '{key}': {value}") from exc
