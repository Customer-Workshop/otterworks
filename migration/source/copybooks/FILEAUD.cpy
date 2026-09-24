      * FILEAUD  LRECL 160
       01  FA-REC.
           05  FA-AUD-KEY          PIC X(20).
           05  FA-ARCH-KEY         PIC X(16).
           05  FA-EVT-TYPE         PIC X(4).
           05  FA-EVT-TS           PIC X(32).
           05  FA-ACTOR            PIC X(12).
           05  FA-RET-CLASS        PIC X(4).
           05  FA-DISP-CD          PIC X(2).
           05  FA-CLIENT-IP        PIC X(15).
           05  FA-DETAIL           PIC X(40).
           05  FILLER              PIC X(15).
