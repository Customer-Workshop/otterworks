      * DOCARCH  LRECL 256
       01  DA-REC.
           05  DA-AKEY             PIC X(16).
           05  DA-DOCI             PIC X(36).
           05  DA-VSEQ             PIC S9(4) COMP.
           05  DA-RCLS             PIC X(4).
           05  DA-LACC             PIC X(32).
           05  DA-SCHG             PIC S9(23)V9(8) COMP-3.
           05  DA-AMT2             PIC S9(23)V9(8) COMP-3.
           05  DA-TXT1             PIC X(40).
           05  DA-DAT1             PIC X(8).
           05  DA-FLG1             PIC X.
           05  DA-CD01             PIC X(8).
           05  DA-HSH1             PIC X(64).
           05  DA-CNT1             PIC S9(18) COMP.
           05  DA-SRC              PIC X(3).
           05  FILLER              PIC X(2).
