# UNLOAD01 - GnuCOBOL build / run / check (CONTRACTS.md 5.4)
#
#   make            build bin/UNLOAD01
#   make run        format fixtures/*.del into build/ and print the UNLOAD01 summary lines
#   make check      byte-compare the output with fixtures/*.expected.asc (+ .cnt/.sha256 sidecars)
#   make fixtures   regenerate fixtures from the seed generator (python3.12)
#   make clean

COBC      ?= cobc
COBCFLAGS ?= -x -std=default -Wall -I ../copybooks
PYTHON    ?= python3.12

BIN     := bin/UNLOAD01
SRC     := UNLOAD01.cbl
COPY    := ../copybooks/RETNPLCY.cpy ../copybooks/DOCARCH.cpy ../copybooks/FILEAUD.cpy
TABLES  := RETNPLCY DOCARCH FILEAUD
BUILD   := build

.PHONY: all build run check fixtures clean

all: build

build: $(BIN)

$(BIN): $(SRC) $(COPY)
	@mkdir -p bin
	$(COBC) $(COBCFLAGS) -o $@ $(SRC)

# Local run: UNLOAD01_DEL points run.sh at a pre-exported .del instead of calling db2.
run: $(BIN)
	@mkdir -p $(BUILD)
	@set -e; for t in $(TABLES); do \
	  UNLOAD01_DEL=fixtures/$$t.del ./run.sh $$t '' '~' $(BUILD)/$$t.asc; \
	done

check: run
	@set -e; for t in $(TABLES); do \
	  cmp fixtures/$$t.expected.asc $(BUILD)/$$t.asc; \
	  test "$$(cat $(BUILD)/$$t.asc.cnt)" = "$$(cat fixtures/$$t.expected.cnt)"; \
	  test "$$(cut -d' ' -f1 $(BUILD)/$$t.asc.sha256)" = "$$(sha256sum fixtures/$$t.expected.asc | cut -d' ' -f1)"; \
	  echo "check $$t: OK ($$(cat $(BUILD)/$$t.asc.cnt) rows)"; \
	done
	@# error paths: bad hex must exit 12, missing table must exit 12
	@if UNLOAD_TABLE=DOCARCH UNLOAD_IN=fixtures/bad-hex.del UNLOAD_OUT=$(BUILD)/bad.asc $(BIN) 2>/dev/null; then \
	  echo "check bad-hex: expected RC 12" >&2; exit 1; fi; echo "check bad-hex: OK (RC 12)"
	@if UNLOAD_TABLE=NOPE UNLOAD_IN=fixtures/DOCARCH.del UNLOAD_OUT=$(BUILD)/bad.asc $(BIN) 2>/dev/null; then \
	  echo "check bad-table: expected RC 12" >&2; exit 1; fi; echo "check bad-table: OK (RC 12)"

fixtures:
	$(PYTHON) fixtures/make_fixtures.py

clean:
	rm -rf bin $(BUILD)
