"""MongoDB (mmp_rt_billing) backend for the legacy billing facade.

One module per migration unit; each reads/writes only that unit's collections
(.migration/mapping/<unit>.json). Connection comes from the environment by NAME
(MONGODB_MMP_RT_TARGET_URI); the URI is never logged.
"""
import os
from functools import lru_cache

from pymongo import MongoClient

NAME = "mongo"
TARGET_SECRET = "MONGODB_MMP_RT_TARGET_URI"
TARGET_DB = "mmp_rt_billing"


@lru_cache(maxsize=1)
def client():
    uri = os.environ.get(TARGET_SECRET)
    if not uri:
        raise RuntimeError(f"{TARGET_SECRET} is not set")
    return MongoClient(uri)


def db():
    return client()[TARGET_DB]


def health():
    db().command("ping")
