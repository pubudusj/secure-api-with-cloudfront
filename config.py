import os
from dotenv import load_dotenv


class Config:
    """Config class. Load env vars."""

    def __init__(self) -> None:  # pylint: disable=too-many-statements
        """Initialize config class."""
        self._parse_environment_files()

        self._ssm_secure_parameter_name = os.getenv("SSM_SECURE_PARAMETER_NAME", None)

    @property
    def ssm_secure_parameter_name(self) -> str:
        """Get the SSM secure parameter name."""
        if not self._ssm_secure_parameter_name:
            raise ValueError("SSM_SECURE_PARAMETER_NAME is not set.")

        return self._ssm_secure_parameter_name

    @staticmethod
    def _parse_environment_files() -> None:
        """Load the .env file a."""

        load_dotenv(".env", verbose=True)
