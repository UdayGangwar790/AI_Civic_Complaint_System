import pytest

from app.core.rate_limit import rate_limiter


@pytest.fixture(autouse=True)
def reset_process_local_rate_limits():
    rate_limiter.reset()
    yield
    rate_limiter.reset()
