"""Target contract for the `customers` collection: $jsonSchema validator + indexes.

The validator is the guarantee the legacy estate never had. It is intentionally
strict at the top level (`additionalProperties: false`), so the ad-hoc 156th
field that lives in ENTITY_ATTR_VALUE today (`TAX_REGION_OVERRIDE`) cannot be
smuggled back in as a rogue column, and `signup_dt` cannot regress to a
`DD-MON-YY` string.

`LEGACY_COLUMNS` mirrors OW_BILLING.CUSTOMER_MASTER (155 columns) minus the
columns that are modelled explicitly at the top level; it is the sparse
"repeating group" surface (ADDR_LINE_1..6, PHONE1..4, FLAG_01..20, UDF_01..40).
Values are emitted only when the source column is non-null.
"""

CUSTOMERS_COLLECTION = "customers"
QUARANTINE_COLLECTION = "customers_quarantine"
SOURCE_TABLE = "OW_BILLING.CUSTOMER_MASTER"
EAV_TABLE = "OW_BILLING.ENTITY_ATTR_VALUE"

# Columns lifted out of the flat legacy row into the document model.
MODELLED_COLUMNS = {
    "cust_id", "tenant_id", "cust_no", "cust_name", "legal_name", "signup_dt",
    "related_acct_ids", "promo_codes_csv", "cur_bal_amt", "past_due_amt",
    "ytd_billed_amt", "ltd_billed_amt", "ytd_paid_amt", "credit_limit_amt",
    "conversion_batch_no",
}

# CUSTOMER_MASTER columns carried verbatim under `legacy`, with the BSON type
# each Oracle type maps to. Mirrors services/legacy-billing/db/oracle/schema/02_horror.sql.
LEGACY_COLUMNS = {
    "cust_seq_no": "long", "cust_name_upper": "string", "dba_name": "string",
    "addr_line_1": "string", "addr_line_2": "string", "addr_line_3": "string",
    "addr_line_4": "string", "addr_line_5": "string", "addr_line_6": "string",
    "city": "string", "state_cd": "string", "zip": "string", "zip4": "string",
    "country_cd": "string", "mail_addr_line_1": "string", "mail_addr_line_2": "string",
    "mail_addr_line_3": "string", "mail_addr_line_4": "string", "mail_addr_line_5": "string",
    "mail_addr_line_6": "string", "mail_city": "string", "mail_state_cd": "string",
    "mail_zip": "string", "phone1": "string", "phone2": "string", "phone3": "string",
    "phone4": "string", "phone1_type_cd": "long", "phone2_type_cd": "long",
    "phone3_type_cd": "long", "phone4_type_cd": "long", "fax": "string", "email_1": "string",
    "email_2": "string", "email_3": "string", "last_activity_dt": "string",
    "last_invoice_dt": "string", "last_payment_dt": "string", "terminate_dt": "string",
    "status_cd": "long", "sub_status_cd": "long", "cust_type_cd": "long", "segment_cd": "long",
    "region_cd": "long", "territory_cd": "long", "channel_cd": "long", "rate_class_cd": "long",
    "tax_exempt_yn": "string", "credit_hold_yn": "string", "dunning_exempt_yn": "string",
    "vip_yn": "string", "child_acct_ids": "string", "contact_notes": "string",
    "legacy_sys_key": "string", "mainframe_acct_no": "string", "flag_01": "string",
    "flag_02": "string", "flag_03": "string", "flag_04": "string", "flag_05": "string",
    "flag_06": "string", "flag_07": "string", "flag_08": "string", "flag_09": "string",
    "flag_10": "string", "flag_11": "string", "flag_12": "string", "flag_13": "string",
    "flag_14": "string", "flag_15": "string", "flag_16": "string", "flag_17": "string",
    "flag_18": "string", "flag_19": "string", "flag_20": "string", "udf_01": "string",
    "udf_02": "string", "udf_03": "string", "udf_04": "string", "udf_05": "string",
    "udf_06": "string", "udf_07": "string", "udf_08": "string", "udf_09": "string",
    "udf_10": "string", "udf_11": "string", "udf_12": "string", "udf_13": "string",
    "udf_14": "string", "udf_15": "string", "udf_16": "string", "udf_17": "string",
    "udf_18": "string", "udf_19": "string", "udf_20": "string", "udf_21": "string",
    "udf_22": "string", "udf_23": "string", "udf_24": "string", "udf_25": "string",
    "udf_26": "string", "udf_27": "string", "udf_28": "string", "udf_29": "string",
    "udf_30": "string", "udf_31": "string", "udf_32": "string", "udf_33": "string",
    "udf_34": "string", "udf_35": "string", "udf_36": "string", "udf_37": "string",
    "udf_38": "string", "udf_39": "string", "udf_40": "string", "udf_amt_01": "decimal",
    "udf_amt_02": "decimal", "udf_amt_03": "decimal", "udf_amt_04": "decimal",
    "udf_amt_05": "decimal", "udf_amt_06": "decimal", "udf_amt_07": "decimal",
    "udf_amt_08": "decimal", "udf_amt_09": "decimal", "udf_amt_10": "decimal",
    "udf_dt_01": "string", "udf_dt_02": "string", "udf_dt_03": "string", "udf_dt_04": "string",
    "udf_dt_05": "string", "udf_dt_06": "string", "udf_dt_07": "string", "udf_dt_08": "string",
    "udf_dt_09": "string", "udf_dt_10": "string", "created_by": "string", "created_dt": "date",
    "updated_by": "string", "updated_dt": "date", "row_version_no": "long",
}

