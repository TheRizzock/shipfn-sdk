# Releasing

Developers install from this GitHub repo for now, so a release is just a tag:

1. Bump `__version__` in `shipfn/__init__.py` and commit.
2. `git tag v0.1.1 && git push origin main v0.1.1`
3. Developers pin it with `pip install "shipfn @ git+https://github.com/<owner>/shipfn-sdk@v0.1.1"`.
4. To make deployed functions use it, update the SDK pin in shipfn-api and redeploy the API. Builds copy whatever SDK version the API has installed.

Keep changes backwards compatible: existing images keep the SDK they were built with, but every redeploy uses the API's current one, and the API reads the result and log markers in `shipfn/runtime.py`.

## Later: PyPI

Pick the final package name first (a PyPI name can't be reused once published). Then:

1. On https://pypi.org, under **Your account → Publishing → Add a new pending publisher**, enter the project name, this repo, workflow `publish.yml` and environment `pypi`.
2. In this GitHub repo, **Settings → Environments → New environment** named `pypi` (optionally with yourself as a required reviewer).
3. Tags then also publish to PyPI through `.github/workflows/publish.yml`. Until step 1 is done, that job just fails, so nothing can be published by accident.
