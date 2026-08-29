-- Store dimension derived from the order headers.
CREATE TABLE IF NOT EXISTS core.dim_store (
    store_id   INTEGER      NOT NULL ENCODE az64,
    store_name VARCHAR(40)  ENCODE lzo,
    store_type VARCHAR(20)  ENCODE bytedict,
    PRIMARY KEY (store_id)
)
DISTSTYLE ALL
SORTKEY (store_id);
