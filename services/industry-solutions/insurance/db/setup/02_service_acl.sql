-- COMMISSION_PKG is now a thin delegate: its body calls the extracted rule
-- owner (commission-service) over HTTP. Oracle refuses outbound callouts
-- unless the calling schema holds a network ACE for the target host, so grant
-- COMMISSION_PAY exactly one: http to commission-service:8000, nothing else.
-- Run as SYSTEM against FREEPDB1.
WHENEVER SQLERROR EXIT SQL.SQLCODE

BEGIN
    DBMS_NETWORK_ACL_ADMIN.append_host_ace(
        host       => 'commission-service',
        lower_port => 8000,
        upper_port => 8000,
        ace        => xs$ace_type(
                          privilege_list => xs$name_list('http'),
                          principal_name => 'COMMISSION_PAY',
                          principal_type => xs_acl.ptype_db));
END;
/

EXIT;
