#!/usr/bin/env python3
"""Records the BoxOffice monolith's responses for the cases the orders service takes over.

Usage: record.py [base-url]   (default: the live before state). Every case is replayed against the
same synthetic seed the service migrates, so totals, statuses and error codes are comparable.
Only synthetic e-mail addresses (example.test) are used.
"""
import json
import sys
import urllib.error
import urllib.request

base = (sys.argv[1] if len(sys.argv) > 1 else "https://tkt01-before.demo.otterworks.app").rstrip("/")
out_dir = __file__.rsplit("/", 1)[0]

def call(method, path, body=None, raw=None):
    data = raw.encode() if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"content-type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, {"raw": txt}

cases = [
    ("purchase_default_two_premium", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+default@example.test", "quantity": 2}, None),
    ("purchase_quantity_one", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+one@example.test", "quantity": 1}, None),
    ("purchase_quantity_four_theater", "POST", "/api/purchase",
     {"performanceId": 7, "email": "contract.orders+four@example.test", "quantity": 4}, None),
    ("purchase_delivery_print", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+print@example.test", "quantity": 2, "delivery": "PRINT"}, None),
    ("purchase_delivery_willcall", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+willcall@example.test", "quantity": 2, "delivery": "WILLCALL"}, None),
    ("purchase_promo_fanclub10", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+fanclub@example.test", "quantity": 2, "promoCode": "FANCLUB10"}, None),
    ("purchase_promo_hallnight_other_event", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+hallnight@example.test", "quantity": 2, "promoCode": "HALLNIGHT"}, None),
    ("purchase_promo_unknown_ignored", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+nopromo@example.test", "quantity": 2, "promoCode": "NOSUCHCODE"}, None),
    ("purchase_section_filter", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+section@example.test", "quantity": 2, "section": "A02"}, None),
    ("purchase_card_0000_declined", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+declined@example.test", "quantity": 2, "cardLast4": "0000"}, None),
    ("purchase_bad_quantity_zero", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+qty0@example.test", "quantity": 0}, None),
    ("purchase_bad_quantity_over_max", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+qty9@example.test", "quantity": 9}, None),
    ("purchase_performance_not_found", "POST", "/api/purchase",
     {"performanceId": 999, "email": "contract.orders+missing@example.test", "quantity": 2}, None),
    ("purchase_sold_out_unknown_section", "POST", "/api/purchase",
     {"performanceId": 1, "email": "contract.orders+soldout@example.test", "quantity": 2, "section": "Z99"}, None),
    ("purchase_invalid_json", "POST", "/api/purchase", None, "{not json"),
    ("order_lookup_not_found", "GET", "/api/orders/BO-DOESNOTEXIST", None, None),
    ("stats", "GET", "/api/stats", None, None),
]

recorded = {}
for name, method, path, body, raw in cases:
    status, resp = call(method, path, body, raw)
    recorded[name] = {"request": {"method": method, "path": path, "body": body if raw is None else raw},
                      "response": {"status": status, "body": resp}}
    print(f"{name}: {status} {json.dumps(resp)[:160]}")

# order lookup for the default purchase and the declined one
for src, name in (("purchase_default_two_premium", "order_lookup_confirmed"),
                  ("purchase_card_0000_declined", "order_lookup_payment_failed")):
    ref = recorded[src]["response"]["body"]["orderRef"]
    status, resp = call("GET", f"/api/orders/{ref}")
    recorded[name] = {"request": {"method": "GET", "path": f"/api/orders/{ref}", "body": None},
                      "response": {"status": status, "body": resp}}
    print(f"{name}: {status} {json.dumps(resp)[:160]}")

for name, rec in recorded.items():
    rec["source"] = base
    with open(f"{out_dir}/{name}.json", "w") as f:
        json.dump(rec, f, indent=2)
        f.write("\n")
