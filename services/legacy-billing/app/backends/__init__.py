import os


def get_backend():
    selected = os.getenv("BILLING_BACKEND", "postgres").lower()
    if selected == "oracle":
        from . import oracle

        return oracle
    if selected == "mongo":
        from . import mongo

        return mongo
    from . import postgres

    return postgres


def backend_name():
    return {"oracle": "oracle", "mongo": "mongo"}.get(get_backend().NAME, "postgres")