# Money columns folded into the `balances` subdocument.
BALANCE_COLUMNS = {
    "cur_bal_amt": "current_amount",
    "past_due_amt": "past_due_amount",
    "ytd_billed_amt": "ytd_billed_amount",
    "ltd_billed_amt": "ltd_billed_amount",
    "ytd_paid_amt": "ytd_paid_amount",
    "credit_limit_amt": "credit_limit_amount",
}

# Comma-separated VARCHAR2 lists promoted to real BSON arrays.
LIST_COLUMNS = {
    "related_acct_ids": "related_acct_ids",
    "promo_codes_csv": "promo_codes",
}

QUARANTINE_REASONS = (
    "dirty_date",
    "malformed_csv_list",
    "invalid_encoding",
    "missing_required_field",
    "null_attribute_value",
)


def _bson_type(kind: str):
    # pymongo encodes small Python ints as int32, so integral Oracle NUMBER
    # columns must accept both widths.
    return ["int", "long"] if kind == "long" else kind


def customers_validator() -> dict:
    """The $jsonSchema contract enforced on ow_tp_mongodb_<ns>.customers."""
    decimal_props = {name: {"bsonType": "decimal"} for name in BALANCE_COLUMNS.values()}
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "title": "OtterWorks customer (migrated from OW_BILLING.CUSTOMER_MASTER)",
            "required": ["_id", "customer_id", "namespace", "source"],
            "additionalProperties": False,
            "properties": {
                "_id": {"bsonType": "binData"},
                "customer_id": {"bsonType": "string"},
                "namespace": {"bsonType": "string"},
                "customer_no": {"bsonType": "string"},
                "customer_name": {"bsonType": "string"},
                "legal_name": {"bsonType": "string"},
                "tenant_id": {"bsonType": "string"},
                "signup_dt": {"bsonType": "date"},
                "related_acct_ids": {"bsonType": "array", "items": {"bsonType": "string"}},
                "promo_codes": {"bsonType": "array", "items": {"bsonType": "string"}},
                "balances": {
                    "bsonType": "object",
                    "additionalProperties": False,
                    "properties": decimal_props,
                },
                "attributes": {
                    "bsonType": "object",
                    "additionalProperties": {
                        "bsonType": "array",
                        "minItems": 1,
                        "items": {
                            "bsonType": "object",
                            "required": ["value"],
                            "additionalProperties": False,
                            "properties": {
                                "value": {"bsonType": "string"},
                                "attr_type": {"bsonType": "string"},
                                "created_dt": {"bsonType": "date"},
                                "created_dt_raw": {"bsonType": "string"},
                            },
                        },
                    },
                },
                "source": {
                    "bsonType": "object",
                    "required": ["table", "batch_no"],
                    "additionalProperties": False,
                    "properties": {
                        "table": {"bsonType": "string"},
                        "batch_no": {"bsonType": ["int", "long"]},
                    },
                },
                "legacy": {
                    "bsonType": "object",
                    "additionalProperties": False,
                    "properties": {
                        name: {"bsonType": _bson_type(kind)}
                        for name, kind in LEGACY_COLUMNS.items()
                    },
                },
            },
        }
    }


def quarantine_validator() -> dict:
    """The quarantine ledger contract: every attributed row names its reason."""
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["_id", "customer_id", "namespace", "reason", "source"],
            "additionalProperties": False,
            "properties": {
                "_id": {"bsonType": "binData"},
                "customer_id": {"bsonType": "string"},
                "namespace": {"bsonType": "string"},
                "reason": {"enum": list(QUARANTINE_REASONS)},
                "field": {"bsonType": "string"},
                "raw_value": {"bsonType": "string"},
                "raw_hex": {"bsonType": "string"},
                "parsed_elements": {"bsonType": "array", "items": {"bsonType": "string"}},
                "detail": {"bsonType": "string"},
                "source": {
                    "bsonType": "object",
                    "required": ["table", "batch_no"],
                    "additionalProperties": False,
                    "properties": {
                        "table": {"bsonType": "string"},
                        "batch_no": {"bsonType": ["int", "long"]},
                    },
                },
            },
        }
    }


CUSTOMER_INDEXES = [
    {"keys": [("customer_id", 1)], "name": "uq_customer_id", "unique": True},
    {"keys": [("namespace", 1), ("customer_no", 1)], "name": "ix_namespace_customer_no"},
    {"keys": [("tenant_id", 1)], "name": "ix_tenant_id"},
    {"keys": [("signup_dt", 1)], "name": "ix_signup_dt"},
]

QUARANTINE_INDEXES = [
    {"keys": [("customer_id", 1), ("reason", 1), ("field", 1)],
     "name": "uq_customer_reason_field", "unique": True},
    {"keys": [("reason", 1)], "name": "ix_reason"},
]


def database_name(namespace: str) -> str:
    return f"ow_tp_mongodb_{namespace}"


def quarantine_database_name(namespace: str) -> str:
    return f"ow_tp_mongodb_{namespace}_quarantine"
