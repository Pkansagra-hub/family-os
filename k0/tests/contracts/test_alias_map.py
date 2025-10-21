from __future__ import annotations

from importlib import import_module

from ward import test  # type: ignore[import]

from k0.drivers.alias_map import AliasMap


@test("alias map bindings resolve to driver modules")
def _() -> None:
    alias_map = AliasMap.from_file()
    assert alias_map.bindings, "alias map must define at least one binding"

    for alias, module_name in alias_map.bindings.items():
        module = import_module(f"k0.drivers.{module_name}")
        assert (
            module is not None
        ), f"module k0.drivers.{module_name} not found for alias {alias}"

        exposed = [
            getattr(module, "build_driver", None),
            getattr(module, "Driver", None),
            getattr(module, "driver", None),
        ]
        if not any(candidate is not None for candidate in exposed):
            driver_like = [
                getattr(module, attr)
                for attr in dir(module)
                if attr.lower().endswith("driver")
            ]
            assert (
                driver_like
            ), f"driver module '{module_name}' must expose a driver factory or driver class"
