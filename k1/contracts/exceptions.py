# Contract system exceptions


class ContractError(Exception):
    pass


class WiringError(ContractError):
    pass


class ValidationError(ContractError):
    pass
