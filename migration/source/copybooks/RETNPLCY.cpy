      * RETNPLCY  LRECL 128
       01  RP-REC.
           05  RP-POLICY-CD        PIC X(4).
           05  RP-POLICY-DESC      PIC X(60).
           05  RP-RET-YEARS        PIC S9(4) COMP.
           05  RP-SUCCESSOR-CD     PIC X(4).
           05  RP-ACTIVE-FLG       PIC X.
           05  RP-DISP-ACTION      PIC X(4).
           05  RP-EFFECTIVE-TS     PIC X(32).
           05  FILLER              PIC X(21).
