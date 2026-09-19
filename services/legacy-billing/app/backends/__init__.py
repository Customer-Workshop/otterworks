import os


def get_backend():
    if os.getenv("BILLING_BACKEND", "postgres").lower() == "oracle":
        from . import oracle

        return oracle
    from . import postgres

    return postgres


def backend_name():
    return "oracle" if get_backend().__name__.endswith(".oracle") else "postgres"
