      ******************************************************************
      * UNLOAD01 - format a Db2 delimited export into the copybook-exact
      *            fixed-width unload file (RECFM=F, no terminators).
      *
      * Input : UNLOAD_IN  - '|' delimited text, one row per line, produced
      *                      by run.sh (db2 EXPORT ... OF DEL NOCHARDEL),
      *                      FOR BIT DATA columns exported as HEX().
      *         UNLOAD_TABLE - RETNPLCY | DOCARCH | FILEAUD
      * Output: UNLOAD_OUT - fixed-width records (LRECL 128 / 256 / 160)
      *         stdout     - "UNLOAD01 ROWS=<n>"
      * RC    : 0 ok, 12 I/O or format error
      *
      * Column order in the input is the copybook field order (see run.sh).
      * Encoding rules: CONTRACTS.md 5.3 / FIELD-DERIVATION.md.
      ******************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. UNLOAD01.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-FILE ASSIGN TO WS-IN-PATH
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-IN-STATUS.
           SELECT RP-FILE ASSIGN TO WS-OUT-PATH
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-OUT-STATUS.
           SELECT DA-FILE ASSIGN TO WS-OUT-PATH
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-OUT-STATUS.
           SELECT FA-FILE ASSIGN TO WS-OUT-PATH
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-OUT-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  IN-FILE.
       01  IN-LINE                 PIC X(1024).

       FD  RP-FILE.
           COPY RETNPLCY.
       FD  DA-FILE.
           COPY DOCARCH.
       FD  FA-FILE.
           COPY FILEAUD.

       WORKING-STORAGE SECTION.
       01  WS-IN-PATH              PIC X(512).
       01  WS-OUT-PATH             PIC X(512).
       01  WS-TABLE                PIC X(8).
       01  WS-IN-STATUS            PIC XX.
       01  WS-OUT-STATUS           PIC XX.
       01  WS-EOF                  PIC X VALUE 'N'.
       01  WS-ROWS                 PIC 9(12) VALUE 0.
       01  WS-ROWS-DISP            PIC Z(11)9.
       01  WS-LINE-LEN             PIC 9(4).
       01  WS-FIELD-COUNT          PIC 99.
       01  WS-FIELDS.
           05  WS-F                PIC X(128) OCCURS 16 TIMES.
      *    packed-decimal parse work area: 23 integer + 8 fraction digits
       01  WS-DEC-TEXT             PIC X(128).
       01  WS-DEC-DIGITS.
           05  WS-DEC-INT          PIC X(23).
           05  WS-DEC-FRC          PIC X(8).
       01  WS-DEC-NUM REDEFINES WS-DEC-DIGITS
                                   PIC 9(23)V9(8).
       01  WS-DEC-SIGN             PIC S9 VALUE +1.
       01  WS-DEC-RESULT           PIC S9(23)V9(8) COMP-3.
       01  WS-INT-TEXT             PIC X(128).
       01  WS-INT-RESULT           PIC S9(18).
       01  WS-HEX-TEXT             PIC X(128).
       01  WS-HEX-OUT              PIC X(64).
       01  WS-HEX-LEN              PIC 999.
       01  WS-NIBBLE               PIC X.
       01  WS-BYTE-VAL             PIC 999.
       01  WS-I                    PIC 9(4).
       01  WS-J                    PIC 9(4).
       01  WS-K                    PIC 9(4).
       01  WS-P                    PIC 9(4).
       01  WS-DOT                  PIC 9(4).
       01  WS-TXT-LEN              PIC 9(4).

       PROCEDURE DIVISION.
       MAIN.
           ACCEPT WS-TABLE    FROM ENVIRONMENT "UNLOAD_TABLE"
           ACCEPT WS-IN-PATH  FROM ENVIRONMENT "UNLOAD_IN"
           ACCEPT WS-OUT-PATH FROM ENVIRONMENT "UNLOAD_OUT"
           IF WS-TABLE = SPACES OR WS-IN-PATH = SPACES
              OR WS-OUT-PATH = SPACES
               DISPLAY "UNLOAD01 E: UNLOAD_TABLE/UNLOAD_IN/UNLOAD_OUT "
                       "must be set" UPON STDERR
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           IF WS-TABLE NOT = "RETNPLCY" AND WS-TABLE NOT = "DOCARCH"
              AND WS-TABLE NOT = "FILEAUD"
               DISPLAY "UNLOAD01 E: unknown table " WS-TABLE UPON STDERR
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF

           OPEN INPUT IN-FILE
           IF WS-IN-STATUS NOT = "00"
               DISPLAY "UNLOAD01 E: open input status " WS-IN-STATUS
                   UPON STDERR
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM OPEN-OUTPUT
           IF WS-OUT-STATUS NOT = "00"
               DISPLAY "UNLOAD01 E: open output status " WS-OUT-STATUS
                   UPON STDERR
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF

           PERFORM UNTIL WS-EOF = 'Y'
               READ IN-FILE
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END PERFORM PROCESS-LINE
               END-READ
           END-PERFORM

           CLOSE IN-FILE
           PERFORM CLOSE-OUTPUT
           MOVE WS-ROWS TO WS-ROWS-DISP
           DISPLAY "UNLOAD01 ROWS=" FUNCTION TRIM(WS-ROWS-DISP)
           MOVE 0 TO RETURN-CODE
           STOP RUN.

       OPEN-OUTPUT.
           EVALUATE WS-TABLE
               WHEN "RETNPLCY" OPEN OUTPUT RP-FILE
               WHEN "DOCARCH"  OPEN OUTPUT DA-FILE
               WHEN "FILEAUD"  OPEN OUTPUT FA-FILE
           END-EVALUATE.

       CLOSE-OUTPUT.
           EVALUATE WS-TABLE
               WHEN "RETNPLCY" CLOSE RP-FILE
               WHEN "DOCARCH"  CLOSE DA-FILE
               WHEN "FILEAUD"  CLOSE FA-FILE
           END-EVALUATE.

       PROCESS-LINE.
           IF IN-LINE = SPACES
               EXIT PARAGRAPH
           END-IF
           MOVE SPACES TO WS-FIELDS
           MOVE 0 TO WS-FIELD-COUNT
           UNSTRING IN-LINE DELIMITED BY '|'
               INTO WS-F(1)  WS-F(2)  WS-F(3)  WS-F(4)
                    WS-F(5)  WS-F(6)  WS-F(7)  WS-F(8)
                    WS-F(9)  WS-F(10) WS-F(11) WS-F(12)
                    WS-F(13) WS-F(14) WS-F(15) WS-F(16)
               TALLYING IN WS-FIELD-COUNT
           END-UNSTRING
           EVALUATE WS-TABLE
               WHEN "RETNPLCY" PERFORM FORMAT-RETNPLCY
               WHEN "DOCARCH"  PERFORM FORMAT-DOCARCH
               WHEN "FILEAUD"  PERFORM FORMAT-FILEAUD
           END-EVALUATE
           IF WS-OUT-STATUS NOT = "00"
               DISPLAY "UNLOAD01 E: write status " WS-OUT-STATUS
                   UPON STDERR
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           ADD 1 TO WS-ROWS.

       CHECK-FIELD-COUNT.
           IF WS-FIELD-COUNT < WS-K
               MOVE WS-ROWS TO WS-ROWS-DISP
               DISPLAY "UNLOAD01 E: row " FUNCTION TRIM(WS-ROWS-DISP)
                       " has " WS-FIELD-COUNT " fields, expected "
                       WS-K UPON STDERR
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF.

      *----------------------------------------------------------------
      * RETNPLCY: POLICY_CODE|POLICY_DESC|RETENTION_YEARS|SUCCESSOR_CODE|
      *           ACTIVE_FLAG|DISPOSITION_ACTION|EFFECTIVE_TS
      *----------------------------------------------------------------
       FORMAT-RETNPLCY.
           MOVE 7 TO WS-K
           PERFORM CHECK-FIELD-COUNT
           MOVE SPACES TO RP-REC
           MOVE WS-F(1) TO RP-POLICY-CD
           MOVE WS-F(2) TO RP-POLICY-DESC
           MOVE WS-F(3) TO WS-INT-TEXT
           PERFORM PARSE-INT
           MOVE WS-INT-RESULT TO RP-RET-YEARS
           MOVE WS-F(4) TO RP-SUCCESSOR-CD
           MOVE WS-F(5) TO RP-ACTIVE-FLG
           MOVE WS-F(6) TO RP-DISP-ACTION
           MOVE WS-F(7) TO RP-EFFECTIVE-TS
           WRITE RP-REC.

      *----------------------------------------------------------------
      * DOCARCH: ARCH_KEY|DOC_ID|VERSION_NO|RETENTION_CLASS|LAST_ACCESS_TS|
      *   STORAGE_CHARGE|UNIT_RATE|HEX(OWNER_NAME)|HEX(DISPOSITION_DT)|
      *   LEGAL_HOLD_FLAG|CHECKSUM_ALG|CONTENT_SHA256|BYTE_SIZE|SOURCE_SYS
      *----------------------------------------------------------------
       FORMAT-DOCARCH.
           MOVE 14 TO WS-K
           PERFORM CHECK-FIELD-COUNT
           MOVE SPACES TO DA-REC
           MOVE WS-F(1) TO DA-AKEY
           MOVE WS-F(2) TO DA-DOCI
           MOVE WS-F(3) TO WS-INT-TEXT
           PERFORM PARSE-INT
           MOVE WS-INT-RESULT TO DA-VSEQ
           MOVE WS-F(4) TO DA-RCLS
           MOVE WS-F(5) TO DA-LACC
           MOVE WS-F(6) TO WS-DEC-TEXT
           PERFORM PARSE-DECIMAL
           MOVE WS-DEC-RESULT TO DA-SCHG
           MOVE WS-F(7) TO WS-DEC-TEXT
           PERFORM PARSE-DECIMAL
           MOVE WS-DEC-RESULT TO DA-AMT2
           MOVE WS-F(8) TO WS-HEX-TEXT
           MOVE 40 TO WS-HEX-LEN
           PERFORM PARSE-HEX
           MOVE WS-HEX-OUT(1:40) TO DA-TXT1
           MOVE WS-F(9) TO WS-HEX-TEXT
           MOVE 8 TO WS-HEX-LEN
           PERFORM PARSE-HEX
           MOVE WS-HEX-OUT(1:8) TO DA-DAT1
           MOVE WS-F(10) TO DA-FLG1
           MOVE WS-F(11) TO DA-CD01
           MOVE WS-F(12) TO DA-HSH1
           MOVE WS-F(13) TO WS-INT-TEXT
           PERFORM PARSE-INT
           MOVE WS-INT-RESULT TO DA-CNT1
           MOVE WS-F(14) TO DA-SRC
           WRITE DA-REC.

      *----------------------------------------------------------------
      * FILEAUD: AUDIT_KEY|ARCH_KEY|EVENT_TYPE|EVENT_TS|ACTOR_ID|
      *          RETENTION_CLASS|DISPOSITION_CODE|CLIENT_IP|DETAIL_TEXT
      *----------------------------------------------------------------
       FORMAT-FILEAUD.
           MOVE 9 TO WS-K
           PERFORM CHECK-FIELD-COUNT
           MOVE SPACES TO FA-REC
           MOVE WS-F(1) TO FA-AUD-KEY
           MOVE WS-F(2) TO FA-ARCH-KEY
           MOVE WS-F(3) TO FA-EVT-TYPE
           MOVE WS-F(4) TO FA-EVT-TS
           MOVE WS-F(5) TO FA-ACTOR
           MOVE WS-F(6) TO FA-RET-CLASS
           MOVE WS-F(7) TO FA-DISP-CD
           MOVE WS-F(8) TO FA-CLIENT-IP
           MOVE WS-F(9) TO FA-DETAIL
           WRITE FA-REC.

      *----------------------------------------------------------------
      * PARSE-INT: optional sign + digits -> WS-INT-RESULT
      *----------------------------------------------------------------
       PARSE-INT.
           MOVE FUNCTION TRIM(WS-INT-TEXT) TO WS-INT-TEXT
           IF FUNCTION TEST-NUMVAL(WS-INT-TEXT) NOT = 0
               PERFORM BAD-NUMBER
           END-IF
           COMPUTE WS-INT-RESULT = FUNCTION NUMVAL(WS-INT-TEXT).

      *----------------------------------------------------------------
      * PARSE-DECIMAL: [+|-]digits[.digits] -> S9(23)V9(8) COMP-3
      * Done digit-by-digit so 31 significant digits survive intact
      * (NUMVAL would round through a double).
      *----------------------------------------------------------------
       PARSE-DECIMAL.
           MOVE FUNCTION TRIM(WS-DEC-TEXT) TO WS-DEC-TEXT
           MOVE +1 TO WS-DEC-SIGN
           MOVE 1 TO WS-P
           IF WS-DEC-TEXT(1:1) = '-'
               MOVE -1 TO WS-DEC-SIGN
               MOVE 2 TO WS-P
           ELSE
               IF WS-DEC-TEXT(1:1) = '+'
                   MOVE 2 TO WS-P
               END-IF
           END-IF
           MOVE 0 TO WS-DOT
           MOVE 0 TO WS-TXT-LEN
           PERFORM VARYING WS-I FROM WS-P BY 1
                   UNTIL WS-I > 128 OR WS-DEC-TEXT(WS-I:1) = SPACE
               IF WS-DEC-TEXT(WS-I:1) = '.'
                   IF WS-DOT NOT = 0
                       PERFORM BAD-NUMBER
                   END-IF
                   MOVE WS-I TO WS-DOT
               ELSE
                   IF WS-DEC-TEXT(WS-I:1) < '0'
                      OR WS-DEC-TEXT(WS-I:1) > '9'
                       PERFORM BAD-NUMBER
                   END-IF
               END-IF
               MOVE WS-I TO WS-TXT-LEN
           END-PERFORM
           IF WS-TXT-LEN < WS-P
               PERFORM BAD-NUMBER
           END-IF
           MOVE ALL '0' TO WS-DEC-DIGITS
           IF WS-DOT = 0
               COMPUTE WS-J = WS-TXT-LEN + 1
           ELSE
               MOVE WS-DOT TO WS-J
           END-IF
      *    integer digits WS-P..WS-J-1, right-justified into 23
           COMPUTE WS-K = WS-J - WS-P
           IF WS-K > 23
      *        leading zeros beyond 23 are fine, other digits are not
               PERFORM VARYING WS-I FROM WS-P BY 1
                       UNTIL WS-I > WS-J - 24
                   IF WS-DEC-TEXT(WS-I:1) NOT = '0'
                       PERFORM BAD-NUMBER
                   END-IF
               END-PERFORM
               COMPUTE WS-P = WS-J - 23
               MOVE 23 TO WS-K
           END-IF
           IF WS-K > 0
               MOVE WS-DEC-TEXT(WS-P:WS-K)
                 TO WS-DEC-INT(24 - WS-K:WS-K)
           END-IF
      *    fraction digits after the dot, left-justified into 8
           IF WS-DOT NOT = 0
               COMPUTE WS-K = WS-TXT-LEN - WS-DOT
               IF WS-K > 8
                   PERFORM BAD-NUMBER
               END-IF
               IF WS-K > 0
                   MOVE WS-DEC-TEXT(WS-DOT + 1:WS-K)
                     TO WS-DEC-FRC(1:WS-K)
               END-IF
           END-IF
           COMPUTE WS-DEC-RESULT = WS-DEC-NUM * WS-DEC-SIGN.

      *----------------------------------------------------------------
      * PARSE-HEX: 2*WS-HEX-LEN hex chars -> WS-HEX-OUT raw bytes
      * (FOR BIT DATA columns; X'00' and CP037 bytes pass through).
      *----------------------------------------------------------------
       PARSE-HEX.
           MOVE ALL X'40' TO WS-HEX-OUT
           MOVE FUNCTION TRIM(WS-HEX-TEXT) TO WS-HEX-TEXT
           COMPUTE WS-K = WS-HEX-LEN * 2
           IF WS-HEX-TEXT(WS-K + 1:1) NOT = SPACE
               PERFORM BAD-HEX
           END-IF
           PERFORM VARYING WS-I FROM 1 BY 1 UNTIL WS-I > WS-HEX-LEN
               MOVE 0 TO WS-BYTE-VAL
               PERFORM VARYING WS-J FROM 1 BY 1 UNTIL WS-J > 2
                   COMPUTE WS-P = (WS-I - 1) * 2 + WS-J
                   MOVE WS-HEX-TEXT(WS-P:1) TO WS-NIBBLE
                   EVALUATE TRUE
                       WHEN WS-NIBBLE >= '0' AND WS-NIBBLE <= '9'
                           COMPUTE WS-BYTE-VAL = WS-BYTE-VAL * 16
                             + FUNCTION ORD(WS-NIBBLE)
                             - FUNCTION ORD('0')
                       WHEN WS-NIBBLE >= 'A' AND WS-NIBBLE <= 'F'
                           COMPUTE WS-BYTE-VAL = WS-BYTE-VAL * 16
                             + FUNCTION ORD(WS-NIBBLE)
                             - FUNCTION ORD('A') + 10
                       WHEN WS-NIBBLE >= 'a' AND WS-NIBBLE <= 'f'
                           COMPUTE WS-BYTE-VAL = WS-BYTE-VAL * 16
                             + FUNCTION ORD(WS-NIBBLE)
                             - FUNCTION ORD('a') + 10
                       WHEN OTHER
                           PERFORM BAD-HEX
                   END-EVALUATE
               END-PERFORM
               MOVE FUNCTION CHAR(WS-BYTE-VAL + 1) TO WS-HEX-OUT(WS-I:1)
           END-PERFORM.

       BAD-NUMBER.
           MOVE WS-ROWS TO WS-ROWS-DISP
           DISPLAY "UNLOAD01 E: row " FUNCTION TRIM(WS-ROWS-DISP)
                   " bad numeric text" UPON STDERR
           MOVE 12 TO RETURN-CODE
           STOP RUN.

       BAD-HEX.
           MOVE WS-ROWS TO WS-ROWS-DISP
           DISPLAY "UNLOAD01 E: row " FUNCTION TRIM(WS-ROWS-DISP)
                   " bad hex text for bit-data column" UPON STDERR
           MOVE 12 TO RETURN-CODE
           STOP RUN.
