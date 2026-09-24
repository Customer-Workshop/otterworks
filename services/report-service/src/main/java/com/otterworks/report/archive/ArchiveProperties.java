package com.otterworks.report.archive;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Archive read-path settings, bound from {@code archive.*} which in turn map the
 * {@code ARCHIVE_STORE}, {@code LDM_NAMESPACE}, {@code DB2_*} and {@code AZSQL_*}
 * environment variables (see application.properties).
 */
@ConfigurationProperties(prefix = "archive")
public class ArchiveProperties {

    private String store = "";
    private String namespace = "";
    private final Db2 db2 = new Db2();
    private final Azsql azsql = new Azsql();

    public String getStore() {
        return store;
    }

    public void setStore(String store) {
        this.store = store;
    }

    public String getNamespace() {
        return namespace;
    }

    public void setNamespace(String namespace) {
        this.namespace = namespace;
    }

    public Db2 getDb2() {
        return db2;
    }

    public Azsql getAzsql() {
        return azsql;
    }

    public ArchiveStoreType storeType() {
        return ArchiveStoreType.parse(store);
    }

    /** Db2 connection settings (DB2_HOST, DB2_PORT, DB2_DATABASE, DB2_USER, DB2_PASSWORD). */
    public static class Db2 {
        private String host = "";
        private String port = "50000";
        private String database = "";
        private String user = "";
        private String password = "";

        public String getHost() {
            return host;
        }

        public void setHost(String host) {
            this.host = host;
        }

        public String getPort() {
            return port;
        }

        public void setPort(String port) {
            this.port = port;
        }

        public String getDatabase() {
            return database;
        }

        public void setDatabase(String database) {
            this.database = database;
        }

        public String getUser() {
            return user;
        }

        public void setUser(String user) {
            this.user = user;
        }

        public String getPassword() {
            return password;
        }

        public void setPassword(String password) {
            this.password = password;
        }

        public boolean isComplete() {
            return !isBlank(host) && !isBlank(database) && !isBlank(user) && !isBlank(password);
        }

        public String jdbcUrl() {
            return "jdbc:db2://" + host + ":" + port + "/" + database;
        }
    }

    /** Azure SQL connection settings (AZSQL_SERVER, AZSQL_DATABASE, AZSQL_AUTH, AZSQL_USER, AZSQL_PASSWORD). */
    public static class Azsql {
        private String server = "";
        private String database = "";
        private String auth = "sql";
        private String user = "";
        private String password = "";
        private String clientId = "";

        public String getServer() {
            return server;
        }

        public void setServer(String server) {
            this.server = server;
        }

        public String getDatabase() {
            return database;
        }

        public void setDatabase(String database) {
            this.database = database;
        }

        public String getAuth() {
            return auth;
        }

        public void setAuth(String auth) {
            this.auth = auth;
        }

        public String getUser() {
            return user;
        }

        public void setUser(String user) {
            this.user = user;
        }

        public String getPassword() {
            return password;
        }

        public void setPassword(String password) {
            this.password = password;
        }

        public String getClientId() {
            return clientId;
        }

        public void setClientId(String clientId) {
            this.clientId = clientId;
        }

        public boolean isManagedIdentity() {
            return "managed-identity".equalsIgnoreCase(auth) || "msi".equalsIgnoreCase(auth);
        }

        public boolean isComplete() {
            if (isBlank(server) || isBlank(database)) {
                return false;
            }
            return isManagedIdentity() || (!isBlank(user) && !isBlank(password));
        }

        public String jdbcUrl() {
            String host = server.contains(".") ? server : server + ".database.windows.net";
            StringBuilder url = new StringBuilder("jdbc:sqlserver://").append(host).append(":1433;")
                    .append("databaseName=").append(database).append(';')
                    .append("encrypt=true;trustServerCertificate=false;loginTimeout=30;");
            if (isManagedIdentity()) {
                url.append("authentication=ActiveDirectoryMSI;");
                if (!isBlank(clientId)) {
                    url.append("msiClientId=").append(clientId).append(';');
                }
            }
            return url.toString();
        }
    }

    static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
