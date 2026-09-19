import os

import oracledb

oracledb.defaults.fetch_decimals = True


def oracle_connect():
    return oracledb.connect(
        user=os.getenv("ORACLE_USER", "ow_billing"),
        password=os.getenv("ORACLE_PASSWORD", "ow_billing"),
        host=os.getenv("ORACLE_HOST", "localhost"),
        port=int(os.getenv("ORACLE_PORT", "52521")),
        service_name=os.getenv("ORACLE_SERVICE", "FREEPDB1"),
    )
