"""Shared pytest configuration for the repo's tests."""


def pytest_configure(config):
    config.addinivalue_line("markers", "real_hermes: runs the real `hermes` CLI against a temp root "
                                       "(skipped unless HERMES_REAL_SMOKE=1 and hermes is on PATH)")
    config.addinivalue_line("markers", "real_toolchain: installs the web squad's pinned npm toolchain with pnpm "
                                       "(skipped without node, pnpm or the npm registry)")
