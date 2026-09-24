//UNLOAD01 JOB (ARCH),'DOCARCH UNLOAD',CLASS=A,MSGCLASS=X,
//         NOTIFY=&SYSUID,REGION=0M
//*-------------------------------------------------------------------*
//* UNLOAD01 - selective unload of ARCHIVE.<TABLE> to a RECFM=F file  *
//*                                                                   *
//* Documentation only: on the demo platform this job is performed by *
//* run.sh (db2 EXPORT + GnuCOBOL UNLOAD01). This member shows the    *
//* equivalent Db2 for z/OS batch: DSNTIAUL pulls the cursor rows,    *
//* UNLOAD01 formats them into the copybook layout, IDCAMS/ICETOOL    *
//* produce the .cnt sidecar. LRECL: RETNPLCY 128, DOCARCH 256,       *
//* FILEAUD 160. Symbolics are filled by the scheduler from the       *
//* migration manifest (table, key range, selection predicate).       *
//*-------------------------------------------------------------------*
//         SET TABLE=DOCARCH
//         SET KEYFROM='DA00000000000001'
//         SET KEYTO='DA00000000050000'
//         SET LRECL=256
//         SET HLQ=ARCH.UNLOAD
//*
//*---- STEP010: DSNTIAUL - delimited cursor extract -----------------*
//STEP010  EXEC PGM=IKJEFT01,DYNAMNBR=20
//STEPLIB  DD DISP=SHR,DSN=DSN.SDSNLOAD
//SYSTSPRT DD SYSOUT=*
//SYSPRINT DD SYSOUT=*
//SYSUDUMP DD SYSOUT=*
//SYSREC00 DD DSN=&HLQ..&TABLE..DEL,DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(200,50),RLSE),
//            DCB=(RECFM=VB,LRECL=1028,BLKSIZE=0)
//SYSPUNCH DD DUMMY
//SYSTSIN  DD *
  DSN SYSTEM(DSN1)
  RUN PROGRAM(DSNTIAUL) PLAN(DSNTIB12) PARMS('SQL') -
      LIB('DSN.RUNLIB.LOAD')
  END
/*
//SYSIN    DD *
  SELECT ARCH_KEY, DOC_ID, VERSION_NO, RETENTION_CLASS,
         LAST_ACCESS_TS, STORAGE_CHARGE, UNIT_RATE,
         HEX(OWNER_NAME), HEX(DISPOSITION_DT), LEGAL_HOLD_FLAG,
         CHECKSUM_ALG, CONTENT_SHA256, BYTE_SIZE, SOURCE_SYS
    FROM ARCHIVE.&TABLE
   WHERE (&LDM_SELECT_WHERE)
     AND ARCH_KEY >= &KEYFROM AND ARCH_KEY <= &KEYTO
   ORDER BY ARCH_KEY;
/*
//*
//*---- STEP020: UNLOAD01 - copybook-exact fixed-width format --------*
//STEP020  EXEC PGM=UNLOAD01,COND=(4,LT,STEP010),
//         PARM='&TABLE'
//STEPLIB  DD DISP=SHR,DSN=ARCH.BATCH.LOADLIB
//UNLOADIN DD DSN=&HLQ..&TABLE..DEL,DISP=SHR
//UNLOADOT DD DSN=&HLQ..&TABLE..ASC,DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(300,50),RLSE),
//            DCB=(RECFM=F,LRECL=&LRECL,BLKSIZE=0)
//SYSOUT   DD SYSOUT=*
//SYSPRINT DD SYSOUT=*
//*
//*---- STEP030: row count sidecar (.cnt) ----------------------------*
//STEP030  EXEC PGM=ICETOOL,COND=(4,LT,STEP020)
//TOOLMSG  DD SYSOUT=*
//DFSMSG   DD SYSOUT=*
//IN       DD DSN=&HLQ..&TABLE..ASC,DISP=SHR
//CNT      DD DSN=&HLQ..&TABLE..CNT,DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(1,1)),DCB=(RECFM=FB,LRECL=80,BLKSIZE=0)
//TOOLIN   DD *
  COUNT FROM(IN) WRITE(CNT) TEXT('UNLOAD01 ROWS=') DIGITS(12)
/*
//*
//*---- STEP040: SHA-256 sidecar (.sha256) via ICSF one-way hash -----*
//STEP040  EXEC PGM=IKJEFT01,COND=(4,LT,STEP030)
//SYSTSPRT DD SYSOUT=*
//SYSTSIN  DD *
  EXEC 'ARCH.BATCH.REXX(SHA256)' '&HLQ..&TABLE..ASC &HLQ..&TABLE..SHA256'
/*
//
