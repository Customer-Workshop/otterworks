# Recon report: unit `w1-b01`

- **Verdict: PASS** (values redacted)
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `1.1.0`
- Tolerance version: `1.0.0`
- Seed: `20260926`
- Generated: 2026-09-26T18:20:48.757171+00:00
- 155 fields: Tier 2 aggregates deferred to Tier 3 (rules change the value)
- 118 string fields: min/max/distinct deferred to Tier 3

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 15 | PASS |
| 3 | keyed_diffs | 33338 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "customers": 25001
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "customers.custId",
    "customers.custSeqNo",
    "customers.tenantId",
    "customers.custNo",
    "customers.custName",
    "customers.custNameUpper",
    "customers.legalName",
    "customers.dbaName",
    "customers.addrLine1",
    "customers.addrLine2",
    "customers.addrLine3",
    "customers.addrLine4",
    "customers.addrLine5",
    "customers.addrLine6",
    "customers.city",
    "customers.stateCd",
    "customers.zip",
    "customers.zip4",
    "customers.countryCd",
    "customers.mailAddrLine1",
    "customers.mailAddrLine2",
    "customers.mailAddrLine3",
    "customers.mailAddrLine4",
    "customers.mailAddrLine5",
    "customers.mailAddrLine6",
    "customers.mailCity",
    "customers.mailStateCd",
    "customers.mailZip",
    "customers.phone1",
    "customers.phone2",
    "customers.phone3",
    "customers.phone4",
    "customers.phone1TypeCd",
    "customers.phone2TypeCd",
    "customers.phone3TypeCd",
    "customers.phone4TypeCd",
    "customers.fax",
    "customers.email1",
    "customers.email2",
    "customers.email3",
    "customers.signupDt",
    "customers.lastActivityDt",
    "customers.lastInvoiceDt",
    "customers.lastPaymentDt",
    "customers.terminateDt",
    "customers.statusCd",
    "customers.subStatusCd",
    "customers.custTypeCd",
    "customers.segmentCd",
    "customers.regionCd",
    "customers.territoryCd",
    "customers.channelCd",
    "customers.rateClassCd",
    "customers.taxExemptYn",
    "customers.creditHoldYn",
    "customers.dunningExemptYn",
    "customers.vipYn",
    "customers.curBalAmt",
    "customers.pastDueAmt",
    "customers.ytdBilledAmt",
    "customers.ltdBilledAmt",
    "customers.ytdPaidAmt",
    "customers.creditLimitAmt",
    "customers.relatedAcctIds",
    "customers.childAcctIds",
    "customers.promoCodesCsv",
    "customers.contactNotes",
    "customers.legacySysKey",
    "customers.mainframeAcctNo",
    "customers.conversionBatchNo",
    "customers.flag01",
    "customers.flag02",
    "customers.flag03",
    "customers.flag04",
    "customers.flag05",
    "customers.flag06",
    "customers.flag07",
    "customers.flag08",
    "customers.flag09",
    "customers.flag10",
    "customers.flag11",
    "customers.flag12",
    "customers.flag13",
    "customers.flag14",
    "customers.flag15",
    "customers.flag16",
    "customers.flag17",
    "customers.flag18",
    "customers.flag19",
    "customers.flag20",
    "customers.udf01",
    "customers.udf02",
    "customers.udf03",
    "customers.udf04",
    "customers.udf05",
    "customers.udf06",
    "customers.udf07",
    "customers.udf08",
    "customers.udf09",
    "customers.udf10",
    "customers.udf11",
    "customers.udf12",
    "customers.udf13",
    "customers.udf14",
    "customers.udf15",
    "customers.udf16",
    "customers.udf17",
    "customers.udf18",
    "customers.udf19",
    "customers.udf20",
    "customers.udf21",
    "customers.udf22",
    "customers.udf23",
    "customers.udf24",
    "customers.udf25",
    "customers.udf26",
    "customers.udf27",
    "customers.udf28",
    "customers.udf29",
    "customers.udf30",
    "customers.udf31",
    "customers.udf32",
    "customers.udf33",
    "customers.udf34",
    "customers.udf35",
    "customers.udf36",
    "customers.udf37",
    "customers.udf38",
    "customers.udf39",
    "customers.udf40",
    "customers.udfAmt01",
    "customers.udfAmt02",
    "customers.udfAmt03",
    "customers.udfAmt04",
    "customers.udfAmt05",
    "customers.udfAmt06",
    "customers.udfAmt07",
    "customers.udfAmt08",
    "customers.udfAmt09",
    "customers.udfAmt10",
    "customers.udfDt01",
    "customers.udfDt02",
    "customers.udfDt03",
    "customers.udfDt04",
    "customers.udfDt05",
    "customers.udfDt06",
    "customers.udfDt07",
    "customers.udfDt08",
    "customers.udfDt09",
    "customers.udfDt10",
    "customers.createdBy",
    "customers.createdDt",
    "customers.updatedBy",
    "customers.updatedDt",
    "customers.rowVersionNo"
  ],
  "string_aggregates_deferred_to_tier3": [
    {
      "field": "customers.custId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.tenantId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.custNo",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.custName",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.custNameUpper",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.legalName",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.dbaName",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.addrLine1",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.addrLine2",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.addrLine3",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.addrLine4",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.addrLine5",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.addrLine6",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.city",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.stateCd",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.zip",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.zip4",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.countryCd",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mailAddrLine1",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mailAddrLine2",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mailAddrLine3",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mailAddrLine4",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mailAddrLine5",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mailAddrLine6",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mailCity",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mailStateCd",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mailZip",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.phone1",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.phone2",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.phone3",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.phone4",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.fax",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.email1",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.email2",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.email3",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.signupDt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.lastActivityDt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.lastInvoiceDt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.lastPaymentDt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.terminateDt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.relatedAcctIds",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.childAcctIds",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.promoCodesCsv",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.contactNotes",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.legacySysKey",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.mainframeAcctNo",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag01",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag02",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag03",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag04",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag05",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag06",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag07",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag08",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag09",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag10",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag11",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag12",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag13",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag14",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag15",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag16",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag17",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag18",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag19",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.flag20",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf01",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf02",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf03",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf04",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf05",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf06",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf07",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf08",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf09",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf10",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf11",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf12",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf13",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf14",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf15",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf16",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf17",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf18",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf19",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf20",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf21",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf22",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf23",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf24",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf25",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf26",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf27",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf28",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf29",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf30",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf31",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf32",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf33",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf34",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf35",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf36",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf37",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf38",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf39",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udf40",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt01",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt02",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt03",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt04",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt05",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt06",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt07",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt08",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt09",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.udfDt10",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.createdBy",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "customers.updatedBy",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    }
  ],
  "fields_fully_deferred": 140
}
```

## Tier 3 coverage
```json
{
  "customers": {
    "mode": "full_diff",
    "population": 25001,
    "duplicate_source_key_count": 0
  },
  "embeds_graded": {
    "customers.attributes": 8337
  }
}
```
