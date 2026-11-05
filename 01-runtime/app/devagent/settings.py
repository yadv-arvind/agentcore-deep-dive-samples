# ---- settings.py  (every later file starts with: from settings import settings) ----
import os, yaml
from types import SimpleNamespace
from dotenv import load_dotenv

load_dotenv()                                   # no-op in the deployed container
_res = yaml.safe_load(open(os.environ.get("PITWALL_RESOURCES", "resources.yaml")))

def env(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Missing environment variable {name}. Copy .env.example to .env and fill it in.")
    return v

settings = SimpleNamespace(
    region=env("AWS_REGION"),
    model_id=_res["model_id"],
)
