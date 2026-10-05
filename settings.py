# ---- settings.py  (every later file starts with: from settings import settings) ----
import os, yaml
from types import SimpleNamespace
from dotenv import load_dotenv

load_dotenv()                                   # no-op in the deployed container
_res = yaml.safe_load(open(os.environ.get("PITWALL_RESOURCES", "resources.yaml")))

def env(name, required=True):
    v = os.environ.get(name)
    if required and not v:
        raise SystemExit(f"Missing environment variable {name}. Copy .env.example to .env and fill it in.")
    return v

settings = SimpleNamespace(
    region=env("AWS_REGION"),
    model_id=_res["model_id"],
    github=SimpleNamespace(**_res["github"]),
    tracker=SimpleNamespace(**_res["tracker"]),
    docs_domains=_res["docs"]["allowed_domains"],
    memory_id=env("MEMORY_ID", required=False),
    gateway_url=env("GATEWAY_URL", required=False),
    env=env,
)

SECRET_PREFIX = os.environ.get("PITWALL_SECRET_PREFIX", "pitwall/")
_cache = {}

def secret(name):
    """Environment variable first (local runs), then AWS Secrets Manager (deployed). Cached per process."""
    if name in _cache:
        return _cache[name]
    value = os.environ.get(name)
    if not value:
        import boto3
        try:
            value = boto3.client("secretsmanager", region_name=settings.region) \
                         .get_secret_value(SecretId=SECRET_PREFIX + name)["SecretString"]
        except Exception as e:
            raise SystemExit(f"Secret {name} not found in the environment or in Secrets Manager "
                             f"at {SECRET_PREFIX}{name}: {e}")
    _cache[name] = value
    return value

settings.secret = secret
