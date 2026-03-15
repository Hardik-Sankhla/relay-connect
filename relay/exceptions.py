"""relay-connect custom exceptions."""


class RelayError(Exception):
    """Base exception for all relay errors."""


class AuthError(RelayError):
    """Authentication or authorisation failed."""


class AgentNotFoundError(RelayError):
    """Named agent is not registered / reachable on the relay."""


class TunnelError(RelayError):
    """Tunnel could not be established or was dropped."""


class CertExpiredError(RelayError):
    """Short-lived session certificate has expired."""


class ConfigError(RelayError):
    """Invalid or missing configuration."""


class DeployError(RelayError):
    """File transfer / deploy operation failed."""
